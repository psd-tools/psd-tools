import logging
from typing import Callable

import numpy as np
import pytest
from PIL import Image

from psd_tools import PSDImage
from psd_tools.api.layers import GroupMixin, PixelLayer
from psd_tools.api.utils import EXPECTED_CHANNELS, color_channels
from psd_tools.composite.blend import (
    BLEND_FUNC,
    color,
    color_dodge,
    darker_color,
    get_blend_func,
    hue,
    lighter_color,
    luminosity,
    multiply,
    normal,
    saturation,
)
import psd_tools.composite.blend as blend_module
from psd_tools.constants import BlendMode, ColorMode
from psd_tools.terminology import Enum
from .test_composite import check_composite_quality

logger = logging.getLogger(__name__)


def test_lighter_color_descriptor_key() -> None:
    """Regression: b"lighterColor" was previously a typo (b"ligherColor")
    which silently fell back to the normal blend mode for effects/strokes."""
    assert BLEND_FUNC.get(b"lighterColor") is lighter_color
    assert BLEND_FUNC.get(b"lighterColor") is not normal


@pytest.mark.parametrize(
    ("filename",),
    [
        ("blend-modes/normal.psd",),
        ("blend-modes/multiply.psd",),
        ("blend-modes/screen.psd",),
        ("blend-modes/overlay.psd",),
        ("blend-modes/darken.psd",),
        ("blend-modes/lighten.psd",),
        ("blend-modes/color-dodge.psd",),
        ("blend-modes/linear-dodge.psd",),
        ("blend-modes/color-burn.psd",),
        ("blend-modes/linear-burn.psd",),
        ("blend-modes/hard-light.psd",),
        ("blend-modes/soft-light.psd",),
        # Was xfailed as a "vivid light algorithm discrepency" until #189: the
        # mode delegated to the guarded color_burn/color_dodge, whose backdrop
        # special cases Photoshop does not apply here. 0.020755 -> 0.000001.
        ("blend-modes/vivid-light.psd",),
        ("blend-modes/linear-light.psd",),
        ("blend-modes/pin-light.psd",),
        ("blend-modes/difference.psd",),
        ("blend-modes/exclusion.psd",),
        ("blend-modes/subtract.psd",),
        ("blend-modes/hard-mix.psd",),
        ("blend-modes/saturation.psd",),
        ("blend-modes/divide.psd",),
        ("blend-modes/hue.psd",),
        ("blend-modes/color.psd",),
        ("blend-modes/luminosity.psd",),
        ("blend-modes/pass-through.psd",),
        # Total test
        ("blend-modes/rgb-blend-modes.psd",),
        ("blend-modes/gray-blend-modes.psd",),
        # Was xfailed as "# Fix me!" until #781: the six non-separable modes
        # went through a CMYK round trip that read the canvas as ink where it
        # holds what is left of it, and the whole document's error sat at
        # 0.026612 against this 0.01 threshold. It is 0.000179 now.
        ("blend-modes/cmyk-blend-modes.psd",),
    ],
)
def test_blend_quality(filename: str) -> None:
    check_composite_quality(filename, threshold=0.01)


@pytest.mark.parametrize(
    ("filename",),
    [
        ("blend-modes/dissolve.psd",),
    ],
)
@pytest.mark.xfail
def test_blend_quality_xfail(filename: str) -> None:
    check_composite_quality(filename, threshold=0.01)


@pytest.mark.parametrize(
    "property",
    [
        ("opacity"),
        ("fill_adjustment"),
        ("fill_blendmode"),
        ("clipping_mask_adjustment"),
        ("clipping_mask_blendmode"),
        ("vector_mask"),
        ("blendmodes1"),
        ("blendmodes2"),
        ("blendmodes3"),
    ],
)
def test_passthrough_properties(property) -> None:
    filename = f"passthrough_{property}"
    check_composite_quality(f"{filename}.psd", 0.001, False)


def _nested_passthrough_psd_with(
    depth: int, opacity: int, layer_alpha: int, background_alpha: int
) -> PSDImage:
    """Build ``depth`` nested pass-through groups holding a single blue layer.

    Only the innermost group carries ``opacity``; the outer ones are opaque, so
    the rendered result must not depend on ``depth``.
    """
    psd = PSDImage.new(mode="RGB", size=(8, 8))
    if background_alpha:
        psd.create_pixel_layer(
            image=Image.new("RGBA", (8, 8), (255, 0, 0, background_alpha)),
            name="Background",
        )

    parent: GroupMixin = psd
    for i in range(depth):
        group = psd.create_group(name=f"Group {i}")
        group.blend_mode = BlendMode.PASS_THROUGH
        group.opacity = opacity if i == depth - 1 else 255
        if parent is not psd:
            psd.remove(group)
            parent.append(group)
        parent = group

    blue = PixelLayer.frompil(Image.new("RGBA", (8, 8), (0, 0, 255, layer_alpha)), psd)
    blue.name = "Blue"
    parent.append(blue)
    return psd


