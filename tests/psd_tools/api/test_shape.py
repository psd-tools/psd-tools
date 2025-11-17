import logging
from typing import Type

import pytest

from psd_tools.api.psd_image import PSDImage
from psd_tools.api.shape import Ellipse, Invalidated, Line, Rectangle, RoundedRectangle

from ..utils import full_name

logger = logging.getLogger(__name__)

VECTOR_MASK2 = PSDImage.open(full_name("vector-mask2.psd"))


@pytest.fixture
def psd():
    return VECTOR_MASK2


def test_layer_properties(psd) -> None:
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


def test_vector_mask(psd) -> None:
    vector_mask = psd[7].vector_mask
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
    if kls == RoundedRectangle:
        assert origination.radii  # type: ignore[attr-defined]
    elif kls == Line:
        assert origination.line_end  # type: ignore[attr-defined]
        assert origination.line_start  # type: ignore[attr-defined]
        assert origination.line_weight == 1.0  # type: ignore[attr-defined]
        assert origination.arrow_start is False  # type: ignore[attr-defined]
        assert origination.arrow_end is False  # type: ignore[attr-defined]
        assert origination.arrow_width == 0.0  # type: ignore[attr-defined]
        assert origination.arrow_length == 0.0  # type: ignore[attr-defined]
        assert origination.arrow_conc == 0  # type: ignore[attr-defined]
