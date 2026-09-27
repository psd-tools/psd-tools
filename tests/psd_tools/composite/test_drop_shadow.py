"""The drop shadow layer effect, drawn and composited.

Four documents in the fixture corpus carry a drop shadow Photoshop rendered
into its own preview -- ``layer_effects.psd``, ``masks.psb``,
``layer_comps.psb`` and ``layer_params.psb`` -- so the fidelity tests below
measure against those rather than against a shadow authored for the purpose.
The combinations the corpus does not pair with a shadow (a faded layer, fill
opacity, the knockout switched off, a shadow on a group or on a pixel layer
with a vector mask) are forged, by editing or copying ``masks.psb``'s.
"""

import copy
import logging
from typing import Any, Callable, cast

import numpy as np
import pytest
from PIL import Image

from psd_tools.api.layers import Group, Layer
from psd_tools.api.psd_image import PSDImage
from psd_tools.composite import composite, effects, utils
from psd_tools.composite.composite import (
    Compositor,
    _content_bbox,
    _effect_reach,
    _shadow_reach,
    paste,
)
from psd_tools.constants import BlendMode, Tag
from psd_tools.psd.base import ByteElement
from psd_tools.psd.descriptor import Descriptor, Double
from psd_tools.terminology import Key, Klass

from ..utils import full_name
from .test_composite import _mse

logger = logging.getLogger(__name__)


def _disc(size: int, radius: float) -> np.ndarray:
    """A hard-edged disc centred on a ``size`` x ``size`` canvas."""
    centre = size // 2
    yy, xx = np.mgrid[0:size, 0:size]
    disc = (xx - centre) ** 2 + (yy - centre) ** 2 <= radius**2
    return disc.astype(np.float32)[:, :, None]


def _centroid(coverage: np.ndarray) -> tuple[float, float]:
    weights = coverage[:, :, 0]
    yy, xx = np.mgrid[0 : weights.shape[0], 0 : weights.shape[1]]
    total = float(weights.sum())
    return float((xx * weights).sum()) / total, float((yy * weights).sum()) / total


@pytest.mark.parametrize(
    ("angle", "expected"),
    [
        (90.0, (0.0, 10.0)),
        (0.0, (-10.0, 0.0)),
        (180.0, (10.0, 0.0)),
        (-90.0, (0.0, -10.0)),
    ],
)
def test_a_drop_shadow_is_cast_away_from_the_light(
    angle: float, expected: tuple[float, float]
) -> None:
    """The shadow falls away from the light, down the image for 90 degrees.

    Photoshop's angle is where the light comes from, so the shadow falls the
    other way, and image rows run down: a light at 90 degrees is overhead and
    casts the shadow straight down. Unblurred, so the silhouette moves whole
    and its centroid moves by exactly the distance.
    """
    shape = _disc(81, 12.0)
    shadow = effects.draw_drop_shadow(
        (0, 0, 81, 81), shape, distance=10.0, angle=angle, size=0.0, spread=0.0
    )
    x, y = _centroid(shadow)
    assert (x - 40.0, y - 40.0) == pytest.approx(expected, abs=1e-3)


def test_spread_grows_the_silhouette_and_takes_the_blur_it_replaces() -> None:
    """Spread is Photoshop's "expands the matte before blurring".

    The descriptor stores it under the key an inner shadow calls choke, which
    shrinks; #679 first read it that way for a drop shadow too. At 100% the
    whole of ``size`` goes to the growth and none to the blur, so the shadow
    is the silhouette grown by ``size`` with a hard edge. At 0% the same
    reach is all blur.
    """
    shape = _disc(81, 12.0)
    hard = effects.draw_drop_shadow(
        (0, 0, 81, 81), shape, distance=0.0, angle=0.0, size=6.0, spread=100.0
    )
    soft = effects.draw_drop_shadow(
        (0, 0, 81, 81), shape, distance=0.0, angle=0.0, size=6.0, spread=0.0
    )
    row = hard[40, 40:, 0]
    # Covered out to the disc's radius plus the size, and not a pixel beyond.
    assert np.all(row[: 12 + 6 + 1] == 1.0), row
    assert np.all(row[12 + 6 + 1 :] == 0.0), row
    # The soft shadow ramps across the same reach instead.
    ramp = soft[40, 40 + 12 - 3 : 40 + 12 + 6, 0]
    assert np.all(np.diff(ramp) < 0), ramp
    assert np.all((ramp > 0.0) & (ramp < 1.0)), ramp


