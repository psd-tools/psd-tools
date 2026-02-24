from typing import Any

import pytest

import psd_tools.compression._rle as _rle  # type: ignore[import-not-found]
import psd_tools.compression.rle as rle

from .test_compression import RAW_IMAGE_3x3_8bit, EDGE_CASE_1


def test_identical() -> None:
    size = len(RAW_IMAGE_3x3_8bit)
    encoded = rle.encode(RAW_IMAGE_3x3_8bit)
    encoded_c = _rle.encode(RAW_IMAGE_3x3_8bit)
    assert encoded == encoded_c
    decoded = rle.decode(encoded, size)
    decoded_c = _rle.decode(encoded_c, size)
    assert decoded == RAW_IMAGE_3x3_8bit
    assert decoded_c == RAW_IMAGE_3x3_8bit

    size = len(EDGE_CASE_1)
    encoded = rle.encode(EDGE_CASE_1)
    encoded_c = _rle.encode(EDGE_CASE_1)
    assert encoded == encoded_c
    decoded = rle.decode(encoded, size)
    decoded_c = _rle.decode(encoded_c, size)
    assert decoded == EDGE_CASE_1
    assert decoded_c == EDGE_CASE_1


@pytest.mark.parametrize(
    ("mod, data, size, expected"),
    [
        # 0xfd = repeat-run: 256-253=3, so repeat 4× byte 0x01.
        # size=3 → overflow clipped: b'\x01\x01\x01'
        (rle, b"\xfd\x01", 3, b"\x01\x01\x01"),
        (_rle, b"\xfd\x01", 3, b"\x01\x01\x01"),
        # size=5 → 4 real bytes + 1 zero-padded: b'\x01\x01\x01\x01\x00'
        (rle, b"\xfd\x01", 5, b"\x01\x01\x01\x01\x00"),
        (_rle, b"\xfd\x01", 5, b"\x01\x01\x01\x01\x00"),
        # 0x02 = copy-run: copy 3 bytes (0x01 0x02 0x03).
        # size=2 → overflow clipped: b'\x01\x02'
        (rle, b"\x02\x01\x02\x03", 2, b"\x01\x02"),
        (_rle, b"\x02\x01\x02\x03", 2, b"\x01\x02"),
        # size=4 → 3 real bytes + 1 zero-padded: b'\x01\x02\x03\x00'
        (rle, b"\x02\x01\x02\x03", 4, b"\x01\x02\x03\x00"),
        (_rle, b"\x02\x01\x02\x03", 4, b"\x01\x02\x03\x00"),
    ],
)
def test_tolerant_decode(mod: Any, data: bytes, size: int, expected: bytes) -> None:
    # The decoder must never raise; it clips overflow runs and zero-pads short output.
    result = mod.decode(data, size)
    assert result == expected
    assert len(result) == size
