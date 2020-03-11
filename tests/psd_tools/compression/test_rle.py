import pytest
import logging
import psd_tools.compression.rle as rle
import psd_tools.compression._rle as _rle
from .test_compression import RAW_IMAGE_3x3_8bit


def test_identical():
    size = len(RAW_IMAGE_3x3_8bit)
    encoded = rle.encode(RAW_IMAGE_3x3_8bit)
    encoded_c = _rle.encode(RAW_IMAGE_3x3_8bit)
    assert encoded == encoded_c
    decoded = rle.decode(encoded, size)
    decoded_c = _rle.decode(encoded_c, size)
    assert decoded == RAW_IMAGE_3x3_8bit
    assert decoded_c == RAW_IMAGE_3x3_8bit


@pytest.mark.parametrize(('mod, data, size'), [
    # b'\x01\x01\x01\x01'
    (rle, b'\xfd\x01', 3),
    (rle, b'\xfd\x01', 5),
    (_rle, b'\xfd\x01', 3),
    (_rle, b'\xfd\x01', 5),
    # b'\x01\x02\x03'
    (rle, b'\x02\x01\x02\x03', 2),
    (rle, b'\x02\x01\x02\x03', 4),
    (_rle, b'\x02\x01\x02\x03', 2),
    (_rle, b'\x02\x01\x02\x03', 4),
])
def test_malicious(mod, data, size):
    with pytest.raises(ValueError):
        mod.decode(data, size)
