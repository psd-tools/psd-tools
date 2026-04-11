import logging
from typing import Iterator, Type

import pytest

from psd_tools.api.psd_image import PSDImage
from psd_tools.api.shape import (
    Ellipse,
    Invalidated,
    Line,
    Rectangle,
    RoundedRectangle,
    VectorMask,
)
from psd_tools.psd.vector import (
    ClosedKnotLinked,
    ClosedPath,
    OpenKnotLinked,
    OpenPath,
    VectorMaskSetting,
)

from ..utils import full_name

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers for VectorMask.bbox unit tests
# ---------------------------------------------------------------------------


def _make_vm(*paths):
    """Return a VectorMask whose _paths list is set directly."""
    vm = VectorMask(VectorMaskSetting())
    vm._paths = list(paths)
    return vm


def _ck(y: float, x: float) -> ClosedKnotLinked:
    """Closed knot with all handles at the anchor (corner knot)."""
    return ClosedKnotLinked(preceding=(y, x), anchor=(y, x), leaving=(y, x))


def _ok(y: float, x: float) -> OpenKnotLinked:
    """Open knot with all handles at the anchor (corner knot)."""
    return OpenKnotLinked(preceding=(y, x), anchor=(y, x), leaving=(y, x))


VECTOR_MASK2 = PSDImage.open(full_name("vector-mask2.psd"))


@pytest.fixture
def psd() -> Iterator[PSDImage]:
    yield VECTOR_MASK2


def test_layer_properties(psd: PSDImage) -> None:
    for index in range(len(psd)):
        layer = psd[index]
        assert layer.has_vector_mask() is True
        assert layer.vector_mask
        expected = index != 0
        assert layer.has_origination() is expected
        if expected:
            assert layer.origination
        else:
            assert not layer.origination
        if layer.kind == "shape":
            expected = index in (2, 4)
            assert layer.has_stroke() is expected
            if expected:
                assert layer.stroke is not None
            else:
                assert layer.stroke is None


def test_vector_mask(psd: PSDImage) -> None:
    vector_mask = psd[7].vector_mask
    assert vector_mask is not None
    assert vector_mask.inverted == 0
    assert vector_mask.not_linked == 0
    assert vector_mask.disabled == 0
    assert vector_mask.initial_fill_rule == 0
    vector_mask.initial_fill_rule = 1
    assert vector_mask.initial_fill_rule == 1
    assert vector_mask.clipboard_record is None
    assert len(vector_mask.paths) == 4
    for path in vector_mask.paths:
        assert path.is_closed()
        for knot in path:
            assert knot.preceding
            assert knot.anchor
            assert knot.leaving


@pytest.mark.parametrize(
    "index, kls",
    [
        (1, Rectangle),
        (2, RoundedRectangle),
        (3, Ellipse),
        (4, Invalidated),
        (5, Line),
    ],
)
def test_origination(
    psd: PSDImage,
    index: int,
    kls: Type[Rectangle | RoundedRectangle | Ellipse | Invalidated | Line],
) -> None:
    origination = psd[index].origination[0]
    assert isinstance(origination, kls)
    if kls == Invalidated:
        return

    assert origination.origin_type > 0
    assert isinstance(origination.resolution, float)
    assert origination.bbox
    assert origination.index == 0
    if isinstance(origination, RoundedRectangle):
        assert origination.radii
    elif isinstance(origination, Line):
        assert origination.line_end
        assert origination.line_start
        assert origination.line_weight == 1.0
        assert origination.arrow_start is False
        assert origination.arrow_end is False
        assert origination.arrow_width == 0.0
        assert origination.arrow_length == 0.0
        assert origination.arrow_conc == 0


# ---------------------------------------------------------------------------
# VectorMask.bbox unit tests
# ---------------------------------------------------------------------------


def test_bbox_empty_paths():
    """No paths → full-canvas fallback."""
    assert _make_vm().bbox == (0.0, 0.0, 1.0, 1.0)


def test_bbox_single_knot_open_path():
    """Single-knot open path has no segments; anchor point must still be included."""
    k = _ok(0.3, 0.5)
    vm = _make_vm(OpenPath(items=[k]))
    assert vm.bbox == pytest.approx((0.5, 0.3, 0.5, 0.3))


