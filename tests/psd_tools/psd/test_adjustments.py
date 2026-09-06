from typing import List, Tuple
import logging
import os
import struct

import pytest

from psd_tools.psd.adjustments import (
    Curves,
    CurvesExtraItem,
    CurvesExtraMarker,
    HueSaturation,
    Levels,
)

from ..utils import TEST_ROOT, check_read_write, check_write_read

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "is_map, version, count_map, data, extra",
    [
        (False, 4, 1, [[(0, 0), (255, 255)]], None),
        (True, 4, 1, [list(range(256))], None),
        (
            False,
            1,
            1,
            [[(0, 0), (255, 255)]],
            CurvesExtraMarker(
                items=[CurvesExtraItem(channel_id=0, points=[(0, 0), (255, 255)])]  # type: ignore[list-item]
            ),
        ),
        (
            True,
            1,
            1,
            [list(range(256))],
            CurvesExtraMarker(
                items=[CurvesExtraItem(channel_id=0, points=list(range(256)))]  # type: ignore[list-item,arg-type]
            ),
        ),
    ],
)
def test_curves(
    is_map: bool, version: int, count_map: int, data: bytes, extra: bytes
) -> None:
    check_write_read(Curves(is_map, version, count_map, data, extra))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "channel_id, points, is_map",
    [
        (0, [(0, 0), (255, 255)], False),
        (0, list(range(256)), True),
    ],
)
def test_curves_extra_item_wr(
    channel_id: int, points: List[Tuple[int, int]], is_map: bool
) -> None:
    check_write_read(
        CurvesExtraItem(channel_id=channel_id, points=points),  # type: ignore[arg-type]
        is_map=is_map,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    "fixture, is_map",
    [
        (b"\x00\x00" + bytes(bytearray(range(256))), True),
        (b"\x00\x00\x00\x02\x00\x00\x00\x00\xff\xff\xff\xff", False),
    ],
)
def test_curves_extra_item_rw(fixture: bytes, is_map: bool) -> None:
    check_read_write(CurvesExtraItem, fixture, is_map=is_map)


@pytest.mark.parametrize("filename", ["curves.dat"])
def test_curves_rw(filename: str) -> None:
    filepath = os.path.join(TEST_ROOT, "tagged_blocks", filename)
    with open(filepath, "rb") as f:
        fixture = f.read()
    check_read_write(Curves, fixture)


@pytest.mark.parametrize("filename", ["curves_2.dat"])
def test_curves_r(filename: str) -> None:
    filepath = os.path.join(TEST_ROOT, "tagged_blocks", filename)
    with open(filepath, "rb") as f:
        Curves.read(f)


@pytest.mark.parametrize(
    "filename", ["levels_clipstudio_1.dat", "levels_photoshop_1.dat"]
)
def test_levels_r(filename: str) -> None:
    filepath = os.path.join(TEST_ROOT, "tagged_blocks", filename)
    with open(filepath, "rb") as f:
        assert isinstance(Levels.read(f), Levels)


# The six range records every 'hue2' block has carried since Photoshop 5.0:
# four range values (outer start, inner start, inner end, outer end) and three
# settings (hue, saturation, lightness).
HUE_SATURATION_RANGES = (
    (315, 345, 15, 45),
    (15, 45, 75, 105),
    (75, 105, 135, 165),
    (135, 165, 195, 225),
    (195, 225, 255, 285),
    (255, 285, 315, 345),
)

# What Photoshop writes after those records, taken from
# psd_files/adjustments/huesaturation_colorize_rgb.psd: one (hue, 100, 50)
# triple per range, hue at the midpoint of that range's inner band.
HUE_SATURATION_TRAILER = struct.pack(
    ">18h", *[v for hue in (0, 60, 120, 180, 240, 300) for v in (hue, 100, 50)]
)


def hue_saturation_block(trailer: bytes = b"") -> bytes:
    data = struct.pack(">HBx3h3h", 2, 1, -118, 45, 14, 0, 0, 0)
    for range_values in HUE_SATURATION_RANGES:
        data += struct.pack(">4h3h", *range_values, 0, 0, 0)
    return data + trailer


@pytest.mark.parametrize("trailer", [b"", HUE_SATURATION_TRAILER])
def test_hue_saturation_rw(trailer: bytes) -> None:
    check_read_write(HueSaturation, hue_saturation_block(trailer))


def test_hue_saturation_keeps_trailing_bytes() -> None:
    block = hue_saturation_block(HUE_SATURATION_TRAILER)
    assert len(block) == 136
    assert HueSaturation.frombytes(block).unknown == HUE_SATURATION_TRAILER
