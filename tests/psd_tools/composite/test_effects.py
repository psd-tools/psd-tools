import logging
import math
import warnings
from pathlib import Path
from typing import Callable

import numpy as np
import pytest
from PIL import Image

from psd_tools.api.psd_image import PSDImage
from psd_tools.composite import _compat, composite, effects
from psd_tools.composite.effects import (
    _BANDS,
    _grow,
    _distance_band,
    _signed_distance,
    stroke_bbox,
)
from psd_tools.constants import Tag
from psd_tools.psd.descriptor import Descriptor, Double, Enumerated, List
from psd_tools.terminology import Enum, Key, Klass

from ..utils import full_name
from .test_composite import _mse, check_composite_quality

logger = logging.getLogger(__name__)


@pytest.mark.xfail
def test_stroke_effects_xfail() -> None:
    """The largest stroke xfail, and the one #846 now accounts for.

    ``stroke-effects.psd``'s stroke-bearing layers are 20-24 px shapes with
    90-92% of their covered pixels at partial alpha, and the ramps are stored
    in the file rather than produced here -- so it is a fixture about soft
    alpha before it is one about strokes. Reading the boundary off coverage
    moved it from 0.120 to 0.093 (#799); what is left of it is the effect
    being composited onto the backdrop rather than into the layer (#846).
    """
    check_composite_quality("effects/stroke-effects.psd", threshold=0.01)


def test_a_partly_antialiased_shape_keeps_its_stroke_close() -> None:
    """``shape-fx2.psd`` is a polygon with a 4 px inset stroke (#799).

    14% of its covered pixels are at partial alpha, all of them along the
    antialiased edges of the polygon, so it is the one fixture the corpus
    already had that could tell the coverage reading from the iso-contour
    one -- and it halves, 1.86e-3 to 8.18e-4, without a fixture being authored
    for it. Asserted at 1e-3 rather than the 0.01 it sat at as an xfail, which
    is the bound that separates the two readings.
    """
    check_composite_quality("effects/shape-fx2.psd", threshold=1e-3)


@pytest.mark.parametrize("force", [False, True])
def test_stroke_traces_the_layer_where_it_runs_off_the_canvas(force: bool) -> None:
    """A stroke follows the layer's edge, not the edge of the canvas (#804).

    ``stroke-effect-transparent-shape.psd`` is a 32x32 document holding one
    shape layer with bbox ``(-2, -2, 34, 34)``, a path running ``(-1, -1)`` to
    ``(33, 33)`` and a 4 px inset stroke, so the rectangle's left edge is a
    pixel off-canvas. The compositor handed the stroke a copy of the coverage
    clipped to its own viewport, where that pixel had been zero-filled, and
    the ring landed on ``0..3`` measured from the canvas edge instead of on
    ``-1..2`` measured from the layer's.

    Both force modes, because they reach the coverage by different routes:
    the stored alpha channel, and the vector mask redrawn from the path. Which
    is also why only the stored one is pixel-exact. aggdraw paints a 0.247
    coverage fringe outside a path whose vertices are all integers (#844), and
    a stroke reads the boundary off coverage (#799), so under ``force=True``
    the ring's inner edge sits a quarter of a pixel further in. That is the
    raster being a quarter pixel wide, not the ring being in the wrong place,
    so what is asserted per force mode is the placement -- which is all #804
    was ever about -- and the exact bound stays on the mode that can meet it.
    """
    psd = PSDImage.open(full_name("effects/stroke-effect-transparent-shape.psd"))
    result = composite(psd, force=force)[0]

    # Three columns of stroke and then the layer's green interior. The pixels
    # rather than the error alone: at 4 px wide the ring is off by one column,
    # which a whole-image bound only registers as "smaller".
    stroke, interior = result[16, 1], result[16, 3]
    assert np.allclose(stroke, result[16, 0], atol=1 / 255.0)
    assert not np.allclose(stroke, interior, atol=1 / 255.0)
    assert np.allclose(interior, result[16, 4], atol=1 / 255.0)

    if not force:
        # Two orders of magnitude over the 1.3e-11 measured, and eight under
        # the 0.022 this fixture sat at while it was an xfail.
        assert _mse(psd.numpy(), result) <= 1e-9
    else:
        # One column, shaded 0.15 out by #844's fringe; 1.5e-3 measured.
        assert _mse(psd.numpy(), result) <= 3e-3


def test_stroke_ignores_a_viewport_narrower_than_the_layer() -> None:
    """Asking for less of a layer must not move its stroke (#804).

    No off-canvas geometry needed: a viewport that cuts through the layer used
    to zero-fill the rest of the coverage the same way, so the stroke was
    traced down the cut as if the square ended there. The wide render is the
    reference because it is the one the fixture's own test already pins to
    Photoshop.
    """
    psd = PSDImage.open(full_name("effects/center-stroke-sizes.psd"))
    layer = next(sub for sub in psd if sub.name == "Size 7")
    assert layer.bbox == (144, 16, 160, 32)

    wide = composite(layer, viewport=(140, 12, 164, 36), as_layer=True)
    cut = composite(layer, viewport=(140, 12, 152, 36), as_layer=True)
    for name, w, c in zip(("color", "shape", "alpha"), wide, cut):
        assert np.array_equal(c, w[:, :12]), name


def test_double_stroke_effects() -> None:
    """Two stroke effects on one layer render close to Photoshop (#798)."""
    check_composite_quality("effects/double-stroke-effects.psd", threshold=0.01)


@pytest.mark.parametrize(
    ("filename",),
    [
        ("effects/shape-fx.psd",),
    ],
)
def test_effects_disabled(filename: str) -> None:
    check_composite_quality(filename, threshold=0.01)


def test_outside_stroke_reaches_outside_bbox() -> None:
    """An outset stroke is drawn outside the layer it outlines (#792).

    ``outside-stroke.psd`` is a 16x16 pixel square whose content fills its
    bounding box exactly, with a 3 px outset stroke -- so the entire stroke
    falls outside the box, and drawing it on the box alone loses all of it.
    The alpha bounds are asserted rather than only the error, because a stroke
    dropped in full and a stroke merely mis-shaded both raise the error while
    only the former moves the bounds.
    """
    psd = PSDImage.open(full_name("effects/outside-stroke.psd"))
    assert psd[0].bbox == (8, 8, 24, 24)
    # Photoshop's own preview of this file, i.e. the 3 px stroke on every side.
    expected = (5, 5, 27, 27)
    preview = psd.topil()
    assert preview is not None
    assert preview.getchannel("A").getbbox() == expected
    composited = psd.composite(ignore_preview=True)
    assert composited is not None
    assert composited.getchannel("A").getbbox() == expected
    check_composite_quality("effects/outside-stroke.psd", threshold=0.01)


def test_outside_stroke_fills_expanded_viewport() -> None:
    """An explicitly widened viewport receives the stroke, not just padding.

    This is the shape the report took: growing the viewport used to add
    transparent margin and nothing else, because the stroke was drawn on the
    layer's bounding box no matter how much room the viewport offered.
    """
    psd = PSDImage.open(full_name("effects/outside-stroke.psd"))
    layer = psd[0]
    left, top, right, bottom = layer.bbox
    padding = 3
    image = layer.composite(
        viewport=(left - padding, top - padding, right + padding, bottom + padding)
    )
    assert image is not None
    assert image.size == (22, 22)
    assert image.getchannel("A").getbbox() == (0, 0, 22, 22)


# How far a centered stroke of each nominal size reaches outside the layer, read
# off Photoshop's own render of ``center-stroke-sizes.psd``. The progression is
# ceil(size / 2), which is what makes it a formula rather than one measurement:
# an implementation that truncated instead reached 1 px for every odd size.
_CENTERED_REACH = {1: 1, 2: 1, 3: 2, 5: 3, 7: 4}

# How far around a square to look when measuring its stroke. Wide enough that
# no stroke here fills it -- _outward_reach() asserts that, because a window
# the coverage touches reports a lower bound rather than a measurement.
_PAD = 12


