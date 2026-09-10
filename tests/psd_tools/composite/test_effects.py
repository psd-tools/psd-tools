import logging
import math

import numpy as np
import pytest

from psd_tools.api.psd_image import PSDImage
from psd_tools.composite import _compat, effects
from psd_tools.composite.effects import (
    _OUTWARD_REACH,
    _distance_band,
    _signed_distance,
)
from psd_tools.terminology import Enum

from ..utils import full_name
from .test_composite import check_composite_quality

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    ("filename",),
    [
        ("effects/stroke-effects.psd",),
        ("effects/shape-fx2.psd",),
        ("effects/stroke-effect-transparent-shape.psd",),
    ],
)
@pytest.mark.xfail
def test_stroke_effects_xfail(filename: str) -> None:
    check_composite_quality(filename, threshold=0.01)


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
    ],
)
def test_hard_edged_stroke_matches_photoshop(filename: str) -> None:
    """A stroke on a hard-edged mask lands where Photoshop puts it (#799).

    Both files are squares with no partial alpha anywhere, so the boundary the
    stroke is measured from is a fact rather than a modelling choice. Every
    straight run of the stroke then matches Photoshop to the bit, because a
    ramp that is linear in distance is the exact area of a pixel cut by a
    straight edge. What is left is the corner arcs, where that ramp is only an
    approximation of a curved cut: 16 pixels of 1024 and 24 of 9216, differing
    by up to 0.073 and 0.110 coverage, which is why this asserts 1e-4 rather
    than equality.

    That is still 60x and 30x under what these scored when the stroke was a
    dilated ``scharr`` edge -- 0.00626 and 0.00326 -- so the threshold
    separates the band from an approximation of it, which the 0.01 used
    elsewhere would not.
    """
    check_composite_quality(filename, threshold=1e-4)


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


@pytest.mark.parametrize("size", [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 7.0, 7.5, 10.0])
def test_band_fits_the_canvas_stroke_bbox_asks_for(size: float) -> None:
    """The band never reaches past the margin :py:func:`stroke_bbox` grants.

    That margin is what keeps an outset or centered stroke from being clipped
    to the layer's own bounding box (#792). On a hard-edged mask the band
    reaches exactly one pixel less than the margin at every size, so equality
    is asserted rather than a bound: the reach and the margin are now stated
    independently -- in the band limits here and in ``_OUTWARD_REACH`` -- and
    a change to either that forgets the other would otherwise start shaving
    the outside of every stroke, or reserving canvas nobody draws on.
    """
    pad = 40
    alpha = np.zeros((2 * pad + 20, 2 * pad + 20), dtype=np.float32)
    alpha[pad : pad + 20, pad : pad + 20] = 1.0
    distance = _signed_distance(alpha)

    for style, limits in (
        (Enum.OutsetFrame, (0.0, size)),
        (Enum.CenteredFrame, (-size / 2.0, size / 2.0)),
    ):
        band = _distance_band(distance, *limits)
        ys, xs = np.nonzero(band)
        # All four sides, not just the horizontal pair: the mask is square, so
        # a band that reached unevenly would otherwise go unnoticed.
        reach = max(
            pad - int(xs.min()),
            int(xs.max()) + 1 - (pad + 20),
            pad - int(ys.min()),
            int(ys.max()) + 1 - (pad + 20),
        )
        margin = math.ceil(size * _OUTWARD_REACH[style]) + 1
        assert reach == margin - 1, (
            f"{style!r} stroke of {size} px reaches {reach} px outside the "
            f"layer, against the {margin} px stroke_bbox() reserves for it"
        )


@pytest.mark.parametrize(
    "alpha",
    [0.0, 1.0, 0.3, 0.9],
    ids=["transparent", "opaque", "below-half", "above-half"],
)
def test_a_mask_with_no_boundary_draws_no_stroke(alpha: float) -> None:
    """A stroke needs a boundary to trace, and a flat mask has none (#799).

    ``distance_transform_edt`` is undefined on an input with no zeros: rather
    than refusing, it reports distances to a phantom feature off the array
    corner, and a band built on those paints a wedge of full-coverage stroke
    into the corner of the canvas. Nothing in the fixture corpus has a
    boundaryless mask -- a layer everywhere below half alpha is all it takes --
    so no rendering comparison can catch this and only this test does.
    """
    flat = np.full((9, 9), alpha, dtype=np.float32)
    distance = _signed_distance(flat)
    # Uniformly infinitely far from a boundary that is not there.
    assert not np.isfinite(distance).any()
    for limits in ((0.0, 3.0), (-1.5, 1.5)):
        band = _distance_band(distance, *limits)
        assert float(band.sum()) == 0.0, f"stroke painted on a flat {alpha} mask"


def test_a_feathered_mask_keeps_its_stroke_at_the_boundary() -> None:
    """A wide alpha ramp takes a stroke at its half-coverage line, not across it.

    Only a pixel the boundary actually cuts is reseeded from its coverage.
    Reseeding every partial pixel instead -- which is the reading the issue's
    own snippet invites -- puts the entire body of a feathered mask within half
    a pixel of a boundary it is nowhere near, and the band spreads over all of
    it: on this ramp that paints all 32 pixels of every row rather than 4, and
    the field stops satisfying the unit gradient the linear ramp relies on.
    """
    ramp = np.tile(np.linspace(1.0, 0.0, 32, dtype=np.float32), (4, 1))
    distance = _signed_distance(ramp)
    for limits in ((0.0, 3.0), (-1.5, 1.5)):
        band = _distance_band(distance, *limits)
        painted = (band > 0).sum(axis=1)
        assert painted.tolist() == [4, 4, 4, 4], (
            f"a 3 px stroke covered {painted.tolist()} pixels of a 32 px ramp"
        )
        for total in band.sum(axis=1):
            assert float(total) == pytest.approx(3.0)


def test_band_strokes_draw_without_scikit_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An outset or centered stroke needs scipy, not scikit-image (#802).

    Only the inset style's dilated edge still uses scikit-image. While the
    whole of :py:func:`draw_stroke_effect` was gated on it, a scipy-only
    install -- a platform with no scikit-image wheel, say -- failed to render
    *any* document carrying *any* stroke, because nothing upstream catches the
    ImportError and turns it into a missing effect.
    """
    monkeypatch.setattr(_compat, "HAS_SKIMAGE", False)
    check_composite_quality("effects/outside-stroke.psd", threshold=1e-4)
    check_composite_quality("effects/center-stroke-sizes.psd", threshold=1e-4)


def test_each_stroke_path_names_the_dependency_it_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two paths ask for different packages, so they must say which.

    Asserted because the obvious way to guard the band is ``@require_scipy``,
    whose message tells the reader to install scipy for *gradient fills* --
    accurate about the package and misleading about why.
    """
    monkeypatch.setattr(_compat, "HAS_SKIMAGE", False)
    with pytest.raises(ImportError, match="scikit-image"):
        check_composite_quality("effects/shape-fx2.psd", threshold=1.0)

    monkeypatch.setattr(effects, "HAS_SCIPY", False)
    with pytest.raises(ImportError, match="stroke effects require: scipy"):
        check_composite_quality("effects/outside-stroke.psd", threshold=1.0)
