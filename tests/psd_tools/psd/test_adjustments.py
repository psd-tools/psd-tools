from __future__ import absolute_import, unicode_literals
import pytest
import logging
import os

from psd_tools.psd.adjustments import (
    Curves,
    CurvesExtraMarker,
    CurvesExtraItem,
)

from ..utils import check_write_read, check_read_write, TEST_ROOT

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    'is_map, version, count_map, data, extra', [
        (False, 4, 1, [[(0, 0), (255, 255)]], None),
        (True, 4, 1, [list(range(256))], None),
        (
            False, 1, 1, [[
                (0, 0), (255, 255)
            ]], CurvesExtraMarker([CurvesExtraItem(0, [(0, 0), (255, 255)])])
        ),
        (
            True, 1, 1, [list(range(256))],
            CurvesExtraMarker([CurvesExtraItem(0, list(range(256)))])
        ),
    ]
)
def test_curves(is_map, version, count_map, data, extra):
    check_write_read(Curves(is_map, version, count_map, data, extra))


@pytest.mark.parametrize(
    'channel_id, points, is_map', [
        (0, [(0, 0), (255, 255)], False),
        (0, list(range(256)), True),
    ]
)
def test_curves_extra_item_wr(channel_id, points, is_map):
    check_write_read(CurvesExtraItem(channel_id, points), is_map=is_map)


@pytest.mark.parametrize(
    'fixture, is_map', [
        (b'\x00\x00' + bytes(bytearray(range(256))), True),
        (b'\x00\x00\x00\x02\x00\x00\x00\x00\xff\xff\xff\xff', False),
    ]
)
def test_curves_extra_item_rw(fixture, is_map):
    check_read_write(CurvesExtraItem, fixture, is_map=is_map)


@pytest.mark.parametrize('filename', ['curves.dat'])
def test_curves_rw(filename):
    filepath = os.path.join(TEST_ROOT, 'tagged_blocks', filename)
    with open(filepath, 'rb') as f:
        fixture = f.read()
    check_read_write(Curves, fixture)


@pytest.mark.parametrize('filename', ['curves_2.dat'])
def test_curves_r(filename):
    filepath = os.path.join(TEST_ROOT, 'tagged_blocks', filename)
    with open(filepath, 'rb') as f:
        Curves.read(f)
