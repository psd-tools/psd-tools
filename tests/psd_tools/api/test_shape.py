from __future__ import absolute_import, unicode_literals
import pytest
import logging

from psd_tools.api.psd_image import PSDImage
from psd_tools.api.shape import (
    Rectangle, RoundedRectangle, Ellipse, Line, Invalidated
)

from ..utils import full_name

logger = logging.getLogger(__name__)

VECTOR_MASK2 = PSDImage.open(full_name('vector-mask2.psd'))


@pytest.fixture
def psd():
    return VECTOR_MASK2


def test_layer_properties(psd):
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
        if layer.kind == 'shape':
            expected = index in (2, 4)
            assert layer.has_stroke() is expected
            if expected:
                assert layer.stroke is not None
            else:
                assert layer.stroke is None


def test_vector_mask(psd):
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
    'index, kls', [
        (1, Rectangle),
        (2, RoundedRectangle),
        (3, Ellipse),
        (4, Invalidated),
        (5, Line),
    ]
)
def test_origination(psd, index, kls):
    origination = psd[index].origination[0]
    assert isinstance(origination, kls)
    if kls == Invalidated:
        return

    assert origination.origin_type > 0
    assert isinstance(origination.resolution, float)
    assert origination.bbox
    assert origination.index == 0
    if kls == RoundedRectangle:
        assert origination.radii
    elif kls == Line:
        assert origination.line_end
        assert origination.line_start
        assert origination.line_weight == 1.0
        assert origination.arrow_start is False
        assert origination.arrow_end is False
        assert origination.arrow_width == 0.0
        assert origination.arrow_length == 0.0
        assert origination.arrow_conc == 0