def test_a_drop_shadow_blur_treats_the_canvas_edge_as_empty() -> None:
    """Nothing past the canvas casts a shadow (#679 review).

    ``gaussian_filter`` reflects at the edge by default, which reads a
    silhouette that touches the edge as continuing past it: the pixel at the
    edge stayed at 0.99 here where half the kernel falls on empty canvas and
    it should be about half covered.
    """
    shape = np.zeros((40, 40, 1), dtype=np.float32)
    shape[:, :10] = 1.0
    shadow = effects.draw_drop_shadow(
        (0, 0, 40, 40), shape, distance=0.0, angle=0.0, size=9.0, spread=0.0
    )
    assert 0.5 < float(shadow[20, 0, 0]) < 0.6


def test_a_drop_shadow_asks_for_scipy_by_name_when_it_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shadow needs scipy the way a stroke does, and says so the same way."""
    monkeypatch.setattr(effects, "HAS_SCIPY", False)
    with pytest.raises(ImportError, match="Drop shadow effects require: scipy"):
        effects.draw_drop_shadow(
            (0, 0, 8, 8),
            np.ones((8, 8, 1), dtype=np.float32),
            distance=1.0,
            angle=90.0,
            size=2.0,
            spread=0.0,
        )


def test_drop_shadow_bbox_holds_the_layer_and_the_cast_shadow() -> None:
    """The canvas grows by the size on every side and by the offset on one."""
    bbox = (10, 20, 30, 40)
    assert effects.drop_shadow_bbox(bbox, 5.0, 90.0, 3.0) == (5, 15, 35, 50)
    assert effects.drop_shadow_bbox(bbox, 5.0, 0.0, 3.0) == (0, 15, 35, 45)
    assert effects.drop_shadow_bbox((0, 0, 0, 0), 5.0, 90.0, 3.0) == (0, 0, 0, 0)


@pytest.mark.parametrize("angle", [0.0, 90.0, 180.0, -90.0, 120.0])
def test_drop_shadow_bbox_does_not_depend_on_where_the_layer_is(angle: float) -> None:
    """The same layer moved is the same canvas moved (#679 review).

    ``cos(90)`` is 6e-17 rather than 0, which floored against 0 took an extra
    column and against 10 did not.
    """
    here = effects.drop_shadow_bbox((0, 0, 20, 20), 5.0, angle, 3.0)
    there = effects.drop_shadow_bbox((10, 10, 30, 30), 5.0, angle, 3.0)
    assert there == tuple(value + 10 for value in here)


def test_the_shadow_canvas_holds_the_whole_shadow() -> None:
    """Nothing the shadow casts falls past the canvas it is drawn on.

    Drawn on the canvas :py:func:`drop_shadow_bbox` asks for and again with
    room to spare, the two agree, and the roomy one has nothing outside the
    first. A gaussian left to its default reach ran on past ``size``, and the
    canvas cut it off in a visible rectangle (#679 review).
    """
    bbox = (0, 0, 40, 40)
    shape = np.ones((40, 40, 1), dtype=np.float32)
    for spread in (0.0, 30.0):
        values = dict(distance=7.0, angle=120.0, size=12.0, spread=spread)
        canvas = effects.drop_shadow_bbox(bbox, 7.0, 120.0, 12.0)
        roomy = (canvas[0] - 20, canvas[1] - 20, canvas[2] + 20, canvas[3] + 20)
        tight = effects.draw_drop_shadow(canvas, paste(canvas, bbox, shape), **values)
        wide = effects.draw_drop_shadow(roomy, paste(roomy, bbox, shape), **values)
        assert np.allclose(paste(roomy, canvas, tight), wide, atol=1e-6)


@pytest.mark.parametrize("alpha", [127 / 255.0, 128 / 255.0])
def test_spread_keeps_the_coverage_of_a_partial_silhouette(alpha: float) -> None:
    """A half-covered silhouette grows into a half-covered matte.

    Spread is a dilation of the matte, which takes the highest coverage
    within reach and invents none. Growing the silhouette's half-coverage
    contour instead turned a matte at 128/255 opaque and grew one at 127/255
    not at all (#679 review).
    """
    shape = np.zeros((41, 41, 1), dtype=np.float32)
    shape[15:26, 15:26] = alpha
    grown = effects.draw_drop_shadow(
        (0, 0, 41, 41), shape, distance=0.0, angle=0.0, size=6.0, spread=100.0
    )
    # Inside the square, and three pixels out from its edge.
    assert float(grown[20, 20, 0]) == pytest.approx(alpha, abs=1e-6)
    assert float(grown[20, 28, 0]) == pytest.approx(alpha, abs=1 / 16)
    assert float(grown[20, 35, 0]) == 0.0


def test_spread_grows_a_faint_feather_at_its_own_levels() -> None:
    """A feather with more coverages than there are levels still grows.

    The levels are picked from the silhouette's own coverages. Spaced evenly
    over 0 to 1 instead, a feather that never passed 5% fell below the first
    of them and did not grow at all (#679 review).
    """
    shape = np.zeros((41, 41, 1), dtype=np.float32)
    shape[15:26, 15:26, 0] = np.linspace(0.001, 0.05, 121).reshape(11, 11)
    assert np.unique(shape[shape > 0]).size > effects._SPREAD_LEVELS
    grown = effects.draw_drop_shadow(
        (0, 0, 41, 41), shape, distance=0.0, angle=0.0, size=6.0, spread=100.0
    )
    assert (grown > 0).sum() > (shape > 0).sum()
    # Three pixels past the square's densest corner, within a step of it.
    assert float(grown[28, 28, 0]) == pytest.approx(0.05, abs=0.05 / 8)


def test_a_pixel_elsewhere_does_not_drop_a_plateau_s_spread() -> None:
    """The levels are spaced over coverage, not over the coverages present.

    A plateau at 0.99 beside a faint feather of 29 coverages: picking every
    few of the coverages present left no level between the feather's top
    and the plateau, so one opaque pixel added across the canvas, nowhere
    near either, sank the plateau's grown fringe from 0.99 to 0.029 (#679
    review). Spaced over coverage, a level is never more than a fifteenth of
    the range below what it grows.
    """
    shape = np.zeros((41, 81, 1), dtype=np.float32)
    shape[15:26, 15:26] = 0.99
    shape[15:26, 45:74, 0] = np.linspace(0.001, 0.029, 29)
    alone = effects.draw_drop_shadow(
        (0, 0, 81, 41), shape, distance=0.0, angle=0.0, size=6.0, spread=100.0
    )
    shape[0, 80] = 1.0
    beside = effects.draw_drop_shadow(
        (0, 0, 81, 41), shape, distance=0.0, angle=0.0, size=6.0, spread=100.0
    )
    # Three pixels out from the plateau's left edge.
    for grown in (alone, beside):
        assert float(grown[20, 12, 0]) == pytest.approx(0.99, abs=1.0 / 15)


# -- Compositing ------------------------------------------------------------ #


def _masks_card(name: str = "Rounded Rectangle 3") -> tuple[PSDImage, Layer]:
    """``masks.psb`` and one of its two cards.

    Each card is a 262 x 287 shape layer casting a black Multiply shadow of
    size 50 at 10% opacity, 2 px straight down, with the layer knocking it
    out -- Photoshop's defaults, apart from the size.
    """
    psd = PSDImage.open(full_name("masks.psb"))
    return psd, next(layer for layer in psd if layer.name == name)


def _around(layer: Layer, margin: int = 16) -> tuple[int, int, int, int]:
    left, top, right, bottom = layer.bbox
    return (left - margin, top - margin, right + margin, bottom + margin)


def _alone(
    layer: Layer, viewport: tuple[int, int, int, int], force: bool = False
) -> np.ndarray:
    """The layer's alpha, composited alone over nothing on ``viewport``."""
    height, width = viewport[3] - viewport[1], viewport[2] - viewport[0]
    compositor = Compositor(
        viewport,
        np.ones((height, width, 3), dtype=np.float32),
        np.zeros((height, width, 1), dtype=np.float32),
        force=force,
    )
    compositor.apply(layer)
    return compositor.finish()[2]


def _forge_shadow(layer: Layer, angle: float = 90.0, **values: float) -> Descriptor:
    """Give ``layer`` a copy of the first card's effects, its shadow edited.

    The shadow is lit from ``angle`` rather than from the document's global
    light, which differs between documents. ``values`` maps descriptor keys,
    by their :py:class:`Key` names, to the number to put there. Returns the
    shadow's descriptor.
    """
    _, card = _masks_card()
    block = copy.deepcopy(
        card.tagged_blocks.get_data(Tag.OBJECT_BASED_EFFECTS_LAYER_INFO)
    )
    layer.tagged_blocks.set_data(Tag.OBJECT_BASED_EFFECTS_LAYER_INFO, block)
    shadow = block[Klass.DropShadow]
    shadow[Key.UseGlobalAngle] = False
    shadow[Key.LocalLightingAngle] = Double(angle)
    for name, value in values.items():
        shadow[getattr(Key, name)] = Double(value)
    return shadow


def _shadow_descriptor(layer: Layer) -> Descriptor:
    return next(iter(layer.effects.find("dropshadow"))).descriptor


def test_layer_opacity_fades_the_drop_shadow_with_the_layer() -> None:
    """A half-opaque layer casts a half-opaque shadow (#679 review).

    The shadow is composited apart from the layer's source, as an outset
    stroke's band is, so it carries the layer opacity itself: nothing later
    applies it where the layer covers nothing.
    """
    psd, layer = _masks_card()
    viewport = _around(layer)
    full = _alone(layer, viewport)
    layer.opacity = 128
    faded = _alone(layer, viewport)

    # Four pixels left of the card, where only the shadow paints.
    y, x = (layer.bbox[1] + layer.bbox[3]) // 2 - viewport[1], 16 - 4
    assert float(full[y, x, 0]) > 0.01, "no shadow to fade"
    assert float(faded[y, x, 0]) == pytest.approx(
        float(full[y, x, 0]) * 128 / 255.0, rel=1e-4
    )


def test_fill_opacity_leaves_the_drop_shadow_and_the_knockout_alone() -> None:
    """Fill opacity fades the layer's own paint and not its effects.

    At fill 0 the card paints nothing, and its shadow is still there at full
    strength beside it. Under it the knockout, which cuts by the layer's
    coverage rather than by its paint, leaves nothing at all: that is the
    "shadow only" setup Photoshop's knockout switch exists for.
    """
    psd, layer = _masks_card()
    viewport = _around(layer)
    full = _alone(layer, viewport)
    layer.tagged_blocks.set_data(Tag.BLEND_FILL_OPACITY, ByteElement(0))
    faded = _alone(layer, viewport)

    y = (layer.bbox[1] + layer.bbox[3]) // 2 - viewport[1]
    beside, under = 16 - 4, (layer.bbox[2] - layer.bbox[0]) // 2 + 16
    assert float(faded[y, beside, 0]) == pytest.approx(float(full[y, beside, 0]))
    assert float(faded[y, under, 0]) == 0.0


def test_a_drop_shadow_lies_beneath_the_layer_not_beside_it() -> None:
    """A shadow is attenuated by the layer over it, not scaled up to fill in.

    An outset stroke's band goes on at ``t / (1 - covered)`` so that it adds
    to the layer's coverage. A shadow is under the layer instead, so with the
    knockout off the layer composites over it like over any backdrop: at fill
    ``f`` the alpha is ``f + a0 * (1 - f)``, where ``a0`` is the shadow alone,
    read off the same card at fill 0. The band's arithmetic gives ``f + a0``
    wherever the shadow is partial.

    Read just inside the card's left edge, where the card covers the pixel
    fully and its shadow, cast 2 px down, is still ramping up.
    """
    psd, layer = _masks_card()
    _shadow_descriptor(layer)[b"layerConceals"] = False
    viewport = _around(layer)
    y = (layer.bbox[1] + layer.bbox[3]) // 2 - viewport[1]
    inside = slice(16 + 2, 16 + 20)

    layer.tagged_blocks.set_data(Tag.BLEND_FILL_OPACITY, ByteElement(0))
    shadow = _alone(layer, viewport)[y, inside, 0]
    fill = 64
    layer.tagged_blocks.set_data(Tag.BLEND_FILL_OPACITY, ByteElement(fill))
    alpha = _alone(layer, viewport)[y, inside, 0]

    assert np.all(np.diff(shadow) > 0), "the shadow is not partial here"
    f = fill / 255.0
    assert np.allclose(alpha, f + shadow * (1.0 - f), atol=1e-6)


def test_a_drop_shadow_reaches_a_viewport_its_layer_misses() -> None:
    """The shadow is cast from the whole layer, wherever the viewport is.

    The strip below the card is clear of the card's own box, so the cull has
    to measure the shadow's reach to keep the card at all, and the
    silhouette it casts from lies wholly outside the strip. The strip has to
    come out as the same rows of a render that includes the card.
    """
    psd, layer = _masks_card()
    left, top, right, bottom = layer.bbox
    strip = (left, bottom + 4, right, bottom + 24)
    assert utils.intersect(strip, layer.bbox) == (0, 0, 0, 0)
    assert utils.intersect(strip, _effect_reach(layer)) != (0, 0, 0, 0)

    alpha = _alone(layer, strip)
    wide = _alone(layer, (left, top, right, bottom + 24))
    assert float(alpha.max()) > 0.01, "the strip lost the shadow"
    assert np.allclose(alpha, wide[bottom + 4 - top :], atol=1e-6)


def test_a_group_canvas_makes_room_for_a_child_shadow() -> None:
    """A group's content box counts the shadows its children cast.

    It is the canvas an isolated group composites its children on (#808).
    ``masks.psb``'s header band casts a 100 px shadow past the group that
    holds it, which the group's own box, a union of its children's boxes,
    does not reach.
    """
    psd = PSDImage.open(full_name("masks.psb"))
    header = next(layer for layer in psd if layer.name == "Header")
    band = next(layer for layer in psd.descendants() if layer.name == "Rectangle 2")
    assert band.parent is header
    reach = _shadow_reach(band)
    assert reach[3] > header.bbox[3]
    assert _content_bbox(header)[3] >= reach[3]


def _header(blend_mode: BlendMode) -> tuple[Layer, Layer]:
    """``masks.psb``'s header group, and the band inside it."""
    psd = PSDImage.open(full_name("masks.psb"))
    header = next(layer for layer in psd if layer.name == "Header")
    header.blend_mode = blend_mode
    band = next(layer for layer in psd.descendants() if layer.name == "Rectangle 2")
    return header, band


@pytest.mark.parametrize("blend_mode", [BlendMode.PASS_THROUGH, BlendMode.NORMAL])
def test_a_group_casts_its_shadow_from_its_childrens_effects_too(
    blend_mode: BlendMode,
) -> None:
    """A group's shadow is drawn on a canvas that holds its whole silhouette.

    The band's own shadow, made hard and cast 40 px down, runs past the
    group's box, which is a union of its children's own boxes. The group's
    shadow, cast 20 px further, has to reach 20 px past the band's; grown
    from the group's box alone, the silhouette was cut off before that and
    the group's shadow with it (#679 review).
    """
    header, band = _header(blend_mode)
    band_shadow = _shadow_descriptor(band)
    for key, value in ((Key.Blur, 0.0), (Key.Distance, 40.0), (Key.Opacity, 100.0)):
        band_shadow[key] = Double(value)
    viewport = (0, 0, 640, 200)
    # The band ends at 102 and its shadow at 142, so 150 is the group's alone.
    y, x = 150, 320
    assert float(_alone(header, viewport)[y, x, 0]) == 0.0

    _forge_shadow(header, Blur=0.0, Distance=20.0, Opacity=100.0)
    assert float(_alone(header, viewport)[y, x, 0]) == pytest.approx(1.0)


def test_a_pass_through_group_keeps_its_shadow_beneath_it() -> None:
    """The shadow of a pass-through group does not paint over the group.

    A pass-through group is composited before what goes on beside it, which
    would put its shadow over it; the shadow goes on before the group is
    resolved instead, and the group is resolved over it. With the knockout
    off, the band's middle has to come out as it does with no group shadow at
    all, and below the band the shadow has to be there (#679 review).
    """

    def render(with_shadow: bool) -> np.ndarray:
        header, _ = _header(BlendMode.PASS_THROUGH)
        if with_shadow:
            shadow = _forge_shadow(header, Blur=10.0, Distance=30.0, Opacity=100.0)
            shadow[b"layerConceals"] = False
        viewport = (0, 0, 640, 260)
        height, width = viewport[3], viewport[2]
        compositor = Compositor(
            viewport,
            np.ones((height, width, 3), dtype=np.float32),
            np.ones((height, width, 1), dtype=np.float32),
        )
        compositor.apply(header)
        return compositor.result_over_backdrop()

    shadowed, plain = render(True), render(False)
    assert np.allclose(shadowed[50, 320], plain[50, 320], atol=1e-6)
    assert not np.allclose(shadowed[120, 320], plain[120, 320], atol=1e-2)


# The social icons in ``masks.psb``'s footer: a pass-through group of four
# shape layers, each at layer opacity 102.
_SOCIAL_VIEWPORT = (150, 960, 490, 1100)


def _social(blend_mode: BlendMode) -> Group:
    psd = PSDImage.open(full_name("masks.psb"))
    social = next(layer for layer in psd.descendants() if layer.name == "Social")
    social.blend_mode = blend_mode
    return cast(Group, social)


def _composited(
    group: Layer, viewport: tuple[int, int, int, int] = _SOCIAL_VIEWPORT
) -> np.ndarray:
    """``group`` over an opaque white backdrop, colour and alpha together."""
    height, width = viewport[3] - viewport[1], viewport[2] - viewport[0]
    compositor = Compositor(
        viewport,
        np.ones((height, width, 3), dtype=np.float32),
        np.ones((height, width, 1), dtype=np.float32),
    )
    compositor.apply(group)
    color, _, alpha = compositor.finish()
    return np.concatenate((compositor.result_over_backdrop(), alpha), axis=2)


def test_a_pass_through_group_casts_the_shadow_a_normal_one_does() -> None:
    """Over contents that blend normally, pass-through changes nothing.

    The icons are 40% opaque, so their shadow shows through them wherever it
    lies under them. Held back from what the group covers after the fact, it
    came out at ``a + s * (1 - a) ** 2`` there rather than ``a + s * (1 - a)``,
    and over the icons' colour rather than under it (#679 review).
    """
    rendered = []
    for blend_mode in (BlendMode.PASS_THROUGH, BlendMode.NORMAL):
        social = _social(blend_mode)
        shadow = _forge_shadow(social, Blur=3.0, Distance=4.0, Opacity=100.0)
        shadow[b"layerConceals"] = False
        rendered.append(_composited(social))
    passthrough, normal = rendered
    assert not np.allclose(passthrough, _composited(_social(BlendMode.NORMAL)))
    assert np.allclose(passthrough, normal, atol=1e-5)


def test_a_faded_pass_through_group_is_resolved_over_its_shadow() -> None:
    """A pass-through group's contents blend with its shadow under them.

    At fill 128 the group is not re-applied by interpolation, but its
    contents are still resolved over the canvas beneath it, which has to
    hold the shadow by then. The icons are white and set to Multiply, so
    over their own shadow they change nothing, and what is left at an icon
    is the shadow alone: 40% black over white. Resolved before the shadow
    went on, their white came back over it at 0.68 (#679 review).
    """
    social = _social(BlendMode.PASS_THROUGH)
    social.tagged_blocks.set_data(Tag.BLEND_FILL_OPACITY, ByteElement(128))
    for icon in social:
        icon.blend_mode = BlendMode.MULTIPLY
    shadow = _forge_shadow(social, Blur=0.0, Distance=0.0, Opacity=100.0)
    shadow[b"layerConceals"] = False
    contents = _alone(_social(BlendMode.PASS_THROUGH), _SOCIAL_VIEWPORT)[:, :, 0]
    rendered = _composited(social)

    icons = np.argwhere(np.isclose(contents, 102 / 255.0, atol=1e-6))
    assert len(icons), "no fully covered icon pixel"
    y, x = icons[len(icons) // 2]
    assert np.allclose(rendered[y, x, :3], 1.0 - 102 / 255.0, atol=1e-5)


@pytest.mark.parametrize("knockout", [1, 2], ids=["shallow", "deep"])
def test_a_group_shadow_does_not_depend_on_the_viewport(knockout: int) -> None:
    """The silhouette is read the same way whatever the viewport holds.

    One icon knocks out at fill 0. Resolved over the canvas, a knockout
    takes alpha from the backdrop it reaches, so a silhouette read off the
    resolved group cast a shadow from the knocked-out icon in a full render
    and none in a render of the shadow alone (#679 review). Read afresh over
    nothing, the strip below the icons comes out the same in both.
    """
    social = _social(BlendMode.PASS_THROUGH)
    icon = next(layer for layer in social if layer.name == "facebook")
    icon.tagged_blocks.set_data(Tag.KNOCKOUT_SETTING, ByteElement(knockout))
    icon.tagged_blocks.set_data(Tag.BLEND_FILL_OPACITY, ByteElement(0))
    _forge_shadow(social, Blur=0.0, Distance=60.0, Opacity=100.0)
    full = _composited(social)
    left, top, right, bottom = _SOCIAL_VIEWPORT
    strip = (left, 1030, right, bottom)
    assert np.allclose(_composited(social, strip), full[1030 - top :], atol=1e-6)


def test_nested_shadowed_groups_are_resolved_once_each() -> None:
    """Shadows on nested groups cost linearly in the nesting, not exponentially.

    A group's silhouette is its contents composited over nothing, once per
    box and pass, so the one layer at the bottom of eight groups that each
    cast a shadow is resolved once for the render and once for each group's
    silhouette. Resolving a pass-through group again over its own shadow
    did it 2 ** 8 times (#679 review).
    """
    psd = PSDImage.new("RGB", (80, 80))
    leaf = psd.create_pixel_layer(
        Image.new("RGBA", (20, 20), (255, 255, 255, 255)), top=30, left=30
    )
    node: Layer = leaf
    for depth in range(8):
        node = psd.create_group([node], name="Group %d" % depth)
        _forge_shadow(node, Blur=0.0, Distance=3.0, Opacity=100.0)

    resolved = 0
    resolve = Compositor._resolve_source

    def counting(compositor: Compositor, layer: Layer) -> Any:
        nonlocal resolved
        resolved += layer is leaf
        return resolve(compositor, layer)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Compositor, "_resolve_source", counting)
        _alone(node, psd.viewbox)
    assert resolved == 8 + 1


@pytest.mark.parametrize("blend_mode", [BlendMode.PASS_THROUGH, BlendMode.NORMAL])
def test_a_group_casts_its_shadow_from_how_opaque_its_contents_are(
    blend_mode: BlendMode,
) -> None:
    """A group's silhouette is its contents' alpha, not their coverage.

    The icons cover their pixels fully at 40% opacity, so their hard shadow,
    cast clear of them, is 40% opaque too, and an icon faded to nothing
    casts nothing. Read off coverage, every icon cast an opaque shadow,
    the invisible one included (#679 review).
    """
    social = _social(blend_mode)
    faded = next(layer for layer in social if layer.name == "facebook")
    faded.opacity = 0
    viewport = _SOCIAL_VIEWPORT
    contents = _alone(social, viewport)[:, :, 0]
    _forge_shadow(social, Blur=0.0, Distance=60.0, Opacity=100.0)
    alpha = _alone(social, viewport)[:, :, 0]

    icons = np.argwhere(np.isclose(contents, 102 / 255.0, atol=1e-6))
    assert len(icons), "no fully covered icon pixel"
    for y, x in icons[:: max(1, len(icons) // 50)]:
        assert float(alpha[y + 60, x]) == pytest.approx(102 / 255.0, abs=1e-5)
    # Under where the faded icon would have cast its shadow.
    left, top, right, bottom = faded.bbox
    below = alpha[
        top + 60 - viewport[1] : bottom + 60 - viewport[1],
        left - viewport[0] : right - viewport[0],
    ]
    assert float(below.max()) == 0.0


@pytest.mark.parametrize("force", [False, True])
def test_a_masked_pixel_layer_casts_its_shadow_from_its_pixels(force: bool) -> None:
    """The silhouette is what the layer covers, not the outline of its mask.

    ``masks/2.psd``'s third ellipse is a pixel layer under a vector mask that
    spans the whole canvas. A stroke traces that mask under ``force``, and so
    did the shadow: it was cast from the whole canvas and then knocked out
    under all of it, leaving nothing (#679 review). Both force modes cover
    the same pixels, so they have to cast the same shadow.
    """
    psd = PSDImage.open(full_name("masks/2.psd"))
    layer = next(layer for layer in psd if layer.name == "ellipse3")
    assert layer.bbox == (8, 16, 56, 64)
    # Lit from the right, so the shadow falls 6 px to the left.
    _forge_shadow(layer, angle=0.0, Blur=0.0, Distance=6.0, Opacity=100.0)
    alpha = _alone(layer, psd.viewbox, force=force)
    reference = _alone(layer, psd.viewbox)
    assert np.allclose(alpha, reference, atol=1e-6)
    # Left of the ellipse, where only its shadow can be: opaque, faded by the
    # layer's own opacity.
    assert float(alpha[40, 4, 0]) == pytest.approx(layer.opacity / 255.0)


def _setting(key: bytes, value: Any) -> Callable[[Descriptor], Any]:
    return lambda desc: desc.__setitem__(key, value)


# Ways a drop shadow's descriptor can defeat the reads that draw it: a number
# that will not parse, one that parses to something no arithmetic survives,
# and a colour that cannot be read. NaN and infinity raise nowhere on their
# own, and let through they took every pixel of the render with them.
_UNDRAWABLE: dict[str, Callable[[Descriptor], Any]] = {
    "size": _setting(Key.Blur, "wide"),
    "infinite-size": _setting(Key.Blur, Double(float("inf"))),
    "infinite-distance": _setting(Key.Distance, Double(float("inf"))),
    "nan-angle": _setting(Key.LocalLightingAngle, Double(float("nan"))),
    "nan-spread": _setting(Key.ChokeMatte, Double(float("nan"))),
    "nan-opacity": _setting(Key.Opacity, Double(float("nan"))),
    "infinite-opacity": _setting(Key.Opacity, Double(float("inf"))),
    "no-color": lambda desc: desc.pop(Key.Color),
    "color-class": lambda desc: setattr(desc[Key.Color], "classID", b"XXXX"),
}


def _rendered(mutate: Callable[[Descriptor], Any]) -> np.ndarray:
    psd = PSDImage.open(full_name("layer_comps.psb"))
    for layer in psd.descendants():
        for effect in list(layer.effects.find("dropshadow")):
            mutate(effect.descriptor)
    color, _, alpha = composite(psd)
    return np.concatenate((color, alpha), axis=2)


@pytest.mark.parametrize("defect", sorted(_UNDRAWABLE))
def test_an_unreadable_drop_shadow_is_dropped_and_the_document_renders(
    defect: str,
) -> None:
    """A descriptor that cannot be read costs its shadow, not the render.

    Asserted against the same document with the shadow switched off, so a
    shadow drawn at some invented size or colour would not pass. The angle
    is read off the descriptor only where the shadow does not use the global
    light, which ``layer_comps.psb``'s do not.
    """
    disabled = _rendered(_setting(Key.Enabled, False))
    assert not np.array_equal(_rendered(lambda desc: None), disabled)
    rendered = _rendered(_UNDRAWABLE[defect])
    assert np.isfinite(rendered).all()
    assert np.array_equal(rendered, disabled)


# -- Fidelity against Photoshop's own render ------------------------------- #

# Each case is a document, the region around its drop shadows (None for the
# whole document), the bound the render is held to, and a floor under the
# error of the same render with the shadows switched off -- which is what
# shows the region is measuring a shadow at all. Measured with the
# ``force=False`` render these tests make:
#
# - layer_effects.psd: 4.3e-6 against 1.4e-3 without. The region stops short
#   of the layer below, whose inner shadow is not drawn.
# - masks.psb, the whole document: 1.3e-5 against 1.8e-4 without.
# - layer_params.psb: 5.2e-3 against 2.7e-2 without. What is left is the
#   outer glow on the same layer, which is not drawn; the bound is what pins
#   spread, since leaving spread out scores 6.6e-3 and shrinking the
#   silhouette by it, as #679 first did, 9.2e-3.
# - layer_comps.psb, the whole document: 4.5e-3 against 6.7e-3 without,
#   the rest being a bevel that is not drawn.
_PREVIEWS = [
    ("layer_effects.psd", (60, 215, 620, 296), 1e-5, 1e-3),
    ("masks.psb", None, 3e-5, 1.5e-4),
    ("layer_params.psb", (130, 230, 470, 560), 5.6e-3, 2e-2),
    ("layer_comps.psb", None, 4.8e-3, 6e-3),
]


def _error(
    psd: PSDImage, region: tuple[int, int, int, int] | None, force: bool = False
) -> float:
    reference = psd.numpy()
    color, _, alpha = composite(psd, force=force)
    result = color
    if reference.shape[2] > color.shape[2]:
        result = np.concatenate((color, alpha), axis=2)
    if region is not None:
        left, top, right, bottom = region
        reference = reference[top:bottom, left:right]
        result = result[top:bottom, left:right]
    return float(_mse(reference, result))


@pytest.mark.parametrize(
    ("filename", "region", "bound", "without"),
    _PREVIEWS,
    ids=[case[0] for case in _PREVIEWS],
)
def test_drop_shadows_render_to_photoshops_preview(
    filename: str,
    region: tuple[int, int, int, int] | None,
    bound: float,
    without: float,
) -> None:
    """Every drop shadow in the corpus, against Photoshop's own render of it."""
    psd = PSDImage.open(full_name(filename))
    error = _error(psd, region)

    unshadowed = PSDImage.open(full_name(filename))
    for layer in unshadowed.descendants():
        for effect in list(layer.effects.find("dropshadow")):
            effect.descriptor[Key.Enabled] = False
    assert _error(unshadowed, region) >= without, "the region has no shadow"
    assert error <= bound


def test_drop_shadows_render_to_photoshops_preview_when_forced() -> None:
    """``force=True`` redraws masks.psb's cards from their paths: 1.6e-5."""
    assert _error(PSDImage.open(full_name("masks.psb")), None, force=True) <= 3e-5
