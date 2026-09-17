"""Acceptance contract for issue #823.

``_draw_path()`` seeds its plane as fully covered when the layer's vector
mask has an initial fill rule and carries no paths. The seed describes a
reveal-all *fill*, so it must apply to a brush call only; a pen-only call
(a stroke with no path to outline) must come back empty, not fully
covered. These tests pin the maintainer-stated behavior from the issue:

- repro: pen-only on the seed condition must not be fully covered
- preserve: brush seed, stroke rasterization, and the ``first and brush``
  fill-rule inversions must not regress.
"""

import numpy as np
import pytest

from psd_tools import PSDImage
from psd_tools.composite import vector

from ..utils import full_name


def _seed_layer():
    """The layer the issue names: initial_fill_rule == 1 and zero paths."""
    psd = PSDImage.open(full_name("adjustment-fillers.psd"))
    layer = [x for x in psd.descendants() if x.name == "Color Fill 1"][0]
    assert layer.vector_mask.initial_fill_rule and len(layer.vector_mask.paths) == 0
    return layer


def test_pen_only_seed_is_not_fully_covered() -> None:
    """Repro (#823): a pen-only raster of a path-less reveal-all mask must not cover everything.

    Today the seed applies to the pen too, so the whole viewport comes back stroke.
    """
    layer = _seed_layer()
    pen = vector._draw_path(layer, pen={"color": 255, "width": 1.0})
    assert pen.min() < 1.0, (
        "a pen-only raster of a path-less layer is fully covered "
        "(the fill-rule seed leaked into the stroke path)"
    )


def test_pen_only_seed_is_empty() -> None:
    """Repro (#823), maintainer-stated expectation: there is no path to outline.

    So the stroke plane is empty, not merely partial.
    """
    layer = _seed_layer()
    pen = vector._draw_path(layer, pen={"color": 255, "width": 1.0})
    assert np.count_nonzero(pen) == 0, (
        "a stroke over zero paths must draw nothing, got %d nonzero pixels"
        % np.count_nonzero(pen)
    )


def test_brush_seed_stays_fully_covered() -> None:
    """Preserve: the seed is correct for a brush (``draw_vector_mask()``) — a reveal-all mask with nothing subtracted from it.

    The fix gates on the brush and must keep this plane fully covered.
    """
    layer = _seed_layer()
    brush = vector._draw_path(layer, brush={"color": 255})
    assert brush.min() == 1.0 and brush.max() == 1.0


def test_draw_vector_mask_on_seed_unchanged() -> None:
    """Preserve: the public brush entry point over the seed layer still returns the reveal-all plane."""
    layer = _seed_layer()
    mask = vector.draw_vector_mask(layer)
    assert mask.shape == (512, 512, 1)
    assert mask.min() == 1.0


def test_pen_raster_of_stroked_layers_unchanged() -> None:
    """Preserve: for layers that do have paths the seed never applied (initial_fill_rule is 0 here).

    So gating it must not move a single coverage value of a real stroke raster.
    """
    psd = PSDImage.open(full_name("stroke.psd"))
    expected = {
        "Rectangle 1": 221.113724,
        "Rounded Rectangle 1": 237.462738,
        "Ellipse 1": 162.458832,
        "Polygon 1": 153.188232,
        "Shape 1": 138.588242,
    }
    seen = set()
    for layer in psd.descendants():
        if layer.stroke and layer.stroke.enabled:
            pen = vector._draw_path(layer, pen={"color": 255, "width": 1.0})
            assert pen.min() == 0.0
            assert pen.sum() == pytest.approx(expected[layer.name], rel=1e-6), (
                layer.name
            )
            seen.add(layer.name)
    assert seen == set(expected)


def test_fill_rule_inversions_stay_brush_gated() -> None:
    """Preserve: the ``if first and brush:`` inversions for subtract and intersect operate on the seeded plane for a brush.

    They are skipped for a pen. Gate the new seed the same way and these sums must not move.
    """
    psd = PSDImage.open(full_name("vector-mask2.psd"))
    masked = [x for x in psd.descendants() if x.name == "Masked Rectangle 1"][0]
    assert masked.vector_mask is not None
    assert masked.vector_mask.initial_fill_rule and len(masked.vector_mask.paths) == 1
    brush = vector._draw_path(masked, brush={"color": 255})
    assert brush.sum() == pytest.approx(90.12942, abs=1e-4)
    pen = vector._draw_path(masked, pen={"color": 255, "width": 1.0})
    assert pen.sum() == pytest.approx(35.843136, abs=1e-4)

    filled = [x for x in psd.descendants() if x.name == "Color Fill 1"][0]
    vm = filled.vector_mask
    assert vm is not None
    assert vm.initial_fill_rule and [p.operation for p in vm.paths] == [3, 3]
    assert vector._draw_path(filled, brush={"color": 255}).sum() == pytest.approx(
        13.241477, abs=1e-4
    )
    assert vector._draw_path(filled, pen={"color": 255, "width": 1.0}).sum() == 0.0
