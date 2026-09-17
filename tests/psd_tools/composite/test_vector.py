import logging

import numpy as np
import pytest

from psd_tools import PSDImage
from psd_tools.api.layers import Group
from psd_tools.composite import composite, vector
from psd_tools.composite.paint import (
    draw_gradient_fill,
    draw_pattern_fill,
    draw_solid_color_fill,
)
from psd_tools.constants import Tag
from psd_tools.psd.descriptor import Double
from psd_tools.terminology import Enum, Key, Type

from ..utils import full_name
from .test_composite import _mse, check_composite_quality

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    ("filename",),
    [
        ("path-operations/combine.psd",),
        ("path-operations/combine-group.psd",),
        ("path-operations/exclude-first.psd",),
        ("path-operations/exclude.psd",),
        ("path-operations/exclude-group.psd",),
        ("path-operations/intersect-all.psd",),
        ("path-operations/intersect-first.psd",),
        ("path-operations/intersect-group.psd",),
        ("path-operations/subtract-all.psd",),
        ("path-operations/subtract-first.psd",),
        ("path-operations/subtract-second.psd",),
        ("path-operations/subtract-group.psd",),
    ],
)
def test_path_operations(filename: str) -> None:
    check_composite_quality(filename, 0.02)


@pytest.mark.parametrize(
    ("filename",),
    [
        ("stroke.psd",),
    ],
)
def test_draw_stroke(filename: str) -> None:
    check_composite_quality(filename, 0.01, force=True)


@pytest.mark.parametrize(
    ("filename",),
    [
        ("effects/stroke-composite.psd",),  # Fix me!
    ],
)
@pytest.mark.xfail
def test_draw_stroke_fail(filename: str) -> None:
    check_composite_quality(filename, 0.01, force=True)


def test_draw_solid_color_fill() -> None:
    psd = PSDImage.open(full_name("layers-minimal/solid-color-fill.psd"))
    desc = psd[0].tagged_blocks.get_data(Tag.SOLID_COLOR_SHEET_SETTING)
    draw_solid_color_fill(psd.viewbox, psd.color_mode, desc)


@pytest.mark.parametrize(
    "filename", ["layers-minimal/pattern-fill.psd", "layers/pattern-fill.psb"]
)
def test_draw_pattern_fill(filename: str) -> None:
    psd = PSDImage.open(full_name(filename))
    desc = psd[0].tagged_blocks.get_data(Tag.PATTERN_FILL_SETTING)
    draw_pattern_fill(psd.viewbox, psd, desc)
    desc[b"Scl "] = Double(50.0)
    desc[b"Opct"] = Double(67.0)
    draw_pattern_fill(psd.viewbox, psd, desc)


def test_draw_pattern_fill_splits_a_multichannel_alpha() -> None:
    """Which plane is alpha comes from the pattern's slots, not from its mode.

    The split used to be keyed on ``EXPECTED_CHANNELS[pattern.image_mode]``,
    which is 64 for multichannel -- the format's maximum rather than any
    pattern's count. ``shape[2] > 64`` is never true, so the alpha stayed in
    the color array and the four-plane result was rejected downstream as
    inconsistent with the three-channel canvas (#741).

    Both callers of this function -- the fill layer and the pattern overlay --
    fail on the same array, which is why the pin sits here rather than at
    either of them.
    """
    psd = PSDImage.open(full_name("multichannel-pattern-fill.psd"))
    desc = psd[0].tagged_blocks.get_data(Tag.PATTERN_FILL_SETTING)

    color, shape = draw_pattern_fill(psd.viewbox, psd, desc)

    assert color is not None and shape is not None
    assert color.shape == (psd.height, psd.width, 3)
    assert shape.shape == (psd.height, psd.width, 1)
    # The three inks are the leading slots, in slot order.
    assert np.allclose(color[0, 0], [0x20 / 255.0, 0x80 / 255.0, 0xC0 / 255.0])
    # The alpha is the last slot: opaque over the top half of each 8x8 tile.
    assert shape[0, 0, 0] == 1.0
    assert shape[4, 0, 0] == 0.0


def test_draw_gradient_fill() -> None:
    psd = PSDImage.open(full_name("layers-minimal/gradient-fill.psd"))
    desc = psd[0].tagged_blocks.get_data(Tag.GRADIENT_FILL_SETTING)
    draw_gradient_fill(psd.viewbox, psd.color_mode, desc)
    for angle in (-90.0, 0.0, 90.0, 180.0):
        desc.get(Key.Angle.value).value = angle
        draw_gradient_fill(psd.viewbox, psd.color_mode, desc)
    desc.get(b"Type").enum = Enum.Radial.value
    draw_gradient_fill(psd.viewbox, psd.color_mode, desc)