def test_bbox_interior_extremum():
    """Bezier curve can extend beyond the convex hull of its anchor points."""
    # k0 has a leaving handle that pulls the curve above (smaller y than) its anchor.
    # Anchor y values: 0.3 and 0.7.  The curve dips to y ≈ 0.259 between them.
    k0 = ClosedKnotLinked(preceding=(0.3, 0.2), anchor=(0.3, 0.2), leaving=(0.1, 0.2))
    k1 = ClosedKnotLinked(preceding=(0.7, 0.8), anchor=(0.7, 0.8), leaving=(0.7, 0.8))
    vm = _make_vm(ClosedPath(items=[k0, k1]))
    left, top, right, bottom = vm.bbox
    # The curve dips above the topmost anchor (smaller y = higher on canvas).
    assert top < 0.3
    assert bottom == pytest.approx(0.7)


def test_bbox_a_zero_linear_fallback():
    """When the cubic coefficient a==0 the derivative is quadratic → linear fallback."""
    # Segment: P0_y=0, C1_y=C2_y=0.3, P3_y=0  →  a=0, t_ext=0.5, B(0.5)=0.225
    k0 = ClosedKnotLinked(preceding=(0.0, 0.0), anchor=(0.0, 0.0), leaving=(0.3, 0.5))
    k1 = ClosedKnotLinked(preceding=(0.3, 0.5), anchor=(0.0, 1.0), leaving=(0.0, 1.0))
    vm = _make_vm(ClosedPath(items=[k0, k1]))
    left, top, right, bottom = vm.bbox
    assert top == pytest.approx(0.0)
    assert bottom == pytest.approx(0.225)
    assert left == pytest.approx(0.0)
    assert right == pytest.approx(1.0)


def test_bbox_repeated_root():
    """Discriminant == 0 (tangent extremum) is handled without error."""
    # Constructed so that disc = b²-4ac = 0 with the repeated root at t=0.5.
    # P0_y=0.1, C1_y=0.6, C2_y=0.1, P3_y=0.6  →  a=2, b=-2, c=0.5, disc=0
    k0 = ClosedKnotLinked(preceding=(0.1, 0.2), anchor=(0.1, 0.2), leaving=(0.6, 0.2))
    k1 = ClosedKnotLinked(preceding=(0.1, 0.8), anchor=(0.6, 0.8), leaving=(0.6, 0.8))
    vm = _make_vm(ClosedPath(items=[k0, k1]))
    left, top, right, bottom = vm.bbox
    # Interior extremum at t=0.5: B(0.5)=0.35 (within anchor range, no extension)
    assert top == pytest.approx(0.1)
    assert bottom == pytest.approx(0.6)


def test_bbox_multi_subpath_union():
    """Bounding box spans all subpaths."""
    path1 = ClosedPath(items=[_ck(0.1, 0.1), _ck(0.2, 0.2)])
    path2 = ClosedPath(items=[_ck(0.7, 0.6), _ck(0.8, 0.9)])
    vm = _make_vm(path1, path2)
    left, top, right, bottom = vm.bbox
    assert left == pytest.approx(0.1)
    assert top == pytest.approx(0.1)
    assert right == pytest.approx(0.9)
    assert bottom == pytest.approx(0.8)


def test_bbox_single_knot_closed_path_degenerate():
    """Single-knot closed path with coincident handles collapses to a point.

    A closed path with one knot forms a self-loop cubic (k→k) whose extent is
    determined by its leaving/preceding handles.  When all handles coincide with
    the anchor the loop degenerates and the bbox is just the anchor point.
    This documents current behaviour for an edge case not yet observed in real
    PSD files.
    """
    k = _ck(0.4, 0.3)
    vm = _make_vm(ClosedPath(items=[k]))
    left, top, right, bottom = vm.bbox
    assert left == pytest.approx(0.3)
    assert top == pytest.approx(0.4)
    assert right == pytest.approx(0.3)
    assert bottom == pytest.approx(0.4)