def _outward_reach(
    alpha: np.ndarray, bbox: tuple[int, int, int, int]
) -> tuple[int, int, int, int]:
    """How far non-zero alpha extends past ``bbox``, per side.

    Measured in absolute coordinates within a window ``_PAD`` px around
    ``bbox``. The window is clamped to the canvas, since a negative slice bound
    would otherwise index from the far edge and quietly measure another square.
    """
    left, top, right, bottom = bbox
    height, width = alpha.shape
    x0, y0 = max(left - _PAD, 0), max(top - _PAD, 0)
    x1, y1 = min(right + _PAD, width), min(bottom + _PAD, height)
    assert (left - x0, top - y0, x1 - right, y1 - bottom) == (_PAD,) * 4, (
        f"{bbox} sits within {_PAD} px of the canvas edge, so the window that "
        f"measures it is clipped and the reach it reports is a lower bound"
    )

    ys, xs = np.nonzero(alpha[y0:y1, x0:x1])
    assert len(xs), f"no coverage at all within {_PAD} px of {bbox}"
    reach = (
        left - (x0 + int(xs.min())),
        top - (y0 + int(ys.min())),
        (x0 + int(xs.max()) + 1) - right,
        (y0 + int(ys.max()) + 1) - bottom,
    )
    assert max(reach) < _PAD, (
        f"coverage reaches the edge of the measuring window around {bbox}, so "
        f"{reach} is a lower bound rather than the real reach"
    )
    return reach


def test_centered_stroke_reach_matches_photoshop() -> None:
    """A centered stroke straddles the layer edge as far as Photoshop's (#792).

    ``center-stroke-sizes.psd`` holds five squares carrying centered strokes of
    1, 2, 3, 5 and 7 px. Every side of every square is checked against the same
    measurement taken from Photoshop's own render of the file, so this pins the
    whole progression rather than a single size -- the defect it covers was a
    truncated dilation radius, which was correct at 1, 2 and 4 px and wrong at
    every odd size above.
    """
    psd = PSDImage.open(full_name("effects/center-stroke-sizes.psd"))
    preview = psd.topil()
    composited = psd.composite(ignore_preview=True)
    assert preview is not None and composited is not None
    reference = np.asarray(preview.convert("RGBA"), dtype=np.uint8)[:, :, 3]
    result = np.asarray(composited.convert("RGBA"), dtype=np.uint8)[:, :, 3]

    measured = {}
    for layer in psd:
        strokes = list(layer.effects.find("stroke"))
        if not strokes:  # The empty layer the document was created with.
            continue
        # Effects.find() is typed as the base _Effect; ``size`` lives on the
        # concrete Stroke class it actually returns.
        size = int(getattr(strokes[0], "size"))
        expected = _outward_reach(reference, layer.bbox)
        assert expected == (_CENTERED_REACH[size],) * 4, (
            f"Photoshop's own render of the {size} px stroke moved"
        )
        assert _outward_reach(result, layer.bbox) == expected, (
            f"{size} px centered stroke does not reach as far as Photoshop's"
        )
        measured[size] = expected[0]
    assert measured == _CENTERED_REACH

    check_composite_quality("effects/center-stroke-sizes.psd", threshold=0.01)


# How deep an inset stroke of each nominal size reaches into the layer, read
# off Photoshop's own render of ``inset-stroke-sizes.psd``. The progression is
# the size itself, unrounded: the ring is exactly as many pixels thick as the
# stroke asks for, which is what makes the anchor a measurement rather than a
# fit. An anchor half a pixel out lands the ring on a fractional coverage
# instead, and one a whole pixel out changes every number in the table.
_INSET_DEPTH = {1: 1, 2: 2, 3: 3, 5: 5, 7: 7}