@pytest.mark.parametrize(
    ("filename",),
    [
        ("gradient-styles.psd",),
        ("gradient-sizes.psd",),
    ],
)
def test_gradient_styles(filename: str) -> None:
    psd = PSDImage.open(full_name(filename))
    for artboard in psd:
        assert isinstance(artboard, Group)
        for layer in artboard:
            desc = layer.tagged_blocks.get_data(Tag.GRADIENT_FILL_SETTING)
            form = desc.get(Key.Gradient).get(Type.GradientForm).enum
            reference = composite(layer)[0]
            result = composite(layer, force=True)[0]
            if form == Enum.CustomStops:
                assert _mse(reference, result) <= 0.08
            elif form == Enum.ColorNoise:
                # Noise gradient is not of good quality.
                assert _mse(reference, result) <= 0.2


# The threshold is per fixture rather than shared. A single loose one hid #743:
# the Lab file passed at 0.05 while sitting at 0.033, an error big enough that
# a near-neutral mid-tone was rendering as a dark saturated colour. Correcting
# the normalization takes it to 0.0013, and 0.01 catches that regression with
# 3x to spare.
#
# Not tighter, because what is left is not a rounding floor: 98% of the residual
# MSE comes from the ~12% of pixels along the stroke edges, which is
# rasterization geometry and moves with the aggdraw and Pillow versions CI
# happens to resolve. The tight bound on this normalization lives in
# test_paint.py instead, on a fixture of solid fills with no edges to raster --
# there it is 2/255 on the worst pixel.
#
# The other three fixtures are untouched by that change and keep the old bound.
@pytest.mark.parametrize(
    ("filename", "threshold"),
    [
        ("descriptors/stroke-color-descriptors-rgb.psd", 0.05),
        ("descriptors/stroke-color-descriptors-gray.psd", 0.05),
        ("descriptors/stroke-color-descriptors-lab.psd", 0.01),
        ("descriptors/stroke-color-descriptors-hsb-with-rgb-mode.psd", 0.05),
    ],
)
def test_stroke_color(filename: str, threshold: float) -> None:
    check_composite_quality(filename, threshold, force=True)


def test_draw_vector_mask_reaches_outside_the_canvas() -> None:
    """A path is rasterized in document coordinates, not clipped to the canvas.

    ``stroke-effect-transparent-shape.psd`` holds a rectangle whose path runs
    from (-1, -1) to (33, 33) on a 32x32 canvas, so on the canvas its left
    edge is not in the picture at all -- every pixel of the row is covered.
    Asked for a wider box, the rasterizer must place the same path on it and
    put that edge back, which is what lets a stroke traced from the mask
    follow the layer rather than the canvas (#804).
    """
    psd = PSDImage.open(full_name("effects/stroke-effect-transparent-shape.psd"))
    layer = psd[1]

    on_canvas = vector.draw_vector_mask(layer)
    assert np.array_equal(on_canvas[16, :4, 0], np.ones(4, dtype=np.float32)), (
        "the canvas holds no left edge to find"
    )

    viewport = (-3, -3, 35, 35)
    wide = vector.draw_vector_mask(layer, viewport)
    assert wide.shape == (38, 38, 1)
    # Row 19 is y = 16, the same row; x = -3 and -2 are outside the path and
    # x = -1 is the first column it covers.
    assert wide[19, 0, 0] == 0.0
    assert wide[19, 2, 0] == 1.0
    # Placing the path elsewhere would also move it: where the two boxes
    # overlap the coverage has to be identical.
    assert np.array_equal(wide[3:35, 3:35], on_canvas)