def _nested_passthrough_psd(depth: int, opacity: int, background: bool) -> PSDImage:
    return _nested_passthrough_psd_with(
        depth, opacity, layer_alpha=128, background_alpha=255 if background else 0
    )


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_passthrough_group_opacity_over_opaque_backdrop(depth: int) -> None:
    """Group opacity must scale the effective alpha of the group's contents
    instead of blending the backdrop in twice (issue #703)."""
    psd = _nested_passthrough_psd(depth, opacity=128, background=True)
    image = psd.composite(ignore_preview=True).convert("RGB")
    pixel = tuple(np.array(image, dtype=int)[4, 4])
    # 50% layer alpha * 50% group opacity = 25% blue over red.
    assert pixel == pytest.approx((191, 0, 64), abs=2)


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_passthrough_group_opacity_over_transparent_backdrop(depth: int) -> None:
    """Without a backdrop, group opacity only scales alpha; the initial
    backdrop color must not bleed into the result (issue #703)."""
    psd = _nested_passthrough_psd(depth, opacity=128, background=False)
    image = psd.composite(ignore_preview=True).convert("RGBA")
    pixel = tuple(np.array(image, dtype=int)[4, 4])
    assert pixel == pytest.approx((0, 0, 255, 64), abs=2)


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_passthrough_group_opacity_over_partial_backdrop(depth: int) -> None:
    """The interpolation has to happen in premultiplied space, so a partially
    transparent backdrop contributes in proportion to its own alpha.

    This is the case the pre-#703 code got wrong even without nesting, because
    it keyed off ``_shape_g`` rather than the backdrop alpha.
    """
    psd = _nested_passthrough_psd_with(
        depth, opacity=128, layer_alpha=128, background_alpha=128
    )
    image = psd.composite(ignore_preview=True).convert("RGBA")
    pixel = tuple(np.array(image, dtype=int)[4, 4])
    # backdrop 0.5 red, group result 0.25 blue over it, group opacity 0.5:
    #   alpha = union(0.5, 0.5 * 0.5)   = 0.625  -> 159
    #   color = (0.375 * red + 0.25 * blue) / 0.625 = 0.6 red + 0.4 blue
    assert pixel == pytest.approx((153, 0, 102, 159), abs=2)


def _flat_psd(alpha: int, background_alpha: int) -> PSDImage:
    """The ungrouped counterpart of :py:func:`_nested_passthrough_psd`."""
    psd = PSDImage.new(mode="RGB", size=(8, 8))
    if background_alpha:
        psd.create_pixel_layer(
            image=Image.new("RGBA", (8, 8), (255, 0, 0, background_alpha)), name="BG"
        )
    psd.append(PixelLayer.frompil(Image.new("RGBA", (8, 8), (0, 0, 255, alpha)), psd))
    return psd


@pytest.mark.parametrize("depth", [1, 2, 3])
@pytest.mark.parametrize("opacity", [255, 192, 128, 64, 0])
@pytest.mark.parametrize("layer_alpha", [255, 128, 64])
@pytest.mark.parametrize("background_alpha", [255, 128, 0])
def test_passthrough_group_opacity_equivalence(
    depth: int, opacity: int, layer_alpha: int, background_alpha: int
) -> None:
    """A pass-through group at opacity ``m`` around a single normal layer at
    alpha ``a`` must render identically to that layer ungrouped at ``m * a``.

    This is the invariant issue #703 violated: group opacity has to scale the
    effective alpha of the contents rather than blend the backdrop in twice.
    """
    grouped = _nested_passthrough_psd_with(
        depth, opacity, layer_alpha, background_alpha
    )
    flat = _flat_psd(round(opacity * layer_alpha / 255.0), background_alpha)

    got = np.array(grouped.composite(ignore_preview=True).convert("RGBA"), dtype=int)
    ref = np.array(flat.composite(ignore_preview=True).convert("RGBA"), dtype=int)
    if got[4, 4, 3] == 0 and ref[4, 4, 3] == 0:
        return  # Fully transparent; the color channels are undefined.
    assert tuple(got[4, 4]) == pytest.approx(tuple(ref[4, 4]), abs=2)


NON_SEPARABLE = [hue, saturation, color, luminosity, darker_color, lighter_color]


@pytest.mark.parametrize("func", NON_SEPARABLE, ids=lambda f: f.__name__)
@pytest.mark.parametrize("channels", [1, 2, 5])
def test_non_separable_falls_back_to_normal_off_rgb(
    func: Callable, channels: int
) -> None:
    """Widths other than RGB and CMYK degrade instead of crashing (#735).

    The four component modes raised on any single-channel document -- every
    grayscale and duotone fixture that has layers::

        hue, saturation:    IndexError: boolean index did not match indexed
                            array along axis 2
        color, luminosity:  ValueError: zero-size array to reduction operation
                            minimum which has no identity

    ``darker_color`` and ``lighter_color`` did not raise, which was worse: the
    empty mask they built selected nothing, so both returned the backdrop
    untouched whatever the source was. Two and five channels -- a duotone canvas
    widened to its inks, a multichannel document with spot plates -- are broken
    too, differing only in which exception comes out and in that five channels
    raises for all six rather than silently passing the backdrop through. So
    the fallback keys on "not RGB" rather than on "single channel".

    ``normal`` is the fallback because Photoshop refuses to set any of these
    six modes on such a document, so there is no result to reproduce.

    Since #746 the width is no longer the whole rule: a multichannel document
    returns before this branch when its mode is known, at three and four plates
    as well as at the widths here. These cases carry no mode, so they still
    reach the width fallback and pin it as #735 left it.
    """
    Cb = np.full((2, 2, channels), 0.4, dtype=np.float32)
    Cs = np.full((2, 2, channels), 0.6, dtype=np.float32)
    result = func(Cb, Cs)
    assert result.shape == (2, 2, channels)
    assert np.array_equal(result, normal(Cb, Cs))