def _inward_depth(
    stroke: np.ndarray, bbox: tuple[int, int, int, int]
) -> tuple[int, ...]:
    """How far solid stroke runs inward from each side of ``bbox``.

    Measured along the middle row and column, so the count is the thickness of
    one side of the ring rather than anything about its corners.
    """
    left, top, right, bottom = bbox
    row, column = stroke[(top + bottom) // 2], stroke[:, (left + right) // 2]

    def run(values: np.ndarray) -> int:
        outside = np.flatnonzero(~values)
        return int(outside[0]) if len(outside) else len(values)

    return (
        run(row[left:right]),
        run(column[top:bottom]),
        run(row[left:right][::-1]),
        run(column[top:bottom][::-1]),
    )


def test_inset_stroke_depth_matches_photoshop() -> None:
    """An inset stroke reaches as far into the layer as Photoshop's (#799).

    ``inset-stroke-sizes.psd`` sweeps inset sizes the way
    ``center-stroke-sizes.psd`` sweeps centered ones: five 16x16 squares
    carrying inset strokes of 1, 2, 3, 5 and 7 px. It is the fixture that
    settles where Photoshop anchors an inset stroke, which #799 opened
    undecided -- the one hard-edged inset in the corpus before it appeared
    measured a *clipped* layer, and made the anchor look a pixel out.

    The whole progression is pinned rather than one size, because the anchors
    that were candidates differ from this one by a constant: half a pixel out
    and every ring picks up a fractional edge, a pixel out and every ring is
    the wrong thickness. Each of those four shifts fails this test.

    It pins the anchor and not the primitive, though: put the dilation back
    and the blob it draws still crosses this threshold at the same depth for
    all five sizes. What separates the two is
    :py:func:`test_hard_edged_stroke_matches_photoshop`, which reads every
    pixel rather than the depth of one run.
    """
    psd = PSDImage.open(full_name("effects/inset-stroke-sizes.psd"))
    preview = psd.topil(apply_icc=False)
    composited = psd.composite(ignore_preview=True, apply_icc=False)
    assert preview is not None and composited is not None
    # The stroke is the only red in the file, the squares under it being blue.
    reference = np.asarray(preview.convert("RGB"), dtype=np.int16)[:, :, 0] > 128
    result = np.asarray(composited.convert("RGB"), dtype=np.int16)[:, :, 0] > 128

    measured = {}
    for layer in psd:
        strokes = list(layer.effects.find("stroke"))
        if not strokes:  # The empty layer the document was created with.
            continue
        # Effects.find() is typed as the base _Effect; ``size`` lives on the
        # concrete Stroke class it actually returns.
        size = int(getattr(strokes[0], "size"))
        # The square fills its bounding box, so the layer has no uncovered
        # pixel of its own to measure an edge against. That is what made an
        # inset stroke vanish entirely until stroke_bbox() granted it one.
        coverage = layer.numpy("shape")
        assert coverage is not None and bool((coverage == 1.0).all()), (
            f"the {size} px square no longer covers its own bounding box, so "
            f"it no longer exercises the missing boundary pixel"
        )
        expected = _inward_depth(reference, layer.bbox)
        assert expected == (_INSET_DEPTH[size],) * 4, (
            f"Photoshop's own render of the {size} px stroke moved"
        )
        assert _inward_depth(result, layer.bbox) == expected, (
            f"{size} px inset stroke does not reach as deep as Photoshop's"
        )
        measured[size] = expected[0]
    assert measured == _INSET_DEPTH


def test_second_stroke_traces_the_layer() -> None:
    """Every stroke effect outlines the layer, not the stroke before it (#798).

    ``double-stroke-effects.psd`` is one rectangle carrying a red outset stroke
    and a blue inset stroke -- the only layer in the corpus with more than one.
    Tracing the second stroke from the first one's mask inset the red ring
    rather than the layer, which both left the blue ring unpainted and painted
    over the red one. Both rings are read off Photoshop's own render and both
    are checked, since the defect moves each of them for a different reason.
    """
    psd = PSDImage.open(full_name("effects/double-stroke-effects.psd"))
    # ICC is off on both sides: the fixture carries a profile, and the ring
    # pixel counts below are a calibration this test asserts exactly, so they
    # should not move with the installed color management library.
    preview = psd.topil(apply_icc=False)
    composited = psd.composite(ignore_preview=True, apply_icc=False)
    assert preview is not None and composited is not None
    reference = np.asarray(preview.convert("RGB"), dtype=np.int16)
    result = np.asarray(composited.convert("RGB"), dtype=np.int16)

    outset = (reference[:, :, 0] > 128) & (reference[:, :, 2] < 128)
    inset = (reference[:, :, 2] > 128) & (reference[:, :, 0] < 128)
    assert (int(outset.sum()), int(inset.sum())) == (104, 96), (
        "Photoshop's own render of the two rings moved, so the pixels this "
        "test measures are no longer the ones it was calibrated against"
    )

    # Well under the 221 the correct render reaches, and well over the 33 the
    # chained one left behind -- the gap is the whole ring, not a shading tweak.
    floor = 192
    assert int(result[:, :, 0][outset].min()) >= floor, (
        "the outset stroke is painted over, which is what happens when the "
        "inset stroke traces it instead of the layer"
    )
    assert int(result[:, :, 2][inset].min()) >= floor, (
        "the inset stroke is missing from the layer's inner edge, which is "
        "where it lands only when it traces the layer"
    )


@pytest.mark.parametrize(
    ("filename",),
    [
        ("effects/outside-stroke.psd",),
        ("effects/center-stroke-sizes.psd",),
        ("effects/inset-stroke-sizes.psd",),
        ("effects/double-stroke-effects.psd",),
    ],
)
def test_hard_edged_stroke_matches_photoshop(filename: str) -> None:
    """A stroke on a hard-edged mask lands where Photoshop puts it (#799).

    Every file here is squares with no partial alpha anywhere, so the boundary
    the stroke is measured from is a fact rather than a modelling choice. Every
    straight run of the stroke then matches Photoshop to the bit, because a
    ramp that is linear in distance is the exact area of a pixel cut by a
    straight edge. What is left is the corner arcs, where that ramp is only an
    approximation of a curved cut: 16 pixels of 1024 in the outset file and 24
    of 9216 in the centered one, differing by up to 0.073 and 0.110 coverage,
    which is why this asserts 1e-4 rather than equality.

    That is still 60x and 30x under what those two scored when the stroke was a
    dilated ``scharr`` edge -- 0.00626 and 0.00326 -- so the threshold
    separates the band from an approximation of it, which the 0.01 used
    elsewhere would not. The two inset files have no arc to approximate at all,
    an inset offset of a convex polygon being another polygon, and reproduce
    Photoshop bit for bit.
    """
    check_composite_quality(filename, threshold=1e-4)


def test_a_feathered_mask_takes_the_stroke_over_its_whole_ramp() -> None:
    """Photoshop's answer to #799's fourth item, rendered.

    ``feathered-stroke.psd`` is six 16x16 squares whose layer mask is a linear
    alpha ramp, carrying outset, inset and centered strokes at two sizes. It
    exists because nothing in the corpus could tell two boundary definitions
    apart: on a hard-edged mask the 0.5 iso-contour and the coverage reading
    name the same line, and every stroke fixture the corpus had was hard.

    The ramp columns are what separates them. Photoshop's stroke fades
    monotonically across the ramp because every pixel of it states where the
    boundary falls within itself; the iso-contour reading puts a ``size`` px
    band somewhere in the middle and leaves both ends bare, which shows up
    here as a profile that is not even monotone (0.157, 0.157, 0.443, 0.522,
    0.721, 0.658 against Photoshop's 0.196 .. 0.588).

    What is still off is the compositing, not the stroke: the band's coverage
    now equals Photoshop's, and the residue is psd-tools painting the effect
    onto the finished backdrop rather than into the layer (#846). That is
    worth up to 0.09 across the columns below, and it is why the shape of
    the profile is asserted tightly and its values are not.
    """
    psd = PSDImage.open(full_name("effects/feathered-stroke.psd"))
    reference = psd.numpy()[..., :3]
    result = composite(psd)[0]

    layer = next(sub for sub in psd if sub.name == "Outset 3")
    x0, y = layer.bbox[0], (layer.bbox[1] + layer.bbox[3]) // 2
    ramp = result[y, x0 : x0 + 6, 1]
    assert np.all(np.diff(ramp) > 0), (
        f"the stroke does not fade across the ramp: {ramp}"
    )
    assert np.allclose(ramp, reference[y, x0 : x0 + 6, 1], atol=0.1)

    # 1.6e-3 measured, against 2.2e-2 for the iso-contour reading.
    check_composite_quality("effects/feathered-stroke.psd", threshold=0.005)


def test_an_antialiased_edge_is_stroked_from_its_own_coverage() -> None:
    """One partial pixel moves the whole stroke, by exactly its coverage (#799).

    ``antialiased-stroke-edge.psd`` is six opaque 16x16 squares whose first and
    last columns carry a single antialiased pixel, at 25%, 50% and 75%. That
    pixel is the only thing that differs between the three, so where the
    stroke's far edge lands is a direct readout of how the boundary was
    located: from coverage it moves with it, and from the 0.5 iso-contour it
    snaps to the pixel edge and two of the three come out identical.

    The far edge rather than the whole square, because the interior is where
    #846 still costs a few percent. On ``main`` the three read 1.0000, 0.8627
    and 0.8627 against Photoshop's 0.9647, 0.9294 and 0.8980 -- the middle one
    a whole pixel of stroke too short, and the outer two indistinguishable.
    """
    psd = PSDImage.open(full_name("effects/antialiased-stroke-edge.psd"))
    reference = psd.numpy()[..., :3]
    result = composite(psd)[0]

    fringes = []
    for layer in psd:
        if not layer.name.startswith("Outset"):
            continue
        x1, y = layer.bbox[2], (layer.bbox[1] + layer.bbox[3]) // 2
        assert result[y, x1 + 2, 0] == pytest.approx(
            reference[y, x1 + 2, 0], abs=2 / 255.0
        ), layer.name
        fringes.append(float(result[y, x1 + 2, 0]))
    # Monotone in the coverage, which is the property the iso-contour loses.
    assert np.all(np.diff(fringes) < 0), fringes

    # 6.0e-4 measured, against 1.7e-3 for the iso-contour reading -- a whole
    # -image bound is the weaker half of this test, which is why the pixels
    # above are asserted at all.
    check_composite_quality("effects/antialiased-stroke-edge.psd", threshold=0.001)


def test_distance_band_covers_its_width_on_a_pixel_boundary() -> None:
    """A stroke of width *w* covers *w* pixels of coverage, fractional *w* too.

    The dilation pen this replaced was built from ``disk(r)`` with an integer
    ``r``, so a 3 px centered stroke could only reach 1 px or 2 px per side and
    never the 1.5 it asks for -- #796 fixed that by rounding to the better of
    two wrong integers. A band in a distance field has no such step, and this
    pins the property that makes it worth having.

    The boundary here falls exactly on a pixel edge, which is the case the
    identity holds for. Where it cuts through a pixel instead, that pixel is
    reseeded from its own coverage and the reseeding does not re-propagate, so
    the field stops being 1-Lipschitz just where the band sits and the total
    drifts by up to half a pixel. That is a property of the primitive as #799
    specifies it, and squaring it away is that issue's fourth tracking item.
    """
    # A single hard vertical edge, covered on the left and empty on the right.
    alpha = np.zeros((1, 12), dtype=np.float32)
    alpha[:, :6] = 1.0
    distance = _signed_distance(alpha)
    # Pixel centres sit half a pixel off the boundary, and the sign says which
    # side: this is the measurement everything below is derived from.
    assert distance[0].tolist() == [
        -5.5,
        -4.5,
        -3.5,
        -2.5,
        -1.5,
        -0.5,
        0.5,
        1.5,
        2.5,
        3.5,
        4.5,
        5.5,
    ]

    for width in (0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        outset = float(_distance_band(distance, 0.0, width).sum())
        assert outset == pytest.approx(width), f"outset stroke of {width} px"
        inset = float(_distance_band(distance, -width, 0.0).sum())
        assert inset == pytest.approx(width), f"inset stroke of {width} px"
        centered = float(_distance_band(distance, -width / 2.0, width / 2.0).sum())
        assert centered == pytest.approx(width), f"centered stroke of {width} px"


def test_centered_band_straddles_the_edge_evenly() -> None:
    """A centered stroke puts half its width on each side of the boundary.

    Asserted separately from the total width above, because a band anchored to
    one side would still total the right coverage while sitting entirely in the
    layer -- which is what an inset stroke is, not a centered one.
    """
    alpha = np.zeros((1, 12), dtype=np.float32)
    alpha[:, :6] = 1.0
    distance = _signed_distance(alpha)
    band = _distance_band(distance, -1.5, 1.5)[0]
    assert float(band[:6].sum()) == pytest.approx(1.5), "coverage inside the layer"
    assert float(band[6:].sum()) == pytest.approx(1.5), "coverage outside the layer"


def _stroke_descriptor(style: bytes, size: float) -> Descriptor:
    """The two keys :py:func:`draw_stroke_effect` reads to place a stroke."""
    color = Descriptor(classID=Klass.RGBColor.value)
    color[Key.Red] = Double(255.0)
    color[Key.Green] = Double(0.0)
    color[Key.Blue] = Double(0.0)
    desc = Descriptor(classID=b"FrFX")
    desc[Key.Style] = Enumerated(typeID=b"FStl", enum=style)
    desc[Key.SizeKey] = Double(size)
    desc[Key.PaintType] = Enumerated(typeID=b"FrFl", enum=Enum.SolidColor)
    desc[Key.Color] = color
    return desc


@pytest.mark.parametrize(
    "style",
    [Enum.OutsetFrame, Enum.InsetFrame, Enum.CenteredFrame, b"nope"],
    ids=["outset", "inset", "centered", "unrecognised"],
)
@pytest.mark.parametrize("size", [0.0, -1.0], ids=["zero", "negative"])
def test_a_stroke_of_no_width_draws_nothing(style: bytes, size: float) -> None:
    """A stroke sized 0 is invisible, not an exception (#805 review).

    Photoshop's own UI will not author one, but ``Stroke.size`` defaults to 0.0
    at the API level and a descriptor can carry it, so both primitives have to
    survive it. Neither did on its own: the dilation's pen is ``disk(-1)``,
    which comes back empty and makes the rank filter it feeds assert; and the
    band, whose limits collapse to a point, paints a quarter of a pixel
    wherever the boundary falls exactly on a pixel centre.

    Both halves are covered here -- the hard-edged square for the pen, the
    half-covered pixel for the band -- because each path only fails on one of
    them, and a square alone lets the band through.
    """
    psd = PSDImage.open(full_name("effects/outside-stroke.psd"))
    square = np.zeros((9, 9, 1), dtype=np.float32)
    square[3:6, 3:6] = 1.0
    # An exactly half-covered pixel sits at distance 0, which is where the
    # collapsed band leaks; the square has no pixel there at all.
    straddled = np.zeros((1, 8, 1), dtype=np.float32)
    straddled[:, :4] = 1.0
    straddled[:, 4] = 0.5

    for shape, viewport in ((square, (0, 0, 9, 9)), (straddled, (0, 0, 8, 1))):
        _, mask = effects.draw_stroke_effect(
            viewport, shape, _stroke_descriptor(style, size), psd
        )
        assert float(mask.sum()) == 0.0, f"{style!r} stroke of {size} px painted"


def test_inset_band_sits_wholly_inside_the_layer() -> None:
    """An inset stroke puts all of its width on the layer's side of the edge.

    The counterpart of the centered assertion above. Both name their limits
    outright, so what they pin is the primitive -- all three positions are one
    band and only the anchor tells them apart -- and not which limits
    :py:func:`draw_stroke_effect` picks, which the fixtures cover. Asserted
    apart from the total width, because an anchor a pixel out still totals the
    right coverage while hanging off the edge of the layer.
    """
    alpha = np.zeros((1, 12), dtype=np.float32)
    alpha[:, :6] = 1.0
    distance = _signed_distance(alpha)
    band = _distance_band(distance, -3.0, 0.0)[0]
    assert float(band[:6].sum()) == pytest.approx(3.0), "coverage inside the layer"
    assert float(band[6:].sum()) == 0.0, "coverage outside the layer"


@pytest.mark.parametrize("size", [1.0, 2.0, 3.0, 7.0])
def test_stroke_bbox_grants_the_inset_the_pixel_it_measures_from(size: float) -> None:
    """An inset stroke needs canvas too, for the edge rather than the stroke.

    A layer whose pixels fill its bounding box -- a filled rectangle, which is
    what ``inset-stroke-sizes.psd`` is made of -- offers the band no uncovered
    pixel to locate a boundary against, and ``_signed_distance`` correctly
    reports the whole box as boundaryless. The stroke then vanishes outright,
    which is the inset twin of the outset clipping #792 fixed. One pixel is
    both necessary and enough: the distance to the nearest uncovered pixel does
    not change once the first ring of them is there.
    """
    desc = _stroke_descriptor(Enum.InsetFrame, size)
    bbox = (10, 10, 30, 30)
    assert stroke_bbox(bbox, desc) == (9, 9, 31, 31)

    filled = np.ones((bbox[3] - bbox[1], bbox[2] - bbox[0]), dtype=np.float32)
    assert float(_distance_band(_signed_distance(filled), -size, 0.0).sum()) == 0.0

    granted = np.zeros((filled.shape[0] + 2, filled.shape[1] + 2), dtype=np.float32)
    granted[1:-1, 1:-1] = filled
    band = _distance_band(_signed_distance(granted), -size, 0.0)
    # The ring of a 20x20 square: the whole square once the stroke is wide
    # enough to close over the middle, and four sides of ``size`` px until then.
    expected = 20**2 - max(20 - 2 * size, 0) ** 2
    assert float(band.sum()) == pytest.approx(expected)
    assert float(band[0].sum()) == 0.0, "the stroke spilled onto the granted pixel"


@pytest.mark.parametrize("size", [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 7.0, 7.5, 10.0])
def test_band_fits_the_canvas_stroke_bbox_asks_for(size: float) -> None:
    """The band never reaches past the margin :py:func:`stroke_bbox` grants.

    That margin is what keeps an outset or centered stroke from being clipped
    to the layer's own bounding box (#792). On a hard-edged mask the band
    reaches exactly one pixel less than the margin at every size, so equality
    is asserted rather than a bound.

    The expected margin is written out per style rather than read back out of
    ``_BANDS``, which is the table the band itself comes from: deriving both
    sides from it made this pass with the outset band widened to twice its
    size, and with :py:func:`stroke_bbox` returning its argument untouched.
    """
    expected = {
        Enum.OutsetFrame: math.ceil(size) + 1,
        Enum.CenteredFrame: math.ceil(size / 2.0) + 1,
        Enum.InsetFrame: 1,
    }
    pad = 40
    alpha = np.zeros((2 * pad + 20, 2 * pad + 20), dtype=np.float32)
    alpha[pad : pad + 20, pad : pad + 20] = 1.0
    distance = _signed_distance(alpha)

    for style, margin in expected.items():
        bbox = stroke_bbox((0, 0, 20, 20), _stroke_descriptor(style, size))
        assert bbox == (-margin, -margin, 20 + margin, 20 + margin), style

        lo, hi = _BANDS[style]
        band = _distance_band(distance, lo * size, hi * size)
        ys, xs = np.nonzero(band)
        # All four sides, not just the horizontal pair: the mask is square, so
        # a band that reached unevenly would otherwise go unnoticed.
        reach = max(
            pad - int(xs.min()),
            int(xs.max()) + 1 - (pad + 20),
            pad - int(ys.min()),
            int(ys.max()) + 1 - (pad + 20),
        )
        assert reach == margin - 1, (
            f"{style!r} stroke of {size} px reaches {reach} px outside the "
            f"layer, against the {margin} px stroke_bbox() reserves for it"
        )


@pytest.mark.parametrize("alpha", [0.0, 1.0], ids=["transparent", "opaque"])
def test_a_mask_with_no_coverage_to_read_draws_no_stroke(alpha: float) -> None:
    """A stroke needs a boundary to trace, and a flat 0 or 1 mask has none (#799).

    ``distance_transform_edt`` is undefined on an input with no zeros: rather
    than refusing, it reports distances to a phantom feature off the array
    corner, and a band built on those paints a wedge of full-coverage stroke
    into the corner of the canvas. Nothing in the fixture corpus has a
    boundaryless mask, so no rendering comparison can catch this and only this
    test does.

    Only 0 and 1 qualify. A mask flat at some *partial* value is boundaryless
    in the 0.5 iso-contour's terms but not in coverage's: every one of its
    pixels states where the boundary falls within itself, which is what the
    test below pins.
    """
    flat = np.full((9, 9), alpha, dtype=np.float32)
    distance = _signed_distance(flat)
    # Uniformly infinitely far from a boundary that is not there.
    assert not np.isfinite(distance).any()
    for limits in ((0.0, 3.0), (-1.5, 1.5)):
        band = _distance_band(distance, *limits)
        assert float(band.sum()) == 0.0, f"stroke painted on a flat {alpha} mask"


@pytest.mark.parametrize("alpha", [0.3, 0.9], ids=["below-half", "above-half"])
def test_a_flat_partial_mask_is_stroked_at_its_own_coverage(alpha: float) -> None:
    """A mask flat at a partial value is half-covered everywhere (#799).

    Photoshop reads a stroke's boundary off coverage, so a pixel at 0.3 says
    the boundary runs 0.3 of the way into it wherever that pixel sits -- and a
    mask that says so everywhere gets an outset stroke of ``1 - alpha`` over
    all of it, with nothing left over to fall off. That is not an artefact of
    the uniform case: ``feathered-stroke.psd``'s ramps reach ``1 - alpha``
    across their whole width, and the plateau that measured this reaches it
    16 px from any edge.

    Uniformity is the property worth asserting either way. The phantom-feature
    failure the test above guards against shows up as a wedge, which a single
    summed total would hide.
    """
    flat = np.full((9, 9), alpha, dtype=np.float32)
    distance = _signed_distance(flat)
    assert np.allclose(distance, 0.5 - alpha)
    outset = _distance_band(distance, 0.0, 3.0)
    assert np.allclose(outset, 1.0 - alpha)
    inset = _distance_band(distance, -3.0, 0.0)
    assert np.allclose(inset, alpha)


def test_a_feathered_mask_is_stroked_across_its_whole_ramp() -> None:
    """A wide alpha ramp takes a stroke over all of it, not a band inside it.

    Photoshop was asked (#799 item 4), with masks whose alpha is a linear ramp
    of a known width: it reads the boundary off *coverage*, so every pixel of
    a 32 px ramp is within half a pixel of the boundary it states, and a
    stroke of any size covers the lot. An outset stroke comes out at
    ``1 - alpha`` there and an inset one at ``alpha``, whatever its size --
    the size only says how far past the ramp the stroke reaches.

    This is the reverse of what psd-tools drew until the measurement: the 0.5
    iso-contour put a ``size`` px band in the middle of the ramp and left the
    rest of it bare. Nothing in the corpus could tell the two apart, which is
    why item 4 called for fixtures of its own; ``feathered-stroke.psd`` is
    the rendered half of this.
    """
    # Strictly inside 0 and 1: a pixel at either is fully covered or not
    # covered, and states nothing about where a boundary falls within it.
    ramp = np.tile(np.linspace(0.99, 0.01, 32, dtype=np.float32), (4, 1))
    distance = _signed_distance(ramp)
    assert np.allclose(distance, 0.5 - ramp)

    for size in (1.0, 3.0, 7.0):
        outset = _distance_band(distance, 0.0, size)
        assert np.allclose(outset, 1.0 - ramp), f"outset stroke of {size} px"
        inset = _distance_band(distance, -size, 0.0)
        assert np.allclose(inset, ramp), f"inset stroke of {size} px"


def test_a_hard_step_keeps_the_pixel_edge_it_has_no_coverage_for() -> None:
    """Where a mask steps 0 -> 1 there is no partial pixel to read (#799).

    Reading the boundary off coverage says nothing about an edge that has no
    coverage to read, and a mask can carry both: a shape antialiased along one
    side and butted against its own bounding box along another. The step keeps
    the pixel-edge boundary the Euclidean field gives it, which is what makes
    the change a no-op on every hard-edged fixture in the corpus.
    """
    alpha = np.zeros((4, 16), dtype=np.float32)
    alpha[:, 2:8] = 1.0  # a hard step at x=2, an antialiased edge at x=8
    alpha[:, 8] = 0.25
    distance = _signed_distance(alpha)
    # The step keeps the pixel edge: half a pixel out on each side of x=2.
    assert distance[0, 0] == pytest.approx(1.5)
    assert distance[0, 1] == pytest.approx(0.5)
    assert distance[0, 2] == pytest.approx(-0.5)
    assert distance[0, 3] == pytest.approx(-1.5)
    # The antialiased pixel states a quarter of the way into itself, and its
    # neighbours measure from there rather than from the pixel edge x=8 -- the
    # quarter pixel the two readings differ by is what moves the whole stroke.
    assert distance[0, 7] == pytest.approx(-0.75)
    assert distance[0, 8] == pytest.approx(0.25)
    assert distance[0, 9] == pytest.approx(1.25)
    # Column 5 is the same distance from the step and from the antialiased
    # pixel, and the coverage reading wins the tie. Asserted because turning
    # ``distance <= to_hard`` into ``<`` moves it to -2.5 and nothing else in
    # the file notices.
    assert distance[0, 5] == pytest.approx(-2.75)


def test_the_nearest_pixel_is_not_the_nearest_boundary() -> None:
    """A pixel measures from the closest boundary, not the closest seed (#799).

    Each partial pixel states a boundary up to half a pixel either side of its
    own centre, so a pixel one further away can state one a whole pixel
    nearer. Taking the nearest *pixel*'s word for it hands the answer to
    whichever of two equidistant ones ``distance_transform_edt`` happens to
    return, which is not a choice the mask makes: mirror the mask and the
    stroke moves.

    The numbers are Photoshop's. This row was authored as a layer mask and
    rendered with a 1 px outset stroke, and its mirror image separately; the
    two renders are identical to the bit, and the coverage they give is the
    band over exactly this field. On the middle pixel Photoshop puts 0.9
    coverage, where reading the nearest pixel puts 0.1.
    """
    row = np.zeros((1, 5), dtype=np.float32)
    row[0, 1], row[0, 3] = 0.1, 0.9
    distance = _signed_distance(row)
    assert distance[0].tolist() == pytest.approx([1.4, 0.4, 0.6, -0.4, 0.6])
    # The middle pixel is one away from both, and 0.9 - 0.5 = 0.4 out from the
    # left one against 0.5 - 0.9 = -0.4 out from the right one.
    assert distance[0, 2] == pytest.approx(0.6)
    assert np.allclose(distance, np.flip(_signed_distance(np.flip(row, 1)), 1))


def test_a_stroke_does_not_depend_on_which_way_the_mask_faces() -> None:
    """Mirroring a mask mirrors its stroke, on a fixture rather than a row.

    ``stroke-effects.psd``'s ellipses are 90% partial alpha, which is what it
    takes for two partial pixels to be equidistant from a third often enough
    to see: before the boundary was chosen by distance rather than by pixel,
    this layer's stroke moved by 0.228 coverage when the mask was flipped.
    Equality rather than a bound, because solving for the nearest boundary
    leaves nothing to break a tie over: every stroke-bearing layer in the
    corpus is now exactly symmetric, in all three positions, on both axes.
    """
    psd = PSDImage.open(full_name("effects/stroke-effects.psd"))
    layer = next(sub for sub in psd.descendants() if sub.name == "Shape Ellipse")
    shape = layer.numpy("shape")
    assert shape is not None
    alpha = shape[..., 0].astype(np.float32)
    assert ((alpha > 0) & (alpha < 1)).mean() > 0.5, "the fixture stopped being soft"

    # Scattered partial pixels of very different coverage, which is what it
    # takes to make the nearest pixel and the nearest boundary disagree in two
    # dimensions at once. Re-measuring against the neighbours narrowed this to
    # 0.026 coverage and did not close it; solving for the boundary does.
    scattered = np.zeros((5, 5), dtype=np.float32)
    scattered[2, 4], scattered[3, 3] = 0.01, 0.80
    scattered[4, 1], scattered[4, 2] = 0.99, 0.20

    for mask in (alpha, scattered):
        for limits in ((0.0, 3.0), (-3.0, 0.0), (-1.5, 1.5)):
            reach = max(abs(limits[0]), abs(limits[1])) + 1.0
            band = _distance_band(_signed_distance(mask, reach), *limits)
            for axis in (0, 1):
                turned = _signed_distance(np.flip(mask, axis), reach)
                flipped = _distance_band(turned, *limits)
                assert np.array_equal(band, np.flip(flipped, axis)), (limits, axis)


def test_a_mask_does_not_meet_itself_around_the_array_edge() -> None:
    """The first row is not the last row's neighbour (#799 review).

    :py:func:`_grow` marks the hard 0-to-1 steps, and rolling rather than
    slicing made a layer flush against one side of its viewport a neighbour of
    the transparency against the other -- which put a phantom boundary between
    them and measured the whole stroke from it. Nothing in the corpus reaches
    that, because :py:func:`stroke_bbox` grants a pixel of clear border on
    every side, so it takes a test of its own.
    """
    mask = np.zeros((1, 6), dtype=bool)
    mask[0, 5] = True
    assert _grow(mask)[0].tolist() == [False, False, False, False, True, True]

    opaque = np.zeros((4, 6), dtype=np.float32)
    opaque[:, 0] = 1.0  # opaque against one edge, clear against the other
    distance = _signed_distance(opaque)
    # Measured from the step at column 1, not from a boundary wrapped around.
    assert distance[0].tolist() == [-0.5, 0.5, 1.5, 2.5, 3.5, 4.5]


def test_every_stroke_position_draws_without_scikit_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A solid stroke of any position needs scipy, not scikit-image (#802).

    While the whole of :py:func:`draw_stroke_effect` was gated on
    scikit-image, a scipy-only install -- a platform with no scikit-image
    wheel, say -- failed to render *any* document carrying *any* stroke,
    because nothing upstream catches the ImportError and turns it into a
    missing effect. #802 freed the outset and centered positions by drawing
    them as bands, inset joined them once its anchor was measured, and the
    last holdout -- a position the descriptor states wrongly or not at all --
    joined them when the dilation it fell through to was dropped (#799).

    The unrecognised position is the case worth keeping here: the other three
    have fixtures of their own above, and it is the one that used to raise.
    """
    monkeypatch.setattr(_compat, "HAS_SKIMAGE", False)
    check_composite_quality("effects/outside-stroke.psd", threshold=1e-4)
    check_composite_quality("effects/center-stroke-sizes.psd", threshold=1e-4)
    check_composite_quality("effects/inset-stroke-sizes.psd", threshold=1e-4)

    shape = np.zeros((8, 8, 1), dtype=np.float32)
    shape[2:6, 2:6] = 1.0
    psd = PSDImage.open(full_name("effects/outside-stroke.psd"))
    omitted = _stroke_descriptor(b"nope", 2.0)
    del omitted[Key.Style]
    for desc in (_stroke_descriptor(b"nope", 2.0), omitted):
        _, mask = effects.draw_stroke_effect((0, 0, 8, 8), shape, desc, psd)
        assert mask.sum() > 0, "an unrecognised position drew nothing"


def test_a_stroke_asks_for_scipy_by_name_when_it_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one package a stroke still needs has to say so itself.

    Asserted because the obvious way to guard the band is ``@require_scipy``,
    whose message tells the reader to install scipy for *gradient fills* --
    accurate about the package and misleading about why.

    scikit-image is no longer on this path at all. It was the fallback for a
    position Photoshop does not write, and that fallback is gone: the band
    draws every position, a position the descriptor states wrongly or does not
    state included (#799). What is left of scikit-image in a stroke is the
    paint, not the shape -- a pattern fill needs it whatever the position,
    which :py:func:`test_a_pattern_stroke_still_needs_scikit_image` pins.
    """
    monkeypatch.setattr(effects, "HAS_SCIPY", False)
    with pytest.raises(ImportError, match="Stroke effects require: scipy"):
        check_composite_quality("effects/outside-stroke.psd", threshold=1.0)


def test_a_pattern_stroke_still_needs_scikit_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stroke's paint can need what its shape no longer does (#802)."""
    monkeypatch.setattr(_compat, "HAS_SKIMAGE", False)
    psd = PSDImage.open(full_name("effects/stroke-effects.psd"))
    pattern = next(layer for layer in psd.descendants() if layer.name == "Pattern")
    with pytest.raises(ImportError, match="scikit-image"):
        pattern.composite()


def _rendered(
    filename: str,
    kind: str = "stroke",
    mutate: Callable[[Descriptor], None] | None = None,
    *,
    nth: int | None = None,
) -> np.ndarray:
    """``filename`` composited after ``mutate`` has broken its effects.

    ``nth`` selects one effect per layer, counted over the enabled effects of
    that kind in the order the compositor draws them. The fixtures below that
    use it carry their effects on a single layer, so it names one effect in
    the document.
    """
    psd = PSDImage.open(full_name(filename))
    for layer in psd.descendants():
        for index, effect in enumerate(list(layer.effects.find(kind))):
            if mutate is not None and (nth is None or index == nth):
                mutate(effect.descriptor)
    return np.asarray(psd.composite(ignore_preview=True).convert("RGBA"))


def _disable(desc: Descriptor) -> None:
    desc[Key.Enabled] = False


# Every way an effect descriptor can defeat the reads that draw it, short of
# the ones the drawing now reads past. The first is the stroke's own width,
# the other two are the paint's, which ``_stroke_reach()`` never looks at at
# all -- so no amount of hardening the measurement would have caught them.
_UNDRAWABLE = {
    "size": lambda desc: desc.__setitem__(Key.SizeKey, "wide"),
    "infinite-size": lambda desc: desc.__setitem__(Key.SizeKey, Double(float("inf"))),
    "no-color": lambda desc: desc.pop(Key.Color),
    "color-class": lambda desc: setattr(desc[Key.Color], "classID", b"XXXX"),
}


@pytest.mark.parametrize("defect", sorted(_UNDRAWABLE), ids=sorted(_UNDRAWABLE))
def test_an_unreadable_stroke_is_dropped_and_the_document_still_renders(
    defect: str,
) -> None:
    """A descriptor that cannot be read costs its effect, not the render.

    Two of these are the stroke's own width and reach the guard that measures
    it: a size that will not parse (``ValueError`` from ``float()``) and one
    that parses but cannot be a margin (``OverflowError`` from ``math.ceil``,
    which no amount of validating the *type* would have caught). The other two
    are the paint's and reach the guard that draws it -- a missing colour
    descriptor, and a colour class that is none of the five -- which
    ``_stroke_reach()`` never reads at all, so no hardening of the measurement
    could have found them (#826).

    Asserted against the same document with the stroke switched off, not
    merely against "it did not raise": a stroke drawn at some invented width
    or in some invented colour would pass that weaker test.
    """
    assert np.array_equal(
        _rendered("effects/outside-stroke.psd", mutate=_UNDRAWABLE[defect]),
        _rendered("effects/outside-stroke.psd", mutate=_disable),
    )


@pytest.mark.parametrize(
    ("key", "type_id", "filename"),
    [
        (Key.Style, b"FStl", "effects/inset-stroke-sizes.psd"),
        (Key.PaintType, b"FrFl", "effects/outside-stroke.psd"),
    ],
    ids=["position", "paint"],
)
@pytest.mark.parametrize(
    "defect", ["absent", "wrong-type"], ids=["absent", "wrong-type"]
)
def test_an_unreadable_stroke_enum_draws_as_an_unrecognised_one(
    key: bytes, type_id: bytes, filename: str, defect: str
) -> None:
    """An enum the descriptor does not state joins the ones it states wrongly.

    Both enums a stroke is drawn from -- its position and its paint type --
    already answer for a value neither table names: the outset band for one, a
    white fill for the other. A key that is missing or holds a ``Double``
    cannot be told apart from a key naming something nobody implements, so it
    costs nothing to let them share that answer, and it buys a stroke that
    draws instead of an ``AttributeError`` out of ``desc.get(...).enum``
    (#826).

    Pinned against the unrecognised value at both ends -- not blank, and not
    what the fixture itself states -- because "it drew something" would pass
    for a missing key that had quietly become inset, or red. Which is why the
    position case reads a fixture stating *inset*: an unrecognised position is
    now drawn as an outset band rather than as a dilated edge of its own
    (#799), so pinning it against an outset fixture would assert nothing.
    """
    mutate: Callable[[Descriptor], None] = (
        (lambda desc: desc.pop(key))
        if defect == "absent"
        else (lambda desc: desc.__setitem__(key, Double(1.0)))
    )
    unrecognised = _rendered(
        filename,
        mutate=lambda desc: desc.__setitem__(
            key, Enumerated(typeID=type_id, enum=b"nope")
        ),
    )
    assert np.array_equal(_rendered(filename, mutate=mutate), unrecognised)
    assert not np.array_equal(unrecognised, _rendered(filename, mutate=_disable)), (
        "the fixture has to draw something for this to pin anything"
    )
    assert not np.array_equal(unrecognised, _rendered(filename)), (
        "an unreadable enum quietly became the one the fixture states"
    )


def test_an_unrecognised_stroke_position_draws_as_an_outset_one() -> None:
    """The widest of the three, which is the one already measured for (#799).

    The fallback used to be a primitive of its own -- a dilated ``scharr``
    edge, stretched back to full opacity -- which is gone now that the band
    draws every position Photoshop writes. Outset rather than either of the
    others because :py:func:`stroke_bbox` has always reserved the outset reach
    for a position it cannot read, so this is the one choice that cannot be
    clipped by the canvas it is handed.
    """
    outset = _rendered(
        "effects/inset-stroke-sizes.psd",
        mutate=lambda desc: desc.__setitem__(
            Key.Style, Enumerated(typeID=b"FStl", enum=Enum.OutsetFrame)
        ),
    )
    unrecognised = _rendered(
        "effects/inset-stroke-sizes.psd",
        mutate=lambda desc: desc.__setitem__(
            Key.Style, Enumerated(typeID=b"FStl", enum=b"nope")
        ),
    )
    assert np.array_equal(unrecognised, outset)
    # Not vacuous: the fixture states inset, so both renders had to move.
    assert not np.array_equal(outset, _rendered("effects/inset-stroke-sizes.psd"))


def test_an_unrecognised_stroke_position_says_so_in_the_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Drawing it as outset leaves nothing in the pixels to notice it by.

    The dilated edge it used to fall through to was visibly not any of the
    three positions, which made an unreadable descriptor its own diagnostic.
    An outset band is the right thing to draw and byte-identical to a stated
    one, so the only place left to say a position was not understood is here.
    """
    shape = np.zeros((8, 8, 1), dtype=np.float32)
    shape[2:6, 2:6] = 1.0
    psd = PSDImage.open(full_name("effects/outside-stroke.psd"))
    with caplog.at_level(logging.DEBUG, logger="psd_tools.composite.effects"):
        effects.draw_stroke_effect(
            (0, 0, 8, 8), shape, _stroke_descriptor(b"nope", 2.0), psd
        )
    assert any("nope" in record.message for record in caplog.records), caplog.text

    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="psd_tools.composite.effects"):
        effects.draw_stroke_effect(
            (0, 0, 8, 8), shape, _stroke_descriptor(Enum.OutsetFrame, 2.0), psd
        )
    assert not any("Unrecognised" in record.message for record in caplog.records)


def test_an_unreadable_stroke_leaves_the_other_stroke_on_the_layer() -> None:
    """One bad descriptor costs one effect, not every effect on the layer.

    ``double-stroke-effects.psd`` carries two strokes on one layer (#798),
    which is what tells a guard around each effect apart from a guard around
    the loop: both render identically unless the second stroke survives the
    first one being unreadable.
    """
    both_off = _rendered("effects/double-stroke-effects.psd", mutate=_disable)
    first_off = _rendered("effects/double-stroke-effects.psd", mutate=_disable, nth=0)
    first_broken = _rendered(
        "effects/double-stroke-effects.psd", mutate=_UNDRAWABLE["no-color"], nth=0
    )
    assert not np.array_equal(first_off, both_off), "the second stroke draws nothing"
    assert np.array_equal(first_broken, first_off)


def test_a_gradient_that_cannot_be_scaled_is_dropped_not_raised() -> None:
    """A descriptor read that survives and then divides by what it read.

    ``draw_gradient_fill()`` scales its coordinate grid by ``Key.Scale``, so a
    gradient overlay scaled to 0 raises ``ZeroDivisionError`` -- a value that
    parses, passes every type check, and still cannot be used. Photoshop's own
    UI floors the scale at 10%, which is why this needs forging, and it is the
    reason the guards catch what a descriptor's *arithmetic* raises and not
    only what reading it raises (#826).
    """
    assert np.array_equal(
        _rendered(
            "clipping-mask2.psd",
            kind="gradientoverlay",
            mutate=lambda desc: desc.__setitem__(Key.Scale, Double(0.0)),
        ),
        _rendered("clipping-mask2.psd", kind="gradientoverlay", mutate=_disable),
    )


def test_an_unreadable_overlay_is_dropped_and_the_document_still_renders() -> None:
    """The overlays read a descriptor to draw too, and raised the same way.

    ``_apply_overlay()`` reaches the same ``paint._get_color()`` the stroke
    does, with no measurement in front of it to degrade first, so a colour
    overlay missing its colour took down ``stroke-composite.psd`` outright.
    The rule is the effect's, not the stroke's: an effect whose descriptor
    cannot be read is skipped (#826).
    """
    assert np.array_equal(
        _rendered(
            "effects/stroke-composite.psd",
            kind="coloroverlay",
            mutate=_UNDRAWABLE["no-color"],
        ),
        _rendered("effects/stroke-composite.psd", kind="coloroverlay", mutate=_disable),
    )


@pytest.mark.parametrize("force", [False, True])
def test_a_group_stroke_traces_the_group_past_the_canvas(force: bool) -> None:
    """A stroke on a group follows the group, not the viewport edge (#808).

    ``group-stroke-off-canvas.psd`` is a 96x32 document with two groups, each
    carrying a 4 px inset stroke on the *group*:

    ``Clipped`` holds an L -- a blue ``Arm`` and a green ``Leg`` -- shifted so
    the group sits at ``(-12, 4, 12, 28)``, 12 px off the left edge, and its
    stroke box ``(-13, 3, 13, 29)`` escapes the canvas. Only the ``Arm``
    crosses ``x = 0``, so the coverage in the escaping strip stops at
    ``y = 14`` and the boundary running through that strip is horizontal.

    That geometry is what separates three answers, at two rows:

    - row 8 runs through the ``Arm``, where the group continues past the canvas
      and so has no boundary. The compositor used to trace its own clipped copy,
      whose coverage stopped dead at ``x = 0``, and painted a band there that
      Photoshop does not.
    - row 20 runs below the ``Arm``, where only the ``Leg`` is, and the group's
      left boundary really is at ``x = 0``. Treating everything outside the
      viewport as covered -- the cheap way to make row 8 pass -- erases this
      band instead.

    ``Inside`` is the control: its stroke box ``(35, 7, 61, 25)`` stays within
    the canvas, so it takes the early return and must not move at all.
    """
    check_composite_quality("effects/group-stroke-off-canvas.psd", 1e-4, force)

    psd = PSDImage.open(full_name("effects/group-stroke-off-canvas.psd"))
    image = psd.composite(ignore_preview=True, force=force)
    assert image is not None
    rgb = np.asarray(image.convert("RGB"))

    blue, red, green = (0, 0, 255), (255, 0, 0), (0, 180, 0)
    assert [tuple(pixel) for pixel in rgb[8, 0:4]] == [blue] * 4, (
        "the group runs past the canvas here, so there is no edge to stroke"
    )
    assert [tuple(pixel) for pixel in rgb[20, 0:4]] == [red] * 4, (
        "but here the group really does end at x = 0, and the band belongs"
    )
    assert tuple(rgb[20, 4]) == green

    # The control third, byte for byte against Photoshop's own render.
    preview = psd.topil()
    assert preview is not None
    assert np.array_equal(
        rgb[:, 32:64], np.asarray(preview.convert("RGB"))[:, 32:64]
    ), "a contained stroke box must still take the early return"


@pytest.mark.parametrize("force", [False, True])
def test_an_isolated_group_keeps_a_child_stroke_that_reaches_past_it(
    force: bool,
) -> None:
    """A group composites on what its children paint, not on their bboxes (#808).

    ``group-clips-child-stroke.psd`` is a 96x32 document holding three 16x16
    squares, each carrying a 3 px red stroke effect and each alone in a group
    of its own: an outset stroke under a Normal group, a centered one under a
    Normal group, and an outset one under a Pass Through group.

    ``Group.bbox`` is the union of its children's own bounding boxes and
    excludes effect coverage, so an isolated group composited on the square
    alone. An outset stroke lies wholly outside the square, so all of it was
    clipped away; a centered one straddles the edge, so its outer half was. The
    pass-through group is the control -- its viewport is the document's, so it
    rendered correctly throughout -- and its ring is the outset ring translated
    by +64 in x, which distinguishes a ring restored in full from one merely
    brought back mis-shaded.

    Every stroke box sits inside the canvas on all four sides, so the fixture
    measures the group clip and not the canvas clip #804 is about.
    """
    check_composite_quality("effects/group-clips-child-stroke.psd", 1e-4, force)

    psd = PSDImage.open(full_name("effects/group-clips-child-stroke.psd"))
    image = psd.composite(ignore_preview=True, force=force)
    assert image is not None
    rgb = np.asarray(image.convert("RGB"))
    outset, centered, passthrough = rgb[:, 0:32], rgb[:, 32:64], rgb[:, 64:96]

    assert np.array_equal(outset, passthrough), "the isolated ring is the control's"
    # Three columns of stroke outside the square, then its blue interior. The
    # pixels rather than the error alone: a whole-image bound reads a dropped
    # ring and a ring one column short as the same kind of "smaller".
    assert [tuple(pixel) for pixel in outset[16, 5:9]] == [(255, 0, 0)] * 3 + [
        (0, 0, 255)
    ]
    assert tuple(outset[16, 4]) == (255, 255, 255)
    # A centered stroke straddles the edge instead of sitting outside it, so
    # only half of it is at risk and the group clip took exactly that half:
    # one full column and one half column beyond the square, where an outset
    # stroke of the same size puts three full ones. It is the case that
    # separates a whole fix from a half one.
    assert tuple(centered[16, 7]) == (255, 0, 0)
    assert tuple(centered[16, 6]) == (255, 127, 127)
    assert tuple(centered[16, 5]) == (255, 255, 255)


def _unreadable_block(filename: str) -> np.ndarray:
    """``filename`` composited with every effects block replaced by raw bytes.

    What ``TaggedBlock.read()`` leaves behind for a block it could not parse,
    which used to raise out of ``Effects.__init__`` before any guard in this
    module could see it (#828).
    """
    psd = PSDImage.open(full_name(filename))
    for layer in psd.descendants():
        for tag in (
            Tag.OBJECT_BASED_EFFECTS_LAYER_INFO,
            Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V0,
            Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V1,
        ):
            if tag in layer.tagged_blocks:
                layer.tagged_blocks[tag].data = b"garbagebytes"
    return np.asarray(psd.composite(ignore_preview=True).convert("RGBA"))


def _with_unknown_class(filename: str, key: bytes, index: int = 0) -> np.ndarray:
    """``filename`` composited with one effect's class forged unknown.

    Not ``_rendered()``: that reaches its effect through
    ``layer.effects.find()``, which is exactly what cannot see an effect whose
    class has no handler. This goes at the descriptor the effects block holds.
    """
    psd = PSDImage.open(full_name(filename))
    for layer in psd.descendants():
        data = layer.effects._data
        if data is None or key not in data:
            continue
        item = data[key]
        item = item[index] if isinstance(item, List) else item
        item.classID = b"XXXX"
    return np.asarray(psd.composite(ignore_preview=True).convert("RGBA"))


def test_an_unknown_effect_class_is_dropped_and_the_document_still_renders() -> None:
    """An effect class with no handler costs its effect, not the render (#828).

    ``Effects`` used to reject it, and since the compositor formats every
    layer it visits through ``Layer.__repr__``, which asks ``has_effects()``,
    the whole document raised -- at any log level, logging disabled included.

    Asserted against the same document with that one stroke switched off, and
    against the other stroke still drawing, for the reason
    ``test_an_unreadable_stroke_leaves_the_other_stroke_on_the_layer`` gives:
    both strokes vanishing would pass a test that only asked whether the
    render raised.
    """
    both_off = _rendered("effects/double-stroke-effects.psd", mutate=_disable)
    first_off = _rendered("effects/double-stroke-effects.psd", mutate=_disable, nth=0)
    first_unknown = _with_unknown_class(
        "effects/double-stroke-effects.psd", b"frameFXMulti", index=0
    )
    assert not np.array_equal(first_off, both_off), "the second stroke draws nothing"
    assert np.array_equal(first_unknown, first_off)


def test_an_effects_block_that_did_not_parse_renders_as_no_effects() -> None:
    """The layer keeps its pixels and loses its effects, not the document.

    Asserted against the same document with the effects switched off rather
    than against "it did not raise", which is what tells a block read as no
    effects apart from one read as some invented effect -- and the fixture's
    stroke has to draw for the second assertion to mean anything (#828).
    """
    both_off = _rendered("effects/double-stroke-effects.psd", mutate=_disable)
    assert np.array_equal(
        _unreadable_block("effects/double-stroke-effects.psd"), both_off
    )
    assert not np.array_equal(both_off, _rendered("effects/double-stroke-effects.psd"))


def test_mark_updated_refreshes_a_preview_the_api_could_not_see(
    tmp_path: Path,
) -> None:
    """The harm #831 measured: a saved file disagreeing with its own layers.

    ``composite()`` hands back the stored preview while the document thinks
    it is unedited, and ``save()`` writes that preview out. An effect colour
    changed through ``descriptor`` sets no flag, so both keep answering from
    before the edit until ``mark_updated()`` says otherwise.
    """

    # Everything is read back in one mode: the preview is RGB and a render
    # of it is RGBA, so raw arrays would differ by shape alone and every
    # assertion below would pass without looking at a pixel.
    def pixels(image: Image.Image) -> np.ndarray:
        return np.asarray(image.convert("RGB"))

    psd = PSDImage.open(full_name("layer_effects.psd"))
    stale = pixels(psd.composite())
    stored = psd.topil()
    assert stored is not None
    assert np.array_equal(stale, pixels(stored)), (
        "the fixture has to be answering from its stored preview"
    )

    psd[6].effects[0].descriptor[Key.Color][Key.Red] = Double(255.0)
    assert np.array_equal(pixels(psd.composite()), stale), (
        "an edit through the escape hatch is invisible to the document"
    )

    psd.mark_updated()
    fresh = pixels(psd.composite())
    assert not np.array_equal(fresh, stale), "still answering from the preview"
    untouched = pixels(
        PSDImage.open(full_name("layer_effects.psd")).composite(ignore_preview=True)
    )
    assert not np.array_equal(fresh, untouched), (
        "the re-render has to show the edit, not merely differ from a preview"
    )

    out = tmp_path / "marked.psd"
    psd.save(out)
    saved = PSDImage.open(out).topil()
    assert saved is not None
    assert np.array_equal(pixels(saved), fresh), (
        "save() has to write the preview it just regenerated"
    )


def test_the_render_path_does_not_trip_its_own_deprecation() -> None:
    """#831 step 6: the compositor was the last in-tree reader of ``value``.

    Rendering this fixture reaches all four sites it read from -- the stroke
    reach the cull measures, the overlay fill, and the stroke's own box and
    draw. Filtering on the message rather than on ``DeprecationWarning``
    keeps a warning from somewhere else in the stack out of it.
    """
    psd = PSDImage.open(full_name("layer_effects.psd"))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        psd.composite(ignore_preview=True)

    assert not [w for w in caught if "'value' is deprecated" in str(w.message)]
