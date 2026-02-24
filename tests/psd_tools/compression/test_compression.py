import logging

import pytest

from psd_tools.compression import (
    compress,
    decode_prediction,
    decode_rle,
    decompress,
    encode_prediction,
    encode_rle,
    rle_impl,
)
from psd_tools.constants import Compression

logger = logging.getLogger(__name__)

RAW_IMAGE_3x3_8bit = b"\x00\x01\x02\x01\x01\x01\x01\x00\x00"
RAW_IMAGE_2x2_16bit = b"\x00\x01\x00\x02\x00\x03\x00\x04"
RAW_IMAGE_2x2_32bit = (
    b"\x00\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00\x00\x04"
)
EDGE_CASE_1 = b"\xf9\xfa\xf4\xff\xff\xb8\xbc\xff\x96-\xe5\xf5\xb5\xd4\xff\xc2?\x95\xff\xc8\x96\xff\xff\xdav\xe4\xff\xa5\xd5\xff\xf9\xdb\xe3\xff\xf6\xc8\xe8\xff\xfa\xce\xd2\xff\xd4v\xe9\xff\x9fz\xee\xe9b\x95\xff\xbd6\xac\xff\xc6\x82\xd8\xffa\x1c\xec\xff\xf3\xe5\xe9\xf2iD\xff\xff\xdc\xfc\xf1\x94\xc6\xff\xd9\x1e:\xff\xffd\x86\xff\xcb\x1ap\xfe\xd7\\\x90\xff\xbd\xa1\xff\xde\x00z\xff\x96\x1c\xb7\xff\xc3w\xe3\xdd\x1d\x1f\xfd\xff\xd1\x82\xf3\x8e\x040\xf3\x98\x06\xa5\xa2t"


@pytest.mark.parametrize(
    "fixture, width, height, depth",
    [
        (bytes(bytearray(range(256))), 128, 2, 8),
        (bytes(bytearray(range(256))), 64, 2, 16),
        (bytes(bytearray(range(256))), 32, 2, 32),
    ],
)
def test_prediction(fixture: bytes, width: int, height: int, depth: int) -> None:
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
def test_rle(fixture: bytes, width: int, height: int, depth: int, version: int) -> None:
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
def test_compress_decompress(
    data: bytes, kind: Compression, width: int, height: int, depth: int, version: int
) -> None:
    compressed = compress(data, kind, width, height, depth, version)
    output = decompress(compressed, kind, width, height, depth, version)
    assert output == data, "output=%r, expected=%r" % (output, data)


def test_decompress_rle_overflow_clips() -> None:
    # Header: 1 row of 4 compressed bytes (\x00\x04).
    # Row data: literal run header 0x02 = copy 3 bytes, but row_size is 2.
    # Tolerant decoder clips to 2 bytes → correct decoded output, no fallback.
    rle_data = b"\x00\x04\x02\x00\x00\x00"
    width, height, depth = 2, 1, 8
    result = decompress(rle_data, Compression.RLE, width, height, depth)
    assert result == b"\x00\x00"


# --- Low-level decode() tolerance tests (exercise both Python and Cython impls) ---


def test_decode_rle_repeat_overflow() -> None:
    # 0x82 = repeat-run header: 256 - 0x82 = 126, so repeat 127× next byte.
    # row_size=3 → decoder should clip to 3 repetitions of 0xAA.
    data = bytes([0x82, 0xAA])
    assert rle_impl.decode(data, 3) == b"\xaa\xaa\xaa"


def test_decode_rle_copy_overflow() -> None:
    # 0x02 = copy-run header: copy 3 bytes, but row_size=2.
    # Decoder should clip to 2 bytes.
    data = bytes([0x02, 0x01, 0x02, 0x03])
    assert rle_impl.decode(data, 2) == b"\x01\x02"


def test_decode_rle_copy_truncated_input() -> None:
    # 0x04 = copy-run header: copy 5 bytes, but only 3 bytes follow in the stream.
    # Decoder should copy 3 available bytes and zero-pad the remaining 2.
    data = bytes([0x04, 0x01, 0x02, 0x03])
    assert rle_impl.decode(data, 5) == b"\x01\x02\x03\x00\x00"


def test_decode_rle_lone_repeat_header() -> None:
    # 0x82 = repeat-run header with no following pixel byte (stream ends).
    # Should not raise (previously caused IndexError in Cython); returns zeros.
    data = bytes([0x82])
    assert rle_impl.decode(data, 4) == b"\x00\x00\x00\x00"


def test_decode_rle_short_output() -> None:
    # Stream is valid but encodes fewer bytes than row_size (zero-padded remainder).
    # 0x00 = copy 1 byte (0xFF); row_size=4 → b"\xff\x00\x00\x00"
    data = bytes([0x00, 0xFF])
    assert rle_impl.decode(data, 4) == b"\xff\x00\x00\x00"


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
def test_compress_decompress_fail(
    data: bytes, width: int, height: int, depth: int
) -> None:
    decoded = decompress(data, Compression.ZIP_WITH_PREDICTION, width, height, depth)
    encoded = compress(decoded, Compression.ZIP_WITH_PREDICTION, width, height, depth)
    assert data == encoded
