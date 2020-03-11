from __future__ import unicode_literals, print_function
import pytest
import logging
from psd_tools.compression import (
    compress, decompress, encode_prediction, decode_prediction,
    encode_rle, decode_rle
)
from psd_tools.constants import Compression

logger = logging.getLogger(__name__)

RAW_IMAGE_3x3_8bit = b'\x00\x01\x02\x01\x01\x01\x01\x00\x00'
RAW_IMAGE_2x2_16bit = b'\x00\x01\x00\x02\x00\x03\x00\x04'
RAW_IMAGE_2x2_32bit = (
    b'\x00\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00\x00\x04'
)


@pytest.mark.parametrize(
    'fixture, width, height, depth', [
        (bytes(bytearray(range(256))), 128, 2, 8),
        (bytes(bytearray(range(256))), 64, 2, 16),
        (bytes(bytearray(range(256))), 32, 2, 32),
    ]
)
def test_prediction(fixture, width, height, depth):
    encoded = encode_prediction(fixture, width, height, depth)
    decoded = decode_prediction(encoded, width, height, depth)
    assert fixture == decoded


@pytest.mark.parametrize(
    'fixture, width, height, depth, version', [
        (bytes(bytearray(range(256))), 128, 2, 8, 1),
        (bytes(bytearray(range(256))), 128, 2, 8, 2),
    ]
)
def test_rle(fixture, width, height, depth, version):
    encoded = encode_rle(fixture, width, height, depth, version)
    decoded = decode_rle(encoded, width, height, depth, version)
    assert fixture == decoded


@pytest.mark.parametrize(
    'data, kind, width, height, depth, version', [
        (RAW_IMAGE_3x3_8bit, Compression.RAW, 3, 3, 8, 1),
        (RAW_IMAGE_3x3_8bit, Compression.RLE, 3, 3, 8, 1),
        (RAW_IMAGE_3x3_8bit, Compression.RLE, 3, 3, 8, 2),
        (RAW_IMAGE_3x3_8bit, Compression.ZIP, 3, 3, 8, 1),
        (RAW_IMAGE_3x3_8bit, Compression.ZIP_WITH_PREDICTION, 3, 3, 8, 1),
        (RAW_IMAGE_2x2_16bit, Compression.RAW, 2, 2, 16, 1),
        (RAW_IMAGE_2x2_16bit, Compression.RLE, 2, 2, 16, 1),
        (RAW_IMAGE_2x2_16bit, Compression.RLE, 2, 2, 16, 2),
        (RAW_IMAGE_2x2_16bit, Compression.ZIP, 2, 2, 16, 1),
        (RAW_IMAGE_2x2_16bit, Compression.ZIP_WITH_PREDICTION, 2, 2, 16, 1),
        (RAW_IMAGE_2x2_32bit, Compression.RAW, 2, 2, 32, 1),
        (RAW_IMAGE_2x2_32bit, Compression.RLE, 2, 2, 32, 1),
        (RAW_IMAGE_2x2_32bit, Compression.RLE, 2, 2, 32, 2),
        (RAW_IMAGE_2x2_32bit, Compression.ZIP, 2, 2, 32, 1),
        (RAW_IMAGE_2x2_32bit, Compression.ZIP_WITH_PREDICTION, 2, 2, 32, 1),
    ]
)
def test_compress_decompress(data, kind, width, height, depth, version):
    compressed = compress(data, kind, width, height, depth, version)
    output = decompress(compressed, kind, width, height, depth, version)
    assert output == data, 'output=%r, expected=%r' % (output, data)


# This will fail due to irreversible zlib compression.
@pytest.mark.xfail
@pytest.mark.parametrize(
    'data, width, height, depth', [(
        b'H\x89\xb2g`8\xc8P\xca\xc0\xd0\xcd\xf0\x85\x81\x81\x87\x01\n\xec1D'
        b'\xed\x0f\x02\xc5\xcc\xba\x81b\xf5<01;\x06F\x06\x86\xf3\x0c\xe9\x8b'
        b'\xe2\xf4\x19\x026\xf9\xcdf(\x9c\x91a\x0f\x920cX\xc4\x10W\xcf\xb0\x89'
        b'\xc1\x8f\x87a\x06C\x06@\x80\x01\x00\x94#\x14\x01', 5, 5, 32
    )]
)
def test_compress_decompress_fail(data, width, height, depth):
    decoded = decompress(
        data, Compression.ZIP_WITH_PREDICTION, width, height, depth
    )
    encoded = compress(
        decoded, Compression.ZIP_WITH_PREDICTION, width, height, depth
    )
    assert data == encoded