def test_draw_stroke_reaches_outside_the_canvas() -> None:
    """A stroke is rasterized in document coordinates, not clipped to the canvas.

    The stroke twin of :py:func:`test_draw_vector_mask_reaches_outside_the_canvas`.
    ``path-operations/combine.psd`` holds three overlapping ellipses on a 64x64
    canvas whose combined path runs the full 0..64 in both axes, so a 1 px
    stroke centred on it hangs off all four edges. Asked for a wider box, the
    rasterizer has to put those four strips back (#807).
    """
    psd = PSDImage.open(full_name("path-operations/combine.psd"))
    layer = psd[0]

    on_canvas = vector.draw_stroke(layer)
    assert on_canvas.shape == (64, 64, 1)

    viewport = (-4, -4, 68, 68)
    wide = vector.draw_stroke(layer, viewport)
    assert wide.shape == (72, 72, 1)
    # Row 3 is y = -1, one row above the canvas, where the tops of the two
    # upper ellipses are; the canvas raster has nowhere to hold them.
    assert wide[3, 28, 0] == pytest.approx(0.463, abs=0.02)
    assert wide[3, 44, 0] == pytest.approx(0.463, abs=0.02)
    # What the canvas raster loses is the whole margin, not one strip of it.
    margin = float(wide.sum() - wide[4:68, 4:68].sum())
    assert margin == pytest.approx(14.2, rel=0.1)

    # Placing the path elsewhere must not move it. aggdraw is not exactly
    # translation-invariant, so the overlap agrees to a quantization step
    # rather than bitwise -- eight of the 4096 pixels are 1/255 apart.
    assert np.allclose(wide[4:68, 4:68], on_canvas, atol=1 / 255)


def test_stroke_follows_a_shifted_viewport() -> None:
    """Moving the viewport by a pixel moves the stroke with it.

    ``_get_stroke()`` used to rasterize at document size and relocate the
    result only when its *dimensions* differed from the compositor's. A
    viewport the size of the document but at another origin took the other
    branch, and the document-coordinate raster was used as if it were already
    in viewport coordinates, putting the stroke a viewport-origin away from
    the fill it is supposed to cover (#807).
    """
    psd = PSDImage.open(full_name("stroke.psd"))
    width, height = psd.width, psd.height

    for force in (False, True):
        base = composite(psd, force=force)[0]
        shifted = composite(psd, viewport=(1, 1, width + 1, height + 1), force=force)[0]
        assert np.allclose(
            shifted[: height - 1, : width - 1], base[1:, 1:], atol=1 / 255
        ), f"the shifted render is not the shifted base render (force={force})"


def test_layer_composite_places_a_stroke_on_a_layer_sized_viewport() -> None:
    """The same trap, reached without asking for a viewport at all.

    ``layers/shape-layer.psd`` is 32x32 and its one shape layer has bbox
    (-1, -1, 31, 31), so ``layer.composite()`` renders on a box that carries
    the document's dimensions and a different origin -- exactly the case the
    dimension comparison got wrong. It is the only *stroked* layer in the
    fixture corpus whose box does, which is why this file is pinned here
    rather than parametrized.

    The document render is the ground truth: it is on the canvas box, so it
    never took the wrong branch and this fix leaves it untouched. The two
    rasters are a pixel apart, which aggdraw does not guarantee to be exact,
    so they are compared to a quantization step -- ample against an error that
    was a full 1.0 (#807).
    """
    psd = PSDImage.open(full_name("layers/shape-layer.psd"))
    layer = psd[0]
    assert layer.bbox == (-1, -1, 31, 31)

    for force in (False, True):
        document = composite(psd, force=force)[0]
        own = composite(layer, force=force)[0]
        # The boxes overlap on (0, 0, 31, 31): the document's top-left corner
        # and the layer's, one pixel in.
        assert np.allclose(document[:31, :31], own[1:, 1:], atol=1 / 255), (
            f"the layer render puts the stroke elsewhere (force={force})"
        )


def test_layer_composite_keeps_a_stroke_past_the_canvas_edge() -> None:
    """The canvas clip, at the compositor rather than at the rasterizer.

    ``transparency/transparency-group.psd`` holds a white rectangle with a
    black 1 px stroke at bbox (-1, -1, 129, 129) on a 256x256 canvas, so the
    left and top of its stroke are off the canvas. ``layer.composite()``
    renders on the layer's own box and so asks for those pixels; the stroke
    used to be drawn on the canvas, which has nothing there, and they came
    back as the white the stroke fill is pasted over (#807).

    This is the largest change in the corpus, and the only test that pins it
    end to end -- the document render cannot, because these pixels are exactly
    the ones it does not show.
    """
    psd = PSDImage.open(full_name("transparency/transparency-group.psd"))
    layer = list(psd.descendants())[2]
    assert layer.name == "Rectangle 1" and layer.bbox == (-1, -1, 129, 129)

    color, _, alpha = composite(layer, force=True)
    assert color.shape == (130, 130, 3)
    # Column 0 is x = -1 and row 0 is y = -1, both off the canvas. Every pixel
    # of both is the black stroke, partly covering -- not the white fill that
    # used to show through where the stroke had no coverage.
    assert color[:, 0].max() < 1 / 255, "the left edge lost its stroke"
    assert color[0, :].max() < 1 / 255, "the top edge lost its stroke"
    assert np.asarray(alpha)[:, 0, 0].min() > 0.0
