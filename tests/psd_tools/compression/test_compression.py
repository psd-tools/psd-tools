from __future__ import print_function, unicode_literals

import logging

import pytest

from psd_tools.compression import (
    compress,
    decode_prediction,
    decode_rle,
    decompress,
    encode_prediction,
    encode_rle,
)
from psd_tools.constants import Compression

logger = logging.getLogger(__name__)

RAW_IMAGE_3x3_8bit = b"\x00\x01\x02\x01\x01\x01\x01\x00\x00"
RAW_IMAGE_2x2_16bit = b"\x00\x01\x00\x02\x00\x03\x00\x04"
RAW_IMAGE_2x2_32bit = (
    b"\x00\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00\x00\x04"
)
EDGE_CASE_1 = b"\xfe\xfb\xfb\xff\xff\xff\x98\x00\x00\x00\xa9\xff\xf8\xfb\xf3\xec\xfa\xff\xc5\xbb\xf8\xd6\xb7\xe3\xff\xf1\xd8\xfb\xff\xfc\xf6\xff\xff\xf4\xf4\xff\xfe\xe0\xfd\xff\xff\xff\xff\xff\xff\xb2\xc0\xff\xe2\x97\xde\xff\xbcu\xe1\xd4p\xa2\xff\xf2\xd8\xff\xf0hR\xb0\xf6\xc1\xbb\xff\xc8H\xb3\xff\xff\xe1\xf0\xff\xfe\xf0\xf9\xff\xff\xfb\xf6\xf4\xdb\xb9\xff\xf9\x05=\xff\xedT\xa5\xffo\x10\xc2\xff\xf3\xf1\xff\xdaKk\xff\xff\xfb\xf4\xff\xff\xe8\xfc\xff\xad&\xb9\xf8\xce\xb8\xf9\xffk\x10\xa0\xd8\xdf\xfe\xeb\xe6\xfd\xff\xf6\x90\x8d\xff\xff\xe7\xd3\xe7\xa9_\xcf\xff\xb2c\xcc\xff\xba\x80\xe2\xee\x87\x8f\xef\xf2\xc8\xe0\xff\xd2k\xcf\xf2\xd4\xda\xf8\xf3\xce\xdd\xf4\xf9\xfa\xf4\xff\xff\xb8\xbc\xff\x96-\xe5\xf5\xb5\xd4\xff\xc2?\x95\xff\xc8\x96\xff\xff\xdav\xe4\xff\xa5\xd5\xff\xf9\xdb\xe3\xff\xf6\xc8\xe8\xff\xfa\xce\xd2\xff\xd4v\xe9\xff\x9fz\xee\xe9b\x95\xff\xbd6\xac\xff\xc6\x82\xd8\xffa\x1c\xec\xff\xf3\xe5\xe9\xf2iD\xff\xff\xdc\xfc\xf1\x94\xc6\xff\xd9\x1e:\xff\xffd\x86\xff\xcb\x1ap\xfe\xd7\\\x90\xff\xbd\xa1\xff\xde\x00z\xff\x96\x1c\xb7\xff\xc3w\xe3\xdd\x1d\x1f\xfd\xff\xd1\x82\xf3\x8e\x040\xf3\x98\x06\xa5\xa2t"


@pytest.mark.parametrize(
    "fixture, width, height, depth",
    [
        (bytes(bytearray(range(256))), 128, 2, 8),
        (bytes(bytearray(range(256))), 64, 2, 16),
        (bytes(bytearray(range(256))), 32, 2, 32),
    ],
)
def test_prediction(fixture, width, height, depth):
    encoded = encode_prediction(fixture, width, height, depth)
    decoded = decode_prediction(encoded, width, height, depth)
    assert fixture == decoded


@pytest.mark.parametrize(
    "fixture, width, height, depth, version",
    [
        (bytes(bytearray(range(256))), 128, 2, 8, 1),
        (bytes(bytearray(range(256))), 128, 2, 8, 2),
    ],
)
def test_rle(fixture, width, height, depth, version):
    encoded = encode_rle(fixture, width, height, depth, version)
    decoded = decode_rle(encoded, width, height, depth, version)
    assert fixture == decoded


@pytest.mark.parametrize(
    "data, kind, width, height, depth, version",
    [
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
    ],
)
def test_compress_decompress(data, kind, width, height, depth, version):
    compressed = compress(data, kind, width, height, depth, version)
    output = decompress(compressed, kind, width, height, depth, version)
    assert output == data, "output=%r, expected=%r" % (output, data)


# This will fail due to irreversible zlib compression.
@pytest.mark.xfail
@pytest.mark.parametrize(
    "data, width, height, depth",
    [
        (
            b"H\x89\xb2g`8\xc8P\xca\xc0\xd0\xcd\xf0\x85\x81\x81\x87\x01\n\xec1D"
            b"\xed\x0f\x02\xc5\xcc\xba\x81b\xf5<01;\x06F\x06\x86\xf3\x0c\xe9\x8b"
            b"\xe2\xf4\x19\x026\xf9\xcdf(\x9c\x91a\x0f\x920cX\xc4\x10W\xcf\xb0\x89"
            b"\xc1\x8f\x87a\x06C\x06@\x80\x01\x00\x94#\x14\x01",
            5,
            5,
            32,
        )
    ],
)
def test_compress_decompress_fail(data, width, height, depth):
    decoded = decompress(data, Compression.ZIP_WITH_PREDICTION, width, height, depth)
    encoded = compress(decoded, Compression.ZIP_WITH_PREDICTION, width, height, depth)
    assert data == encoded