def _mixed_pair(channels: int) -> tuple[np.ndarray, np.ndarray]:
    """A backdrop and a source that no single operand can be mistaken for.

    The source is brighter than the backdrop in one pixel and darker in the
    other. A spatially constant pair would not do: ``darker_color`` and
    ``lighter_color`` return one whole operand, so on constant input one of the
    two always coincides with ``normal`` and a comparison could not tell a real
    blend from the fallback.
    """
    Cb = np.full((1, 2, channels), 0.4, dtype=np.float32)
    Cs = np.full((1, 2, channels), 0.6, dtype=np.float32)
    Cs[0, 0, 0] = 0.9
    Cs[0, 1, :] = 0.1
    return Cb, Cs


@pytest.mark.parametrize("func", NON_SEPARABLE, ids=lambda f: f.__name__)
@pytest.mark.parametrize(
    ("color_mode", "channels"),
    [
        (None, 3),
        (None, 4),
        (ColorMode.RGB, 3),
        (ColorMode.INDEXED, 3),
        (ColorMode.LAB, 3),
        (ColorMode.CMYK, 4),
    ],
)
def test_non_separable_still_blends_the_modes_with_ground_truth(
    func: Callable,
    color_mode: ColorMode | None,
    channels: int,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The fallbacks must not swallow the cases that do have ground truth.

    Photoshop offers all six on an RGB, a Lab and a CMYK document, so those
    three keep blending -- the three-channel ones directly, CMYK on its CMY
    complement with K carried across. So does an array with no mode attached,
    which is what a bare ``Compositor`` or a direct call hands over: there the
    width decides alone, as it did before #746.

    Indexed rides along on width rather than on ground truth. Photoshop
    flattens on conversion to Indexed Color, the same argument that keeps
    multichannel out, so there is no layer to set a blend mode on; what the row
    pins is that the mode-keyed branch singles out multichannel and leaves
    every other three-channel canvas on the RGB path.

    What the CMYK row is worth is settled separately, by
    ``test_non_separable_matches_photoshop_on_cmyk`` below: since #781 the
    result is Photoshop's to within one 8-bit step, where this row only asks
    that some blending happened at all.
    """
    Cb, Cs = _mixed_pair(channels)
    with caplog.at_level(logging.DEBUG, logger="psd_tools.composite.blend"):
        result = func(Cb.copy(), Cs.copy(), color_mode)
    assert result.shape == (1, 2, channels)
    assert not np.array_equal(result, normal(Cb, Cs))
    assert "falling back to normal" not in caplog.text


def test_non_separable_fallback_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Degrading silently would hide a mode the caller asked for (#735)."""
    Cb = np.full((2, 2, 1), 0.4, dtype=np.float32)
    Cs = np.full((2, 2, 1), 0.6, dtype=np.float32)
    with caplog.at_level(logging.DEBUG, logger="psd_tools.composite.blend"):
        luminosity(Cb, Cs)
    assert "luminosity blend is not defined for a 1-channel source" in caplog.text


@pytest.mark.parametrize("func", NON_SEPARABLE, ids=lambda f: f.__name__)
@pytest.mark.parametrize("channels", [1, 2, 3, 4, 5])
def test_non_separable_falls_back_on_a_multichannel_document(
    func: Callable, channels: int, caplog: pytest.LogCaptureFixture
) -> None:
    """A spot plate is not a colour component, at any plate count (#746).

    #745 keyed the fallback on the width, which left two plate counts blending:
    four were claimed as CMYK and the fourth ink blended as black generation,
    and three went into the RGB helpers as if the plates were R, G and B. Both
    were silently wrong rather than an error, and three is the count the only
    multichannel fixture in the corpus has.

    The assertion on the message is what makes this discriminate. At one, two
    and five channels the width fallback #745 added returns ``normal`` too, so
    the equality alone would pass there with this fix reverted; and for three
    and four the width is the wrong diagnosis to log.
    """
    Cb, Cs = _mixed_pair(channels)
    with caplog.at_level(logging.DEBUG, logger="psd_tools.composite.blend"):
        result = func(Cb.copy(), Cs.copy(), ColorMode.MULTICHANNEL)
    assert result.shape == (1, 2, channels)
    assert np.array_equal(result, normal(Cb, Cs))
    assert (
        "%s blend is not defined on a multichannel document" % func.__name__
        in caplog.text
    )


def test_only_cmyk_is_four_channels_wide() -> None:
    """The premise the ``Cs.shape[2] == 4`` branch reads as CMYK (#746).

    Multichannel returns before that branch, so what makes its remaining
    reading of a four-channel array sound is that no other mode can produce
    one: :py:data:`EXPECTED_CHANNELS` fixes every mode but multichannel, whose
    entry is the format maximum and whose count the header supplies. Pinned
    here so that a change to the table -- indexed expanding to four
    post-palette, say -- fails as a test rather than as an unrelated mode
    blended as ink.
    """
    assert {m for m in ColorMode if EXPECTED_CHANNELS[m] == 4} == {ColorMode.CMYK}
    assert EXPECTED_CHANNELS[ColorMode.MULTICHANNEL] == 64
    assert color_channels(ColorMode.MULTICHANNEL, 4) == 4


@pytest.mark.parametrize("func", NON_SEPARABLE, ids=lambda f: f.__name__)
def test_non_separable_defaults_to_deciding_by_width(func: Callable) -> None:
    """Called with two arguments, these behave as they did before #746.

    Every other case passes a mode explicitly, including the ``None`` rows, so
    without this the *default* would be untested -- and a default of, say,
    ``ColorMode.MULTICHANNEL`` would degrade every direct caller to ``normal``
    while the whole suite stayed green.
    """
    Cb, Cs = _mixed_pair(4)
    assert np.array_equal(func(Cb.copy(), Cs.copy()), func(Cb.copy(), Cs.copy(), None))
    assert not np.array_equal(func(Cb.copy(), Cs.copy()), normal(Cb, Cs))


# Photoshop 2026's own answers, in ink percent, authored in its default CMYK
# working space -- U.S. Web Coated (SWOP) v2. The space is provenance, not a
# parameter: nothing in the model these pin consults a profile, so a document
# saved in another working space blends by the same arithmetic. Format:
# ``(backdrop, source, {mode: result})``. Authored by scripting Photoshop --
# fill a Background, add a layer, set ``blendMode``, flatten, and read the pixel
# back through ``doc.colorSamplers`` -- so these are its render and not a
# derivation. The pairs are off the neutral axis and differ in every channel;
# pair 3's near-neutral backdrop and pair 5's paper white are the two that
# discriminate hardest (see the test below).
PHOTOSHOP_CMYK: list[tuple[list[float], list[float], dict[str, list[float]]]] = [
    (
        [80, 20, 10, 5],
        [10, 70, 60, 20],
        {
            "hue": [0, 53.73, 45.1, 5.1],
            "saturation": [73.73, 22.35, 13.73, 5.1],
            "color": [0, 53.73, 45.1, 5.1],
            "luminosity": [93.73, 33.73, 23.53, 20],
            "darker_color": [9.8, 69.8, 60, 20],
            "lighter_color": [80, 20, 9.8, 5.1],
        },
    ),
    (
        [10, 70, 60, 20],
        [80, 20, 10, 5],
        {
            "hue": [87.45, 36.08, 27.45, 20],
            "saturation": [2.75, 72.94, 61.57, 20],
            "color": [93.73, 33.73, 23.53, 20],
            "luminosity": [0, 53.73, 45.1, 5.1],
            "darker_color": [9.8, 69.8, 60, 20],
            "lighter_color": [80, 20, 9.8, 5.1],
        },
    ),
    (
        [5, 5, 90, 0],
        [70, 60, 0, 10],
        {
            "hue": [17.65, 14.9, 0, 0],
            "saturation": [6.67, 6.67, 76.47, 0],
            "color": [17.65, 14.9, 0, 0],
            "luminosity": [50.98, 50.98, 99.61, 9.8],
            "darker_color": [69.8, 60, 0, 9.8],
            "lighter_color": [5.1, 5.1, 89.8, 0],
        },
    ),
    (
        [40, 40, 40, 40],
        [0, 90, 30, 0],
        {
            "hue": [40, 40, 40, 40],
            "saturation": [40, 40, 40, 40],
            "color": [0, 63.53, 21.18, 40],
            "luminosity": [56.08, 56.08, 56.08, 0],
            "darker_color": [40, 40, 40, 40],
            "lighter_color": [0, 89.8, 29.8, 0],
        },
    ),
    (
        [95, 0, 30, 60],
        [20, 15, 85, 2],
        {
            "hue": [27.06, 21.18, 99.61, 60],
            "saturation": [78.43, 8.24, 30.2, 60],
            "color": [27.45, 22.35, 92.55, 60],
            "luminosity": [72.16, 0, 22.75, 1.96],
            "darker_color": [94.9, 0, 29.8, 60],
            "lighter_color": [20, 14.9, 85.1, 1.96],
        },
    ),
    (
        [0, 0, 0, 0],
        [50, 40, 30, 10],
        {
            "hue": [0, 0, 0, 0],
            "saturation": [0, 0, 0, 0],
            "color": [0, 0, 0, 0],
            "luminosity": [41.96, 41.96, 41.96, 9.8],
            "darker_color": [49.8, 40, 29.8, 9.8],
            "lighter_color": [0, 0, 0, 0],
        },
    ),
]

# One 8-bit step is 1/255, and Photoshop reports through an 8-bit sampler, so
# the floor here is quantization and not model error: the worst of the 36 rows
# is 1.20 steps and none exceeds one and a quarter. Two steps leaves the
# assertion loose enough to be stable and tight enough to fail loudly -- every
# defect #781 fixed moves at least one of these rows by 25 to 148 steps. The
# separable table further down shares this tolerance on the same reasoning; its
# own worst row is 1.13 steps, and the defects #189 fixed move rows by 6 to 255.
_ONE_STEP = 1.0 / 255.0


def _cmyk_canvas(ink: list[float]) -> np.ndarray:
    """Ink percent as the compositor holds it: a canvas counts what is left."""
    return (1.0 - np.array(ink, dtype=np.float32) / 100.0).reshape(1, 1, 4)


@pytest.mark.parametrize("mode", [f.__name__ for f in NON_SEPARABLE])
@pytest.mark.parametrize("pair", range(len(PHOTOSHOP_CMYK)), ids=lambda i: "pair%d" % i)
def test_non_separable_matches_photoshop_on_cmyk(pair: int, mode: str) -> None:
    """The whole of what #781 fixed, against Photoshop's own render.

    Three separate defects lived in the four-channel branch, and the corpus
    fixture ``blend-modes/cmyk-blend-modes.psd`` catches only the first even
    though it exercises all six modes:

    1. The round trip. ``_cmyk2rgb`` computed ``(1 - C) * (1 - K)``, reading the
       canvas as ink where it holds what is left of it, so all six collapsed to
       a constant and ``color(Cb, Cb)`` was not ``Cb``. There is no round trip
       now: Photoshop blends the CMY complement directly, which is what the
       canvas already holds, and no formula that converts to RGB first came
       within 6/255 of these numbers.
    2. Which operand supplies K -- the backdrop's for hue, saturation and
       color, the source's for luminosity. The code took the source's for all
       four. Reverting that alone still passes the fixture, and moves pair 4 by
       148/255 here.
    3. Darker and Lighter Color return an operand *whole*, K included, and
       weigh K when deciding which is darker. Reverting either half still passes
       the fixture; dropping K from the comparison changes no pixel in it at
       all, while pair 3 -- a near-neutral backdrop against a saturated source
       -- moves by 127.5/255.

    So this table is not redundant with the fixture; for two of the three it is
    the only thing standing.
    """
    backdrop, source, expected = PHOTOSHOP_CMYK[pair]
    blend_fn = getattr(blend_module, mode)
    result = blend_fn(_cmyk_canvas(backdrop), _cmyk_canvas(source), ColorMode.CMYK)
    ink = (1.0 - result.ravel()) * 100.0
    assert ink == pytest.approx(expected[mode], abs=2 * _ONE_STEP * 100.0)


@pytest.mark.parametrize("func", NON_SEPARABLE, ids=lambda f: f.__name__)
def test_non_separable_is_the_identity_on_equal_cmyk_operands(func: Callable) -> None:
    """Blending a colour with itself must return it (#781).

    The plainest statement of what the inverted round trip broke: it answered
    full CMY for every input, so even this could not hold. ``hue`` and
    ``saturation`` come back one ulp out because ``_set_sat`` rebuilds the
    channels from a sorted comparison rather than passing them through; the
    other four are exact.

    Weak for ``darker_color`` and ``lighter_color``, deliberately kept for
    symmetry: equal operands make their mask all-false, so they return the
    backdrop whatever ``_lightness`` computes and whichever operand K would come
    from. Those two are pinned by the Photoshop table above, not here.
    """
    Cb = _cmyk_canvas([37, 12, 68, 21])
    result = func(Cb.copy(), Cb.copy(), ColorMode.CMYK)
    assert result == pytest.approx(Cb, abs=1e-6)


@pytest.mark.parametrize("func", NON_SEPARABLE, ids=lambda f: f.__name__)
def test_non_separable_falls_back_when_the_operands_disagree_in_width(
    func: Callable, caplog: pytest.LogCaptureFixture
) -> None:
    """Operands of different widths degrade rather than half-blend (#781).

    Unreachable through the compositor -- ``_fit_source()`` brings every source
    to the canvas width, and the backdrop *is* the canvas -- so this pins a
    direct caller's blast radius. It is worth pinning because #781 made the
    failure quieter before making it louder: taking K from the backdrop means a
    three-channel backdrop under a four-channel source slices ``Cb[:, :, 3:4]``
    to *nothing*, and ``concatenate`` then returns three channels where four
    were asked for -- a silent short array rather than the ``IndexError`` the
    same input used to raise.
    """
    Cb = np.full((2, 2, 3), 0.4, dtype=np.float32)
    Cs = np.full((2, 2, 4), 0.6, dtype=np.float32)
    with caplog.at_level(logging.DEBUG, logger="psd_tools.composite.blend"):
        result = func(Cb.copy(), Cs.copy(), ColorMode.CMYK)
    assert result.shape == (2, 2, 4), "must not silently narrow the result"
    assert np.array_equal(result, normal(Cb, Cs))
    assert "4-channel source against a 3-channel backdrop" in caplog.text


def test_get_blend_func_binds_the_mode_only_to_the_non_separable_six() -> None:
    """Which functions take a colour mode is a correctness question (#746).

    ``color_dodge`` and ``color_burn`` already have a third parameter of their
    own -- the ``s`` factor -- so binding the mode across the whole table would
    hand them a ``ColorMode`` as that factor. The six wrappers register
    themselves as the decorator builds them; everything else must come back
    untouched, and identically, so that a caller can still compare identity.
    """
    assert get_blend_func(BlendMode.MULTIPLY, ColorMode.MULTICHANNEL) is multiply
    assert get_blend_func(BlendMode.COLOR_DODGE, ColorMode.CMYK) is color_dodge
    assert get_blend_func(BlendMode.HUE) is hue
    assert get_blend_func(BlendMode.HUE, ColorMode.MULTICHANNEL) is not hue


def test_get_blend_func_defaults_unknown_keys_to_normal() -> None:
    """The ``.get(..., normal)`` default this replaced is load-bearing (#746).

    ``PASS_THROUGH`` has no entry in ``BLEND_FUNC`` and reaches the lookup for
    real: a group that isolates its adjustments is composited as an ordinary
    source, so ``_apply_source()`` is called with it. Answering ``None`` there
    would raise rather than composite.
    """
    assert BLEND_FUNC.get(BlendMode.PASS_THROUGH) is None
    assert get_blend_func(BlendMode.PASS_THROUGH) is normal
    assert get_blend_func(BlendMode.PASS_THROUGH, ColorMode.MULTICHANNEL) is normal
    assert get_blend_func(b"nosuchblendmode", ColorMode.CMYK) is normal


@pytest.mark.parametrize(
    "key",
    [Enum.Hue, Enum.Saturation, Enum.Color, Enum.Luminosity]
    + [b"darkerColor", b"lighterColor"],
)
def test_get_blend_func_degrades_the_descriptor_keys_too(key: bytes) -> None:
    """Effects and strokes look their blend mode up by descriptor key (#746).

    ``BLEND_FUNC`` carries the six twice over, once per key family, and a typo
    in the descriptor half shipped undetected once already -- see
    ``test_lighter_color_descriptor_key`` above. So the family a layer's own
    blend mode does *not* come through is pinned here rather than assumed to
    follow.
    """
    Cb, Cs = _mixed_pair(4)
    blend_fn = get_blend_func(key, ColorMode.MULTICHANNEL)
    assert np.array_equal(blend_fn(Cb.copy(), Cs.copy()), normal(Cb, Cs))


# The separable half of the same experiment that produced ``PHOTOSHOP_CMYK``
# above, and the answer to #189: 17 of the 20 modes here already agreed with
# Photoshop to within 1.4/255, so the compositor's CMYK convention -- the
# canvas counts what is left of the ink, and the separable formulas apply to
# that complement -- was never the problem the issue supposed. Three modes were
# wrong, and wrong in every colour mode rather than only in CMYK:
# ``soft_light`` keyed D on the source, ``vivid_light`` inherited backdrop
# special cases Photoshop does not apply, and ``hard_mix`` fudged the tie.
# Pairs 2 and 3 are the ones that discriminate: pair 2 carries the two
# ``vivid_light`` corners (Cb == 1 with Cs == 0, and Cb == 0 with Cs == 1) and
# pair 3 carries the ``hard_mix`` tie from both sides (Cb + Cs == 1 with Cb
# above and below a half) together with two backdrops under a quarter, where
# ``soft_light``'s D actually differs. Pair 2 does one more job: its
# ``color_burn`` and ``color_dodge`` rows sit on those same two corners and
# pin that the plain modes *do* keep the backdrop special cases Vivid Light
# does not, which is the surprising half of that fix and the reason it is not
# simply a bug in one of the two. Format: ``(backdrop, source, {mode:
# result})``, ink percent, authored the same way -- Photoshop's own render.
PHOTOSHOP_CMYK_SEPARABLE: list[
    tuple[list[float], list[float], dict[str, list[float]]]
] = [
    (
        [80, 20, 10, 5],
        [10, 70, 60, 20],
        {
            "color_burn": [88.63, 66.27, 24.71, 6.27],
            "color_dodge": [0, 0, 0, 0],
            "darken": [80, 69.8, 60, 20],
            "difference": [29.8, 50.2, 49.8, 85.1],
            "divide": [77.65, 0, 0, 0],
            "exclusion": [25.88, 38.43, 41.96, 77.25],
            "hard_light": [16.08, 51.76, 27.84, 1.96],
            "hard_mix": [0, 0, 0, 0],
            "lighten": [9.8, 20, 9.8, 5.1],
            "linear_burn": [89.8, 89.8, 69.8, 25.1],
            "linear_dodge": [0, 0, 0, 0],
            "linear_light": [0, 60, 30.2, 0],
            "multiply": [81.96, 75.69, 63.92, 23.92],
            "normal": [9.8, 69.8, 60, 20],
            "overlay": [63.92, 27.84, 11.76, 1.96],
            "pin_light": [19.61, 40, 20.39, 5.1],
            "screen": [7.84, 14.12, 5.88, 1.18],
            "soft_light": [60.39, 26.27, 11.76, 3.53],
            "subtract": [100, 50.2, 49.8, 85.1],
            "vivid_light": [0, 33.33, 12.16, 0],
        },
    ),
    (
        [10, 70, 60, 20],
        [80, 20, 10, 5],
        {
            "color_burn": [49.02, 87.45, 66.67, 21.18],
            "color_dodge": [0, 0, 0, 0],
            "darken": [80, 69.8, 60, 20],
            "difference": [29.8, 50.2, 49.8, 85.1],
            "divide": [0, 62.35, 55.69, 15.69],
            "exclusion": [25.88, 38.43, 41.96, 77.25],
            "hard_light": [63.92, 28.24, 12.16, 1.96],
            "hard_mix": [0, 0, 0, 0],
            "lighten": [9.8, 20, 9.8, 5.1],
            "linear_burn": [89.8, 89.8, 69.8, 25.1],
            "linear_dodge": [0, 0, 0, 0],
            "linear_light": [70.2, 10.2, 0, 0],
            "multiply": [81.96, 75.69, 63.92, 23.92],
            "normal": [80, 20, 9.8, 5.1],
            "overlay": [15.69, 51.76, 27.84, 1.96],
            "pin_light": [60, 40, 19.61, 10.2],
            "screen": [7.84, 14.12, 5.88, 1.18],
            "soft_light": [15.29, 54.9, 41.57, 11.76],
            "subtract": [29.8, 100, 100, 100],
            "vivid_light": [24.71, 24.31, 0, 0],
        },
    ),
    (
        [100, 0, 50, 0],
        [0, 100, 50, 0],
        {
            "color_burn": [100, 0, 99.22, 0],
            "color_dodge": [100, 0, 0, 0],
            "darken": [100, 100, 49.8, 0],
            "difference": [0, 0, 100, 100],
            "divide": [100, 0, 0, 0],
            "exclusion": [0, 0, 49.8, 100],
            "hard_light": [0.39, 100, 49.8, 0],
            "hard_mix": [100, 0, 0, 0],
            "lighten": [0, 0, 49.8, 0],
            "linear_burn": [100, 100, 99.61, 0],
            "linear_dodge": [0, 0, 0, 0],
            "linear_light": [0.39, 100, 49.8, 0],
            "multiply": [100, 100, 74.9, 0],
            "normal": [0, 100, 49.8, 0],
            "overlay": [100, 0, 49.8, 0],
            "pin_light": [0, 100, 49.8, 0],
            "screen": [0, 0, 24.71, 0],
            "soft_light": [100, 0, 49.8, 0],
            "subtract": [100, 0, 100, 100],
            "vivid_light": [0, 100, 49.8, 0],
        },
    ),
    (
        [25, 75, 95, 95],
        [75, 25, 0, 25],
        {
            "color_burn": [100, 100, 94.9, 100],
            "color_dodge": [0, 0, 0, 79.61],
            "darken": [74.9, 74.9, 94.9, 94.9],
            "difference": [50.2, 50.2, 5.1, 30.2],
            "divide": [0, 66.67, 94.9, 93.33],
            "exclusion": [37.65, 37.65, 5.1, 27.84],
            "hard_light": [62.35, 38.04, 0.39, 47.84],
            "hard_mix": [0, 100, 0, 100],
            "lighten": [25.1, 25.1, 0, 25.1],
            "linear_burn": [100, 100, 94.9, 100],
            "linear_dodge": [0, 0, 0, 20],
            "linear_light": [75.29, 25.49, 0, 45.49],
            "multiply": [81.18, 81.18, 94.9, 96.08],
            "normal": [74.9, 25.1, 0, 25.1],
            "overlay": [37.65, 62.35, 89.8, 92.55],
            "pin_light": [49.8, 50.59, 0, 50.59],
            "screen": [18.82, 18.82, 0, 23.92],
            "soft_light": [34.51, 62.35, 82.35, 88.63],
            "subtract": [50.2, 100, 100, 100],
            "vivid_light": [50.2, 50.2, 0, 89.8],
        },
    ),
    (
        [0, 0, 0, 0],
        [100, 100, 100, 100],
        {
            "color_burn": [0, 0, 0, 0],
            "color_dodge": [0, 0, 0, 0],
            "darken": [100, 100, 100, 100],
            "difference": [0, 0, 0, 0],
            "divide": [0, 0, 0, 0],
            "exclusion": [0, 0, 0, 0],
            "hard_light": [100, 100, 100, 100],
            "hard_mix": [0, 0, 0, 0],
            "lighten": [0, 0, 0, 0],
            "linear_burn": [100, 100, 100, 100],
            "linear_dodge": [0, 0, 0, 0],
            "linear_light": [100, 100, 100, 100],
            "multiply": [100, 100, 100, 100],
            "normal": [100, 100, 100, 100],
            "overlay": [0, 0, 0, 0],
            "pin_light": [100, 100, 100, 100],
            "screen": [0, 0, 0, 0],
            "soft_light": [0, 0, 0, 0],
            "subtract": [0, 0, 0, 0],
            "vivid_light": [100, 100, 100, 100],
        },
    ),
]


def _cmyk_canvas_8bit(ink: list[float]) -> np.ndarray:
    """Ink percent snapped to the 8-bit value Photoshop actually stored.

    ``_cmyk_canvas`` above converts the percentage directly, which is fine when
    a blend is continuous in its operands. ``hard_mix`` is not: it turns on a
    tie at ``Cb + Cs == 1``, and a nominal 50% ink is stored as 128/255 rather
    than the 0.5 that a direct conversion yields -- close enough to read as a
    tie that is not one, and to assert the wrong branch. Snapping first makes
    the readable round numbers in the table above mean exactly what Photoshop
    held: every operand in the table round-trips to the byte Photoshop reported.
    That is checked rather than guaranteed -- inks such as 10, 50 and 70 land on
    a .5 boundary in exact arithmetic, and it is float64 representation error
    and ``np.round``'s half-to-even rule that put them on Photoshop's side. A
    new pair that lands on such a boundary needs the same check, which
    ``test_the_table_operands_round_trip_to_photoshops_bytes`` below applies.
    """
    value = np.round((1.0 - np.array(ink, dtype=np.float64) / 100.0) * 255.0)
    return (value / 255.0).astype(np.float32).reshape(1, 1, 4)


def test_the_separable_table_covers_every_pair_alike() -> None:
    """The parametrize below reads its mode list from pair 0 alone.

    A key missing from a later pair would be a ``KeyError`` at run time and an
    extra one would go silently untested, so the table is made to answer for
    itself here.
    """
    keys = [set(res) for _, _, res in PHOTOSHOP_CMYK_SEPARABLE]
    assert all(k == keys[0] for k in keys)
    assert len(keys[0]) == 20


def test_the_table_operands_round_trip_to_photoshops_bytes() -> None:
    """``_cmyk_canvas_8bit``'s premise, pinned rather than assumed.

    The table reads in round nominal ink because that is legible, and relies on
    the snap landing on the byte Photoshop stored. ``normal`` returns the source
    untouched, so its row is Photoshop's own report of that operand and gives
    the check for free on one side; the backdrops are covered by the fact that
    every pair's backdrop appears as some pair's source, or as its own
    ``darken``/``lighten`` row.
    """
    for backdrop, source, expected in PHOTOSHOP_CMYK_SEPARABLE:
        stored = list((1.0 - _cmyk_canvas_8bit(source).reshape(4)) * 100.0)
        # Photoshop's sampler reports ink to two decimals, so 9.803921... comes
        # back as 9.8. One 8-bit step is 100/255 == 0.392 of a percent, so this
        # tolerates that report rounding and still catches a whole byte.
        assert stored == pytest.approx(expected["normal"], abs=0.01)
        assert _cmyk_canvas_8bit(backdrop).dtype == np.float32


@pytest.mark.parametrize(
    "mode", sorted(PHOTOSHOP_CMYK_SEPARABLE[0][2]), ids=lambda m: m
)
@pytest.mark.parametrize(
    "pair", range(len(PHOTOSHOP_CMYK_SEPARABLE)), ids=lambda i: "pair%d" % i
)
def test_separable_matches_photoshop_on_cmyk(pair: int, mode: str) -> None:
    """Every separable mode against Photoshop's own CMYK render (#189).

    This is the coverage the 164-layer ``cmyk-blend-modes.psd`` fixture cannot
    give. That document exercises all of these modes, but its error is diluted
    across the whole canvas: it sat at 0.000179 against a 0.01 threshold while
    three modes were wrong, and two of the three defects moved it by less than
    a thousandth. Reverting any one of the three fails a row here instead.

    A CMYK table settles a fix advertised for every colour mode because these
    twenty are not mode-aware: none is in ``_MODE_AWARE``, so ``get_blend_func``
    hands back the bare function and one object serves RGB, Grayscale, Lab and
    CMYK alike, as the ``get_blend_func`` binding test above pins. So fixing the
    arithmetic on CMYK fixes it everywhere, which is why #189's report against
    CMYK alone never located a CMYK fault.
    """
    backdrop, source, expected = PHOTOSHOP_CMYK_SEPARABLE[pair]
    blend_fn = getattr(blend_module, mode)
    result = blend_fn(_cmyk_canvas_8bit(backdrop), _cmyk_canvas_8bit(source))
    ink = list((1.0 - result.reshape(4)) * 100.0)
    assert ink == pytest.approx(expected[mode], abs=2 * _ONE_STEP * 100.0)
