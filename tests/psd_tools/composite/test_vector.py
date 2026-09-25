import logging

import numpy as np
import pytest

from psd_tools import PSDImage
from psd_tools.api.layers import Group, Layer
from psd_tools.composite import composite, vector
from psd_tools.composite.paint import (
    draw_gradient_fill,
    draw_pattern_fill,
    draw_solid_color_fill,
)
from psd_tools.constants import Tag
from psd_tools.psd.descriptor import Bool, Double, Enumerated, UnitFloat
from psd_tools.psd.vector import ClosedKnotLinked, ClosedPath
from psd_tools.terminology import Enum, Key, Type

from ..utils import full_name
from .test_composite import _mse, check_composite_quality

logger = logging.getLogger(__name__)

# The two rectangles forged into one component below, in document
# coordinates on the 100x150 canvas of ``transparentbg.psd``.
_OUTER = (20, 40, 80, 110)
_INNER = (35, 55, 65, 95)


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


# Was expected to fail at 0.01, then measured 0.0066 once the fill it is
# stroked over stopped carrying aggdraw's quarter pixel of dilation (#844),
# and measures 0.00377 now that its eight inner strokes land inside their paths
# (#854) and blend with the fill rather than replacing it (#883). The bound is
# set above the measurement rather than at it: what is left is the stroke,
# which is still drawn by an aggdraw pen and so not bit-stable across versions.
@pytest.mark.parametrize(
    ("filename", "threshold"),
    [
        ("effects/stroke-composite.psd", 0.005),
    ],
)
def test_draw_stroke_over_a_fill(filename: str, threshold: float) -> None:
    check_composite_quality(filename, threshold, force=True)


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
    ``effects/stroke-composite.psd`` holds a shape at (182, 7, 273, 78) on a
    256x256 canvas, so its right-hand end is off the canvas and the inner
    stroke along its top and bottom edges runs off with it. Asked for a wider
    box, the rasterizer has to put that strip back (#807).
    """
    psd = PSDImage.open(full_name("effects/stroke-composite.psd"))
    layer = [x for x in psd.descendants() if x.name == "Clip+Effects"][0]
    assert layer.bbox == (182, 7, 273, 78), "the shape runs off the canvas"

    on_canvas = vector.draw_stroke(layer)
    assert on_canvas.shape == (256, 256, 1)

    viewport = (-4, -4, 260, 260)
    wide = vector.draw_stroke(layer, viewport)
    assert wide.shape == (264, 264, 1)
    # The 4 px stroke follows two horizontal edges off the right of the canvas,
    # so what the canvas raster loses is two 4x4 blocks of full coverage.
    margin = float(wide.sum() - wide[4:260, 4:260].sum())
    assert margin == 32.0
    assert float(wide[:, -4:].sum()) == 32.0, "the strip is the right-hand one"
    for strip in (wide[:4], wide[-4:], wide[:, :4]):
        assert float(strip.sum()) == 0.0, "the shape only leaves one edge"

    # Placing the path elsewhere must not move it.
    assert np.allclose(wide[4:260, 4:260], on_canvas, atol=1 / 255)


def test_an_inner_stroke_covers_the_whole_width_inside_the_path() -> None:
    """The band sits where the alignment puts it, and is as wide as it says (#854).

    ``effects/stroke-composite.psd``'s ``Plain`` is a 100x100 path in a 102x102
    box, carrying a 3 px inner stroke. Inner means the whole band lies inside the path, so it covers
    the first three columns the fill covers. A pen centred on the path put 1.5
    px in and 1.5 px out instead, covering two columns, one of them outside the
    shape -- where a vector stroke cannot show at all, since it has no coverage
    of its own.
    """
    psd = PSDImage.open(full_name("effects/stroke-composite.psd"))
    # Two of the eight layers are named ``Plain``; this is the left-hand one.
    layer = [x for x in psd.descendants() if x.name == "Plain"][0]
    assert layer.stroke is not None and layer.bbox == (20, 19, 122, 121)
    assert layer.stroke.line_width == 3.0
    assert layer.stroke.line_alignment == "inner"

    stroke = vector.draw_stroke(layer)[:, :, 0]
    fill = vector.draw_vector_mask(layer)[:, :, 0]
    # Midway down the shape, clear of the horizontal edges and their corners.
    row = 70
    assert list(fill[row, 20:27]) == [0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    assert list(stroke[row, 20:27]) == [0.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0]
    # Nothing outside the fill, and 3 px of it, on the left half of the row.
    assert float((stroke[row] * (fill[row] == 0.0)).sum()) == 0.0
    assert float(stroke[row, :61].sum()) == 3.0


def test_a_fractional_stroke_width_matches_photoshops_own_band() -> None:
    """A 1.47 px band covers 1.47 px, where Photoshop puts it (#854).

    ``stroke.psd``'s ``Rectangle 1`` has no fill, so the channels Photoshop
    stored for it are its own rasterization of the stroke band and nothing
    else -- an oracle for the two things a band has, its width and its side.
    Across the left edge it reads 1.0 then 0.4706, which is the 1.47 px the
    descriptor asks for, laid inside the path; this draws 1.0 then 0.4667,
    within a quantization step of it.

    Only across that edge. The stroke is dashed (``strokeStyleLineDashSet`` of
    4 on, 2 off), which the pen does not draw, so Photoshop's horizontal runs
    are broken where this one is solid -- 188 of the layer's pixels differ by
    more than a quantization step, and the band sums to 317.4 against
    Photoshop's 212.6, a ratio of 0.670 against the 4/6 the dashes cut it to.
    Row 20 falls inside a dash, and the left edge is where the comparison is
    about the band rather than about the gaps in it.
    """
    psd = PSDImage.open(full_name("stroke.psd"))
    layer = [x for x in psd.descendants() if x.name == "Rectangle 1"][0]
    assert layer.stroke is not None
    assert layer.stroke.line_width == 1.47
    assert layer.stroke.line_alignment == "inner"

    stored = layer.numpy("shape")
    assert stored is not None
    stored = stored[:, :, 0]
    stroke = vector.draw_stroke(layer, layer.bbox)[:, :, 0]
    fill = vector.draw_vector_mask(layer, layer.bbox)[:, :, 0]
    row = 20
    assert list(fill[row, 0:4]) == [0.0, 1.0, 1.0, 1.0], "the path's left edge"
    assert stroke[row, 1] == 1.0
    assert stroke[row, 2] == pytest.approx(0.467, abs=0.01)
    assert float(stroke[row, :37].sum()) == pytest.approx(1.47, abs=0.01)
    # Photoshop's own numbers for those two pixels, and its own empty third.
    assert np.allclose(stroke[row, 1:4], stored[row, 1:4], atol=1 / 255)
    assert stored[row, 3] == 0.0 and stroke[row, 3] == 0.0


def test_a_centred_stroke_is_still_the_plain_pen() -> None:
    """The position #854 did not change, pinned so that it cannot drift.

    Every stroke used to be drawn as a pen centred on the path, and a centred
    one still is -- the same call, at the width the descriptor states, with no
    clip over it.
    """
    psd = PSDImage.open(full_name("descriptors/stroke-color-descriptors-rgb.psd"))
    layer = [x for x in psd.descendants() if x.name == "Rectangle 1"][0]
    assert layer.stroke is not None and layer.stroke.line_alignment == "center"

    plain = vector._draw_path(layer, pen={"color": 255, "width": 1.0})
    assert np.array_equal(vector.draw_stroke(layer), plain)


def test_a_stroke_whose_alignment_is_unreadable_is_drawn_centred() -> None:
    """An unstated or unrecognised position degrades, it does not raise (#854).

    :py:attr:`psd_tools.api.shape.Stroke.line_alignment` raises on a
    descriptor that carries no alignment at all, and answers a ``repr`` for an
    enum it does not know. Neither is any way for a renderer to end -- the
    position is one field of a stroke with the rest of itself to draw -- so
    both are drawn centred, which is where every stroke was drawn before #854
    and the only one of the three positions not biased in or out.

    Photoshop writes one of the three, so this is forged onto a fixture that
    states ``inner``.
    """
    psd = PSDImage.open(full_name("effects/stroke-composite.psd"))
    layer = [x for x in psd.descendants() if x.name == "Plain"][0]
    assert layer.stroke is not None and layer.stroke.line_alignment == "inner"
    desc = layer.stroke._data
    centred = vector._draw_path(layer, pen={"color": 255, "width": 3.0})
    assert not np.array_equal(vector.draw_stroke(layer), centred), "inner, for now"

    del desc[b"strokeStyleLineAlignment"]
    with pytest.raises(AttributeError):
        layer.stroke.line_alignment
    assert np.array_equal(vector.draw_stroke(layer), centred), "no alignment"

    desc[b"strokeStyleLineAlignment"] = Enumerated(
        b"strokeStyleLineAlignment", b"strokeStyleAlignNonesuch"
    )
    assert layer.stroke.line_alignment == "b'strokeStyleAlignNonesuch'"
    assert np.array_equal(vector.draw_stroke(layer), centred), "unknown alignment"


def test_an_outer_stroke_lies_outside_the_path() -> None:
    """The other side of the same clip (#854).

    The corpus has exactly one outer-aligned vector stroke, on a layer whose
    own test is an ``xfail``, so the branch is forged here instead: an outer
    band lies wholly outside the path, and reaches the width it states.

    A layer's coverage stops at its own box, and ``_get_object()`` keeps only
    the stroke's colour, so most of an outer band cannot show in a render.
    That is the rasterizer's answer, not the render's.
    """
    psd = PSDImage.open(full_name("effects/stroke-composite.psd"))
    layer = [x for x in psd.descendants() if x.name == "Plain"][0]
    assert layer.stroke is not None and layer.bbox == (20, 19, 122, 121)
    layer.stroke._data[b"strokeStyleLineAlignment"] = Enumerated(
        b"strokeStyleLineAlignment", b"strokeStyleAlignOutside"
    )
    assert layer.stroke.line_alignment == "outer"
    assert layer.stroke.line_width == 3.0

    viewport = (10, 10, 132, 131)
    stroke = vector.draw_stroke(layer, viewport)[:, :, 0]
    fill = vector.draw_vector_mask(layer, viewport)[:, :, 0]
    assert float((stroke * (fill > 1e-9)).sum()) == 0.0, "nothing inside the path"
    # Midway down the shape, the three columns outside the fill's left edge,
    # which on this viewport starts at column 11.
    row = 60
    assert list(fill[row, 7:12]) == [0.0, 0.0, 0.0, 0.0, 1.0]
    assert list(stroke[row, 7:12]) == [0.0, 1.0, 1.0, 1.0, 0.0]


def test_a_centred_stroke_survives_negative_document_coordinates() -> None:
    """#807's guarantee for a stroke that really does leave the canvas.

    ``path-operations/combine.psd``'s combined path runs the full 0..64 of its
    canvas, so a stroke *centred* on it hangs off all four edges -- the case
    this used to be measured on, before its own stroke turned out to be inner
    and to stop at the path (:py:func:`test_an_inner_stroke_stops_where_the_path_does`).
    Forging the alignment back keeps the negative-coordinate half of #807
    pinned: the pen translates the path by minus the viewport origin, which is
    machinery of its own, and a band that never leaves the canvas cannot
    exercise it.
    """
    psd = PSDImage.open(full_name("path-operations/combine.psd"))
    layer = psd[0]
    assert layer.stroke is not None
    layer.stroke._data[b"strokeStyleLineAlignment"] = Enumerated(
        b"strokeStyleLineAlignment", b"strokeStyleAlignCenter"
    )
    assert layer.stroke.line_alignment == "center"

    on_canvas = vector.draw_stroke(layer)
    wide = vector.draw_stroke(layer, (-4, -4, 68, 68))
    # Row 3 is y = -1, above the canvas, where the tops of the two upper
    # ellipses are; the canvas raster has nowhere to hold them.
    assert wide[3, 28, 0] == pytest.approx(0.463, abs=0.02)
    assert wide[3, 44, 0] == pytest.approx(0.463, abs=0.02)
    assert float(wide.sum() - wide[4:68, 4:68].sum()) == pytest.approx(14.2, rel=0.1)
    # aggdraw is not exactly translation-invariant, so the overlap agrees to a
    # quantization step rather than bitwise.
    assert np.allclose(wide[4:68, 4:68], on_canvas, atol=1 / 255)


def test_an_inner_stroke_wider_than_the_shape_cancels_itself() -> None:
    """The limit of drawing a sided band with a pen of twice the width (#854).

    The pen is one outline filled by the even-odd rule, so where the shape is
    thinner than the doubled width the band overlaps itself and cancels. On a
    100x100 path an inner stroke of width ``w`` leaves a square hole of side
    ``2w - 100`` once ``w`` passes 50, where Photoshop paints solid.

    Drawn centred, the same cancellation started at ``w = 100`` and left a
    hole of side ``100 - w``, so the two cross at ``w = 66.7``: this is the
    better of them below that and the worse above. Both are wrong, and the
    widest stroke in the corpus is 10 px on a far larger shape. Pinned so the
    limit is a decision rather than a surprise.
    """
    psd = PSDImage.open(full_name("effects/stroke-composite.psd"))
    layer = [x for x in psd.descendants() if x.name == "Plain"][0]
    assert layer.stroke is not None and layer.stroke.line_alignment == "inner"
    desc = layer.stroke._data
    unit = desc[b"strokeStyleLineWidth"].unit
    viewport = (12, 11, 130, 129)
    fill = vector.draw_vector_mask(layer, viewport)[:, :, 0]
    assert float(fill.sum()) == 10000.0, "a 100x100 path"
    solid = fill > 0.5

    def hole(width: float) -> int:
        desc[b"strokeStyleLineWidth"] = UnitFloat(value=width, unit=unit)
        band = vector.draw_stroke(layer, viewport)[:, :, 0]
        return int((solid & (band < 0.5)).sum())

    # Half the thickness is the widest band the doubled pen draws whole.
    assert hole(50.0) == 0
    assert hole(60.0) == 20 * 20
    assert hole(90.0) == 80 * 80
    # And the centred pen it replaces was worse over all of that range.
    for width in (50.0, 60.0):
        desc[b"strokeStyleLineWidth"] = UnitFloat(value=width, unit=unit)
        centred = vector._draw_path(
            layer, pen={"color": 255, "width": width}, viewport=viewport
        )[:, :, 0]
        assert int((solid & (centred < 0.5)).sum()) > hole(width)


def test_an_inner_stroke_stops_where_the_path_does() -> None:
    """An inner stroke has nothing outside the path, canvas edge or not.

    ``path-operations/combine.psd``'s three ellipses combine into a path that
    runs the full 0..64 of its canvas, so the 1 px stroke *centred* on it hung
    off all four edges, and used to be what
    :py:func:`test_draw_stroke_reaches_outside_the_canvas` measured. The
    stroke is inner-aligned (#854), so now it stops where the path stops and
    the margin is empty -- while the rasterizer still honours the wider box,
    which is what the overlap below says.
    """
    psd = PSDImage.open(full_name("path-operations/combine.psd"))
    layer = psd[0]
    assert layer.stroke is not None and layer.stroke.line_alignment == "inner"

    on_canvas = vector.draw_stroke(layer)
    wide = vector.draw_stroke(layer, (-4, -4, 68, 68))
    assert float(wide.sum() - wide[4:68, 4:68].sum()) == 0.0
    assert np.allclose(wide[4:68, 4:68], on_canvas, atol=1 / 255)
    # Not empty for want of a stroke: the band is inside the path instead.
    assert float(on_canvas.sum()) > 700.0


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
    never took the wrong branch and this fix leaves it untouched. The error it
    was written against was a full 1.0 (#807).

    The colour is read only where both renders put something, because where
    the alpha is zero the colour channel holds whatever the compositor last
    left there and the two boxes leave different things. That is not a
    weakening: a fill is now the area of the path, which does not depend on
    where the path is rasterized, so the alphas agree exactly and the visible
    colours agree exactly -- where aggdraw's raster used to need a
    quantization step of slack (#844).
    """
    psd = PSDImage.open(full_name("layers/shape-layer.psd"))
    layer = psd[0]
    assert layer.bbox == (-1, -1, 31, 31)

    for force in (False, True):
        document_color, _, document_alpha = composite(psd, force=force)
        own_color, _, own_alpha = composite(layer, force=force)
        # The boxes overlap on (0, 0, 31, 31): the document's top-left corner
        # and the layer's, one pixel in.
        document_alpha = np.asarray(document_alpha)[:31, :31]
        own_alpha = np.asarray(own_alpha)[1:, 1:]
        assert np.allclose(document_alpha, own_alpha, atol=1e-6), (
            f"the layer render covers different pixels (force={force})"
        )
        visible = (document_alpha[..., 0] > 0) & (own_alpha[..., 0] > 0)
        assert visible.sum() > 500, "nothing visible to compare"
        difference = np.abs(document_color[:31, :31] - own_color[1:, 1:]).max(axis=2)
        assert difference[visible].max() == 0.0, (
            f"the layer render puts the stroke elsewhere (force={force})"
        )


def test_layer_composite_keeps_a_stroke_past_the_canvas_edge() -> None:
    """The canvas clip, at the compositor rather than at the rasterizer.

    ``transparency/transparency-group.psd`` holds a white rectangle with a
    black 1 px stroke at bbox (-1, -1, 129, 129) on a 256x256 canvas, so the
    box it renders on runs a pixel off the canvas on the left and the top.
    ``layer.composite()`` asks for those pixels; the stroke used to be drawn
    on the canvas, which has nothing there, and the whole box came back as the
    white the stroke fill is pasted over (#807).

    The layer carries Photoshop's own raster of itself, which is what this
    compares against -- the document render cannot, because the box reaches
    pixels it does not show. That raster settles what belongs in the off-canvas
    column too: nothing. The stroke is inner-aligned, so it lies inside a path
    whose left edge is x = 0, and the column at x = -1 is padding. It used to
    come out as stroke only because aggdraw dilated the fill a quarter pixel
    into it (#844).
    """
    psd = PSDImage.open(full_name("transparency/transparency-group.psd"))
    layer = list(psd.descendants())[2]
    assert layer.name == "Rectangle 1" and layer.bbox == (-1, -1, 129, 129)
    assert layer.stroke is not None and layer.stroke.line_alignment == "inner"

    color, _, alpha = composite(layer, force=True)
    alpha = np.asarray(alpha)[..., 0]
    assert color.shape == (130, 130, 3)

    # Photoshop's raster of this layer, to the last bit of the mantissa.
    stored_shape = layer.numpy("shape")
    stored_color = layer.numpy("color")
    assert stored_shape is not None and stored_color is not None
    assert np.allclose(alpha, stored_shape[..., 0], atol=1e-6)
    # Colour only where there is enough coverage for it to mean anything:
    # below a quantization step the compositor leaves whatever it last had.
    opaque = alpha > 1 / 255
    assert opaque.sum() > 16000
    assert np.array_equal(color[opaque], stored_color[opaque])

    # The box is the path grown by the stroke width, so its first and last
    # row and column are padding: x = -1 and x = 128, y = -1 and y = 128, all
    # outside a path that spans 0 to 128. Photoshop leaves them empty and so
    # does this, where the dilated fill used to put a quarter pixel there.
    assert alpha[:, 0].max() == 0.0 and alpha[0, :].max() == 0.0
    assert alpha[:, -1].max() == 0.0 and alpha[-1, :].max() == 0.0
    # Column 1 is x = 0, the first column on the canvas, and it is the black
    # stroke over its whole height -- not the white fill, which is what the
    # whole box came back as before #807.
    assert alpha[1:-1, 1].min() == 1.0, "the left edge lost its stroke"
    assert color[1:-1, 1].max() == 0.0, "the left edge is not the stroke colour"
    assert alpha[1, 1:-1].min() == 1.0, "the top edge lost its stroke"
    assert color[1, 1:-1].max() == 0.0, "the top edge is not the stroke colour"


def _pathless_reveal_all_layer() -> Layer:
    """The layer #823 names: an initial fill rule and no path to rule on."""
    psd = PSDImage.open(full_name("adjustment-fillers.psd"))
    layer = [x for x in psd.descendants() if x.name == "Color Fill 1"][0]
    assert layer.vector_mask is not None
    assert layer.vector_mask.initial_fill_rule and not layer.vector_mask.paths
    return layer


def _forged_pathless_stroke(disable_stroke: bool = False) -> tuple[PSDImage, Layer]:
    """``stroke.psd``'s stroked rectangle, with its paths stripped.

    No fixture carries the combination #823 describes, because Photoshop does
    not author a stroked shape layer whose reveal-all fill rule has no path
    under it. Forging it onto a layer that does have a stroke is enough.

    The strip empties the list behind ``VectorMask.paths`` while the fill rule
    writes through to the record; the mask is cached, so nothing rebuilds the
    one from the other.
    """
    psd = PSDImage.open(full_name("stroke.psd"))
    layer = [x for x in psd.descendants() if x.name == "Rectangle 1"][0]
    # Every term of ``_get_object()``'s stroke guard, so that an equality
    # below cannot come out true because the stroke was never drawn at all.
    assert layer.has_vector_mask()
    assert layer.stroke is not None and layer.stroke.enabled
    assert np.count_nonzero(vector.draw_stroke(layer)) > 0, (
        "the layer has no stroke raster for the forge to empty"
    )

    vm = layer.vector_mask
    assert vm is not None
    del vm.paths[:]
    vm.initial_fill_rule = 1
    # The setter is a no-op on a mask that carries no initial-fill-rule
    # record, which would leave the seed nothing to key on.
    assert vm.initial_fill_rule == 1 and len(vm.paths) == 0

    if disable_stroke:
        layer.stroke._data[b"strokeEnabled"] = Bool(False)
        assert not layer.stroke.enabled
    return psd, layer


def _nested_component(inner_alike: bool) -> tuple[PSDImage, Layer]:
    """Two nested rectangles forged into one component of a real layer.

    The layer is ``transparentbg.psd``'s only one, and its path is replaced
    outright.

    Photoshop does not author this: it cuts a hole by reversing the subpath
    that makes it, so every combined path in the corpus has its inner
    subpaths wound against the outer one, and even-odd and non-zero agree on
    all of them. Forging is the only way to reach the case that separates the
    two rules -- the same reason :py:func:`_forged_pathless_stroke` forges.
    """
    psd = PSDImage.open(full_name("transparentbg.psd"))
    layer = psd[0]
    setting = layer.tagged_blocks.get_data(Tag.VECTOR_MASK_SETTING1)

    def rectangle(box, clockwise, operation):
        x0, y0, x1, y1 = box
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        if not clockwise:
            corners.reverse()
        knots = []
        for x, y in corners:
            point = (y / psd.height, x / psd.width)  # knots are (y, x) fractions
            knots.append(ClosedKnotLinked(point, point, point))
        return ClosedPath(items=knots, operation=operation, index=0)

    keep = [x for x in setting.path if not isinstance(x, ClosedPath)]
    setting.path._items = keep + [
        rectangle(_OUTER, True, 1),
        rectangle(_INNER, inner_alike, -1),
    ]
    # ``Layer.vector_mask`` builds itself from the block above on first
    # access and caches it, so the block is edited before anything reads it.
    assert "_vector_mask" not in layer.__dict__
    return psd, layer


def test_photoshop_reads_a_combined_path_even_odd() -> None:
    """Which rule fills a combined path, settled by asking Photoshop.

    The corpus cannot answer it: Photoshop writes a hole as a subpath wound
    against its outer, where even-odd and non-zero agree, so all 17 combined
    paths in ``tests/psd_files`` score the same under either rule.

    So both windings were forged into this layer and Photoshop 2026 was given
    the files. It rasterized **both** to the same ring -- 3000 pixels, the
    4200 of the outer rectangle less the 1200 of the inner -- and our render
    of them matched its raster exactly, to 0.0 on every pixel. Non-zero would
    have filled the same-wound one solid at 4200. The PSD specification says
    the same thing, and so does
    :py:attr:`psd_tools.api.shape.VectorMask.paths` (#844).

    To redo it: save the forged document, open it in Photoshop, rasterize the
    layer, and read back the channel it leaves.
    """
    expected = (_OUTER[2] - _OUTER[0]) * (_OUTER[3] - _OUTER[1]) - (
        _INNER[2] - _INNER[0]
    ) * (_INNER[3] - _INNER[1])
    assert expected == 3000

    for alike in (True, False):
        psd, layer = _nested_component(inner_alike=alike)
        coverage = vector.draw_vector_mask(layer, (0, 0, psd.width, psd.height))[..., 0]
        assert coverage.sum() == pytest.approx(expected, abs=0.5), alike
        # The middle of the inner rectangle: empty whichever way it winds.
        assert coverage[75, 50] == 0.0, alike
        # And the band between the two rectangles is covered.
        assert coverage[75, 25] == 1.0, alike


def test_the_subpaths_of_one_component_are_filled_as_one_path() -> None:
    """A combined path is wound, not unioned (#844).

    ``masks.psd``'s social-media glyphs are the corpus's clearest case: each
    is one component whose inner subpath runs against the outer one and cuts
    the counter out of it. Drawn a subpath at a time and unioned, which is
    what aggdraw was asked to do, the counter fills in.

    The oracle is Photoshop's own raster of the layer, carried in its stored
    transparency channel, so this cannot come out true by construction.
    Filled as one path the error against it is 0.0014; unioned it is 0.1357,
    two orders away, and both bounds below sit between the two with a factor
    of ten either side.
    """
    psd = PSDImage.open(full_name("masks.psd"))
    layer = [x for x in psd.descendants() if x.name == "twitter"][0]
    assert layer.vector_mask is not None
    subpaths = layer.vector_mask.paths
    assert sum(1 for x in subpaths if x.operation == -1) > 0, (
        "the glyph is not a combined path, so nothing here is about winding"
    )

    stored = layer.numpy("shape")
    assert stored is not None
    coverage = vector.draw_vector_mask(layer, layer.bbox)[..., 0]
    assert float(np.abs(coverage - stored[..., 0]).mean()) < 0.01

    # The counter itself, away from its antialiased rim: Photoshop leaves 932
    # pixels of this glyph empty, where filling as one path reaches 0.0101 and
    # unioning reaches a flat 1.0.
    counter = stored[..., 0] < 0.01
    assert counter.sum() > 500, "no counter to lose"
    assert float(coverage[counter].max()) < 0.1


def test_pen_over_zero_paths_draws_nothing() -> None:
    """A stroke with no path to outline comes back empty.

    ``_draw_path()`` seeds its plane as covered when the vector mask has an
    initial fill rule and carries no paths. That seed describes a *fill*, and
    applied to a pen it returned the whole viewport as stroke coverage
    (#823, #832).
    """
    layer = _pathless_reveal_all_layer()
    pen = vector._draw_path(layer, pen={"color": 255, "width": 1.0})
    assert np.count_nonzero(pen) == 0, (
        f"a stroke over zero paths drew {np.count_nonzero(pen)} pixels"
    )


def test_draw_vector_mask_over_zero_paths_reveals_all() -> None:
    """The same seed is right for a brush, and gating it must not take it away.

    A vector mask with an initial fill rule and no path of its own reveals the
    whole layer, so the fill it describes covers the viewport (#823).
    """
    layer = _pathless_reveal_all_layer()
    mask = vector.draw_vector_mask(layer)
    assert mask.shape == (512, 512, 1)
    assert mask.min() == 1.0 and mask.max() == 1.0


def test_stroke_over_zero_paths_leaves_the_render_alone() -> None:
    """The seed reached the way a user reaches it, through the compositor.

    #823 arrives through ``_get_stroke()`` -> ``draw_stroke()`` ->
    ``_draw_path()``, the chain #807 and #822 changed the blast radius of. An
    empty stroke has to render as no stroke at all, which is the reference
    here -- no rasterized constant to go stale, and since both arms rasterize
    the same paths for the other four layers, aggdraw drift cancels and the
    measured difference is 0.

    Both viewports are pinned because #807 is what made them differ, and
    both under ``force=True``: without it the fill is not drawn from the
    vector mask and the two renders land within a quantization step of each
    other either way. Even there the tempting per-layer assertion is the
    vacuous one -- the forced layer render comes back with a uniform alpha of
    194 whether or not the seed is gated, and only its colour moves.
    """
    _, layer = _forged_pathless_stroke()
    assert np.count_nonzero(vector.draw_stroke(layer)) == 0, (
        "a stroke over zero paths covers the whole viewport"
    )

    # On the layer's own box every value moves when the seed leaks into the
    # pen; on the canvas, which the layer covers a corner of, 4.6% of them do.
    assert np.allclose(
        composite(_forged_pathless_stroke()[1], force=True)[0],
        composite(_forged_pathless_stroke(disable_stroke=True)[1], force=True)[0],
        atol=1 / 255,
    ), "an empty stroke does not render as no stroke on the layer"
    assert np.allclose(
        composite(_forged_pathless_stroke()[0], force=True)[0],
        composite(_forged_pathless_stroke(disable_stroke=True)[0], force=True)[0],
        atol=1 / 255,
    ), "an empty stroke does not render as no stroke on the document"


def test_pen_raster_of_stroked_layers_keeps_both_extremes() -> None:
    """A pen raster of layers that do have paths keeps both of its extremes.

    Every stroked layer in ``stroke.psd`` has ``initial_fill_rule == 0``,
    asserted below, so the seed never ran for them either way: this does not
    discriminate #823 and is not meant to. What it pins is the two ways a
    fill-rule gate can go wrong for them -- a seed leaking into the pen
    leaves no uncovered pixel, and a gate that empties a real stroke leaves
    no covered one.

    Deliberately no pinned sums: aggdraw is not bit-stable across versions
    (see :py:func:`test_draw_stroke_reaches_outside_the_canvas`) and this test
    has no opinion about its numerics, while the background pixels it reads
    are untouched by the rasterizer, so ``min() == 0.0`` is exact.
    """
    psd = PSDImage.open(full_name("stroke.psd"))
    stroked = [x for x in psd.descendants() if x.stroke and x.stroke.enabled]
    assert {x.name for x in stroked} == {
        "Rectangle 1",
        "Rounded Rectangle 1",
        "Ellipse 1",
        "Polygon 1",
        "Shape 1",
    }
    for layer in stroked:
        assert layer.vector_mask is not None
        assert layer.vector_mask.initial_fill_rule == 0, layer.name
        pen = vector._draw_path(layer, pen={"color": 255, "width": 1.0})
        assert pen.min() == 0.0, layer.name
        assert np.count_nonzero(pen) > 0, layer.name


def test_fill_rule_inversions_stay_brush_gated() -> None:
    """The ``first and brush`` inversions for subtract and intersect.

    They operate on the seeded plane for a brush and are skipped for a pen.
    The new seed is gated the same way, so these sums must not move (#823).

    Only the last assertion discriminates that gating, and it needs no
    tolerance: ungating turns the empty pen plane into the drawn one, 0.0 to
    2.61, while leaving all three raster sums bit-identical. Those are a
    non-regression pin on the subtract and intersect arithmetic, which
    :py:func:`test_path_operations` otherwise only checks at 0.02 MSE.

    The brush sums are exact now that a fill is the area of the path rather
    than aggdraw's quarter-pixel dilation of it (#844): the masked rectangle
    is 9x9 on the pixel grid, and 81.0 is what 9x9 covers. It used to read
    90.129. The pen sum keeps its tolerance, because a pen is still aggdraw's
    and aggdraw is not bit-stable between versions.
    """
    psd = PSDImage.open(full_name("vector-mask2.psd"))
    masked = [x for x in psd.descendants() if x.name == "Masked Rectangle 1"][0]
    assert masked.vector_mask is not None
    assert masked.vector_mask.initial_fill_rule and len(masked.vector_mask.paths) == 1
    brush = vector._draw_path(masked, brush={"color": 255})
    assert brush.sum() == pytest.approx(81.0, abs=1e-4)
    pen = vector._draw_path(masked, pen={"color": 255, "width": 1.0})
    assert pen.sum() == pytest.approx(35.843136, rel=0.01)

    filled = [x for x in psd.descendants() if x.name == "Color Fill 1"][0]
    vm = filled.vector_mask
    assert vm is not None
    assert vm.initial_fill_rule and [p.operation for p in vm.paths] == [3, 3]
    assert vector._draw_path(filled, brush={"color": 255}).sum() == pytest.approx(
        11.907392, rel=0.01
    )
    assert vector._draw_path(filled, pen={"color": 255, "width": 1.0}).sum() == 0.0
