import struct
import subprocess
import sys
import warnings

import numpy as np
import pytest

import psd_tools.compression as codecs
from psd_tools.compression import (
    DecompressionLimitError,
    compress,
    decode_rle,
    decompress,
    rle,
)
from psd_tools.constants import Compression
from psd_tools.psd.header import FileHeader
from psd_tools.psd.image_data import ImageData
from psd_tools.psd.layer_and_mask import ChannelData
from psd_tools.psd.patterns import VirtualMemoryArray


def forbidden(*args, **kwargs):
    pytest.fail("allocation or codec reached before rejection")


@pytest.mark.parametrize("entry", [decode_rle, decompress])
@pytest.mark.parametrize("version", [1, 2])
def test_empty_rle_rows_rejected_before_allocation(monkeypatch, caplog, entry, version):
    height = 100_000
    data = bytes(height * (2 if version == 1 else 4))
    monkeypatch.setattr(codecs, "read_be_array", forbidden)
    monkeypatch.setattr(codecs.rle_impl, "decode", forbidden)
    with warnings.catch_warnings(record=True) as emitted:
        with pytest.raises(DecompressionLimitError, match="RLE output"):
            if entry is decode_rle:
                entry(data, 300_000, height, 32, version)
            else:
                entry(data, Compression.RLE, 300_000, height, 32, version)
    assert not emitted
    assert not caplog.records


@pytest.mark.parametrize("kind", list(Compression))
def test_output_limit_rejects_before_codec_or_recovery(monkeypatch, kind):
    monkeypatch.setattr(codecs, "decode_rle", forbidden)
    monkeypatch.setattr(codecs, "_safe_zlib_decompress", forbidden)
    monkeypatch.setattr(codecs, "decode_prediction", forbidden)
    with warnings.catch_warnings(record=True) as emitted:
        with pytest.raises(DecompressionLimitError, match="max_output_bytes=3"):
            decompress(b"abcd", kind, 2, 2, 8, max_output_bytes=3)
    assert not emitted


@pytest.mark.parametrize("kind", list(Compression))
@pytest.mark.parametrize("depth", [1, 8, 16, 32])
@pytest.mark.parametrize("version", [1, 2])
def test_exact_output_limit_roundtrip(kind, depth, version):
    if depth == 1 and kind == Compression.ZIP_WITH_PREDICTION:
        pytest.skip("prediction does not support bitmap depth")
    data = bytes(2 * ((9 * depth + 7) // 8))
    encoded = compress(data, kind, 9, 2, depth, version)
    assert (
        decompress(
            encoded, kind, 9, 2, depth, version, max_output_bytes=np.int64(len(data))
        )
        == data
    )
    with pytest.raises(DecompressionLimitError):
        decompress(encoded, kind, 9, 2, depth, version, max_output_bytes=len(data) - 1)


def test_raw_short_bitmap_uses_actual_output_bound():
    assert decompress(b"a", Compression.RAW, 100, 100, 1, max_output_bytes=1) == b"a"


@pytest.mark.parametrize(
    "kind, payload",
    [
        (Compression.RLE, b""),
        (Compression.ZIP, b"bad"),
        (Compression.ZIP_WITH_PREDICTION, b"bad"),
    ],
)
def test_small_failed_decode_with_finite_limit_still_degrades(kind, payload):
    with pytest.warns(codecs.PSDDecompressionWarning):
        assert decompress(payload, kind, 4, 1, 8, max_output_bytes=4) == bytes(4)


@pytest.mark.parametrize(
    "value, error",
    [
        (True, TypeError),
        (1.5, TypeError),
        ("4", TypeError),
        (0, ValueError),
        (-1, ValueError),
    ],
)
@pytest.mark.parametrize("entry", [decompress, decode_rle])
def test_invalid_output_limits_rejected_before_allocation(
    monkeypatch, value, error, entry
):
    monkeypatch.setattr(codecs, "read_be_array", forbidden)
    monkeypatch.setattr(codecs.rle_impl, "decode", forbidden)
    with pytest.raises(error, match="positive integer or None"):
        if entry is decode_rle:
            entry(b"", 1, 1, 8, 1, max_output_bytes=value)
        else:
            entry(b"", Compression.RLE, 1, 1, 8, max_output_bytes=value)


@pytest.mark.parametrize(
    "params",
    [
        (0, 1, 8, 1),
        (1, 300001, 8, 1),
        (300001, 1, 8, 1),
        (1, 1, 2, 1),
        (1, 1, 8, 0),
        (1, 1, 8, 3),
    ],
)
def test_direct_rle_invalid_dimensions_and_version(monkeypatch, params):
    monkeypatch.setattr(codecs, "read_be_array", forbidden)
    with pytest.raises(ValueError):
        decode_rle(b"", *params)


@pytest.mark.parametrize("use_python", [False, True])
def test_rle_valid_maximum_ratio_and_small_padding(monkeypatch, use_python):
    if use_python:
        monkeypatch.setattr(codecs, "rle_impl", rle)
    monkeypatch.setattr(codecs, "MAX_DEGRADED_BYTES", 16)
    data = struct.pack(">2H", 2, 2) + b"\x81\xaa" * 2
    assert decode_rle(data, 128, 2, 8, 1, max_output_bytes=256) == b"\xaa" * 256
    monkeypatch.setattr(codecs, "MAX_DEGRADED_BYTES", 16 * 1024**2)
    assert decode_rle(b"\x00\x00", 8, 1, 8, 1) == bytes(8)
    assert decompress(b"\x00\x00", Compression.RLE, 8, 1, 8) == bytes(8)


def test_rle_guard_opt_out_preserves_tolerance(monkeypatch):
    monkeypatch.setattr(codecs, "MAX_DEGRADED_BYTES", 1)
    monkeypatch.setattr(codecs, "MAX_DEGRADED_RATIO", 1)
    with pytest.raises(DecompressionLimitError):
        decode_rle(b"\x00\x00", 8, 1, 8, 1)
    monkeypatch.setattr(codecs, "MAX_DEGRADED_BYTES", None)
    assert decode_rle(b"\x00\x00", 8, 1, 8, 1, max_output_bytes=None) == bytes(8)
    with pytest.raises(DecompressionLimitError):
        decode_rle(b"\x00\x00", 8, 1, 8, 1, max_output_bytes=7)


def test_rle_expansion_requires_both_thresholds(monkeypatch):
    monkeypatch.setattr(codecs, "MAX_DEGRADED_BYTES", 16)
    monkeypatch.setattr(codecs, "MAX_DEGRADED_RATIO", 10)
    assert decode_rle(bytes(2), 16, 1, 8, 1) == bytes(16)
    assert decode_rle(bytes(2), 20, 1, 8, 1) == bytes(20)
    with pytest.raises(DecompressionLimitError):
        decode_rle(bytes(2), 21, 1, 8, 1)


def test_failed_decode_guard_still_rejects_black_fill(monkeypatch):
    monkeypatch.setattr(codecs, "MAX_DEGRADED_BYTES", 1)
    monkeypatch.setattr(codecs, "MAX_DEGRADED_RATIO", 1)
    with pytest.warns(codecs.PSDDecompressionWarning):
        with pytest.raises(DecompressionLimitError, match="failed to decode"):
            decompress(b"bad", Compression.ZIP, 8, 1, 8)


def test_low_level_get_data_output_limits():
    header = FileHeader(width=2, height=2, channels=3, depth=8)
    image = ImageData(compression=Compression.RAW, data=bytes(12))
    with pytest.raises(DecompressionLimitError):
        image.get_data(header, max_output_bytes=11)
    assert image.get_data(header, max_output_bytes=12) == [bytes(4)] * 3
    channel = ChannelData(compression=Compression.RAW, data=bytes(4))
    with pytest.raises(DecompressionLimitError):
        channel.get_data(2, 2, 8, max_output_bytes=3)
    assert channel.get_data(2, 2, 8, max_output_bytes=4) == bytes(4)
    pattern = VirtualMemoryArray(
        is_written=1, depth=8, rectangle=(0, 0, 2, 2), data=bytes(4)
    )
    with pytest.raises(DecompressionLimitError):
        pattern.get_data(max_output_bytes=3)
    assert pattern.get_data(max_output_bytes=4) == bytes(4)


def test_rle_guard_in_optimized_python():
    code = """
from psd_tools.compression import decode_rle, DecompressionLimitError
try:
    decode_rle(bytes(200000), 300000, 100000, 32, 1)
except DecompressionLimitError:
    pass
else:
    raise RuntimeError('limit bypassed')
"""
    subprocess.run([sys.executable, "-O", "-c", code], check=True)
