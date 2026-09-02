import logging
import warnings
import zlib

import pytest

from psd_tools.compression import (
    _safe_zlib_decompress,
    PSDDecompressionWarning,
    compress,
    decode_prediction,
    decode_rle,
    decompress,
    decompressed_size_bound,
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


@pytest.mark.parametrize("width", [1, 3, 5, 7, 8, 9, 20, 100])
@pytest.mark.parametrize("version", [1, 2])
def test_rle_round_trips_a_padded_1bit_row(width: int, version: int) -> None:
    """A 1-bit row is ``ceil(width / 8)`` bytes, and both codecs must say so.

    Each used its own expression and both floored: ``decode_rle()`` read
    ``max(width // 8, 1)`` bytes per row where a 20-pixel row stores three, so
    it dropped a third of every row and left the caller short of a whole
    channel; ``encode_rle()`` wrote the same truncation without even the clamp
    (#768). Distinct bytes per row, so a row read at the wrong stride cannot
    round-trip by coincidence.
    """
    row_size = (width + 7) // 8
    height = 4
    fixture = bytes(
        (row * 0x37 + i * 0x11 + 1) & 0xFF
        for row in range(height)
        for i in range(row_size)
    )
    encoded = encode_rle(fixture, width, height, 1, version)
    assert decode_rle(encoded, width, height, 1, version) == fixture
    assert decompress(encoded, Compression.RLE, width, height, 1, version) == fixture


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


# ---------------------------------------------------------------------------
# Security fix tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    [Compression.ZIP, Compression.ZIP_WITH_PREDICTION],
)
def test_decompress_zip_bomb_falls_back_to_black(kind: Compression) -> None:
    """A zlib payload that expands beyond the declared channel size must not
    exhaust memory; it should fall back to a black channel.
    """
    oversized = zlib.compress(b"\x00" * 10_000)
    result = decompress(oversized, kind, width=2, height=2, depth=8)
    assert result == b"\x00" * 4  # black fallback for 2×2 8-bit


@pytest.mark.parametrize(
    "kind",
    [Compression.ZIP, Compression.ZIP_WITH_PREDICTION],
)
def test_decompress_zip_bomb_emits_psd_warning(kind: Compression) -> None:
    """ZIP bomb fallback must emit PSDDecompressionWarning."""
    oversized = zlib.compress(b"\x00" * 10_000)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        decompress(oversized, kind, width=2, height=2, depth=8)
    assert any(issubclass(w.category, PSDDecompressionWarning) for w in caught)


def test_decompress_rle_failure_emits_psd_warning() -> None:
    """An undecodable RLE channel must emit PSDDecompressionWarning."""
    # version=1 row byte-count table needs height*2 bytes (unsigned short each).
    # Providing only 1 byte forces array.frombytes to raise ValueError (not a
    # multiple of 2), which is the path that triggers the warning.
    bad_rle = b"\x00"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        decompress(bad_rle, Compression.RLE, width=4, height=1, depth=8, version=1)
    assert any(issubclass(w.category, PSDDecompressionWarning) for w in caught)


@pytest.mark.parametrize(
    "bad_kwarg",
    [
        {"width": 0},
        {"width": 300_001},
        {"height": 0},
        {"height": 300_001},
        {"depth": 7},
        {"depth": 0},
    ],
)
def test_decompress_invalid_dimensions_raises(bad_kwarg: dict) -> None:
    """Out-of-spec dimensions must raise ValueError immediately."""
    params: dict = dict(width=4, height=4, depth=8, version=1)
    params.update(bad_kwarg)
    with pytest.raises(ValueError):
        decompress(b"\x00" * 16, Compression.RAW, **params)


# ---------------------------------------------------------------------------
# Issue #411 — corrupted zlib stream (invalid deflate stream, Error -3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", [Compression.ZIP, Compression.ZIP_WITH_PREDICTION])
def test_decompress_corrupted_zlib_falls_back_to_black(kind: Compression) -> None:
    """Corrupted zlib stream (invalid deflate stream, Issue #411) returns black pixels."""
    # Valid zlib header (0x78 0x9c) followed by garbage deflate bytes.
    # zlib raises Error -3 (invalid block type) — not a checksum error.
    corrupt = b"\x78\x9c" + b"\xff" * 20
    result = decompress(corrupt, kind, width=2, height=2, depth=8)
    assert result == b"\x00" * 4


@pytest.mark.parametrize("kind", [Compression.ZIP, Compression.ZIP_WITH_PREDICTION])
def test_decompress_corrupted_zlib_emits_warning(kind: Compression) -> None:
    """Corrupted zlib stream must emit PSDDecompressionWarning with codec name."""
    corrupt = b"\x78\x9c" + b"\xff" * 20
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        decompress(corrupt, kind, width=2, height=2, depth=8)
    psd_warnings = [
        w for w in caught if issubclass(w.category, PSDDecompressionWarning)
    ]
    assert len(psd_warnings) >= 1
    assert kind.name in str(psd_warnings[0].message)


def test_decompress_length_mismatch_raises() -> None:
    """A decompressed payload of wrong length must raise ValueError (integrity check).

    Only ZIP is tested here: for ZIP_WITH_PREDICTION a short payload crashes
    inside decode_prediction (IndexError) before reaching the length check.
    """
    # Compress 5 bytes but declare a 3×3=9 pixel channel.
    short_data = zlib.compress(b"\x00" * 5)
    with pytest.raises(ValueError, match="Decompressed length mismatch"):
        decompress(short_data, Compression.ZIP, width=3, height=3, depth=8)


# ---------------------------------------------------------------------------
# decompressed_size_bound() must bound what decompress() returns (#737)
# ---------------------------------------------------------------------------
#
# The bound is what an allocation guard has to work from: it answers "how many
# bytes can this body become" without inflating anything, so a document can be
# rejected before the buffer exists. Falling below the real result is the
# failure that matters -- that is the hole #737 reports at depth 1 -- so these
# assert the inequality in that direction over every codec and depth, and
# equality for the two codecs whose output size is knowable exactly.


def _packed(width: int, height: int, depth: int) -> bytes:
    """A payload of the row size the codecs actually read.

    ``ceil(width * depth / 8)`` bytes per row -- ``decode_rle()``'s ``row_size``
    and ``decompress()``'s ``length`` divided by ``height``, which since #768
    are the same expression at every depth.
    """
    return bytes(height * ((width * depth + 7) // 8))


# Two of these widths are not a multiple of eight, so at depth 1 their rows
# carry padding bits: 20 pixels in three bytes, 5 in one. The floor the codecs
# used to take dropped that last byte (#768).
@pytest.mark.parametrize("width, height", [(8, 4), (64, 3), (4, 4), (20, 3), (5, 2)])
@pytest.mark.parametrize("kind", [Compression.RAW, Compression.RLE, Compression.ZIP])
@pytest.mark.parametrize("depth", [1, 8, 16, 32])
def test_decompressed_size_bound_is_never_below_the_result(
    depth: int, kind: Compression, width: int, height: int
) -> None:
    """Sweep of the invariant the guard depends on, over codec x depth."""
    body = compress(_packed(width, height, depth), kind, width, height, depth)
    bound = decompressed_size_bound(body, kind, width, height, depth)
    produced = len(decompress(body, kind, width, height, depth))
    assert produced <= bound
    if kind in (Compression.RAW, Compression.RLE):
        # Exact, not merely bounded: RAW returns `data[:length]`, and every RLE
        # row is padded or clipped to `row_size` rather than raising. Only ZIP,
        # whose inflated size cannot be known without inflating, is loose.
        assert produced == bound


def test_a_byte_per_pixel_1bit_body_is_cut_back_to_its_rows() -> None:
    """The crafted body #737 reports, no longer returned whole.

    ``length`` used to be a byte per *pixel* at depth 1 -- eight times the
    packed size -- so a body written that wide passed straight through (the
    ``len(result) != length`` check being skipped below depth 8) and unpacked to
    eight float32 planes. Counting rows instead caps it at the eight times
    smaller size a 64x64 1-bit channel really occupies: RAW truncates to it,
    and ZIP, whose ceiling is the same number, refuses the stream and
    black-fills.
    """
    padded = bytes(64 * 64)  # the old `length`; the real one is 64 * 8
    packed_length = 64 * 8

    body = compress(padded, Compression.RAW, 64, 64, 1)
    bound = decompressed_size_bound(body, Compression.RAW, 64, 64, 1)
    assert len(decompress(body, Compression.RAW, 64, 64, 1)) == bound == packed_length

    body = compress(padded, Compression.ZIP, 64, 64, 1)
    with pytest.warns(PSDDecompressionWarning, match="exceeds expected"):
        result = decompress(body, Compression.ZIP, 64, 64, 1)
    assert result == b"\xff" * packed_length  # black, and black at depth 1 is set


@pytest.mark.parametrize("depth", [1, 8, 16, 32])
def test_black_fill_matches_the_declared_length(depth: int) -> None:
    """A failed channel is replaced by exactly ``length`` bytes, at every depth.

    The substitute used to be a PIL image whose mode was picked from the depth
    -- ``"L"`` for 8, ``"RGBA"`` for anything else -- so depth 16 came back at
    four bytes per pixel where the channel declares two. Every reader
    downstream then saw a 16-bit document's channels at twice their width, and
    the bound above could not have held either.

    Depth 1 joined the sweep with #768: ``length`` counting packed rows is what
    makes a fill expressible there at all, and black is ``0xff`` rather than
    zero, an inked bitmap pixel being a *set* bit. Before, this channel ended
    the read.
    """
    corrupt = b"\x78\x9c" + b"\xff" * 20  # valid zlib header, garbage deflate
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PSDDecompressionWarning)
        result = decompress(corrupt, Compression.ZIP, width=4, height=4, depth=depth)
    length = 4 * ((4 * depth + 7) // 8)
    assert result == (b"\xff" if depth == 1 else b"\x00") * length
    assert length <= decompressed_size_bound(corrupt, Compression.ZIP, 4, 4, depth)


def test_safe_zlib_decompress_honours_its_own_ceiling() -> None:
    """Exactly ``max_length + 1`` bytes must be refused, not returned.

    The probe asks zlib for one byte more than the limit so that an oversize
    stream reveals itself through ``unconsumed_tail``. A stream inflating to
    precisely ``max_length + 1`` consumed all of its input, left no tail, and so
    was returned a byte over the ceiling this function documents -- eight extra
    float32 values once a 1-bit reader unpacked it (#737).
    """
    assert len(_safe_zlib_decompress(zlib.compress(bytes(8)), 8)) == 8
    for oversize in (9, 10, 4096):
        with pytest.raises(ValueError, match="exceeds expected maximum"):
            _safe_zlib_decompress(zlib.compress(bytes(oversize)), 8)


def test_a_zip_stream_one_byte_over_length_degrades_to_black() -> None:
    """From depth 8 up, the refused stream black-fills rather than raising.

    It used to reach the ``len(result) != length`` check and raise; being caught
    by the ceiling instead turns it into the warning-and-degrade path every other
    undecodable channel takes.
    """
    body = zlib.compress(bytes(4 * 4 + 1))  # `length` + 1 for a 4x4 8-bit channel
    with pytest.warns(PSDDecompressionWarning, match="exceeds expected"):
        result = decompress(body, Compression.ZIP, 4, 4, 8)
    assert result == bytes(4 * 4)


def test_zip_with_prediction_at_depth_1_degrades_rather_than_ending_the_read() -> None:
    """``decode_prediction`` rejects depth 1 outright; that no longer ends the read.

    The codec has no 1-bit form and never will, so this pair always fails. What
    changed with #768 is what follows the failure: ``length`` counting packed
    rows makes a black channel expressible at depth 1, so the caller gets one
    instead of a ``RuntimeError``.
    """
    body = compress(bytes(4), Compression.ZIP, 4, 4, 1)  # inflates to `length`
    with pytest.warns(PSDDecompressionWarning, match="Invalid pixel size"):
        result = decompress(body, Compression.ZIP_WITH_PREDICTION, 4, 4, 1)
    assert result == b"\xff" * 4  # four rows, one byte each, all inked


@pytest.mark.parametrize("depth", [1, 8, 16, 32])
def test_decompress_failure_warning_states_what_follows(depth: int) -> None:
    """The warning describes the read the caller actually receives.

    Raised in review of #769, when the black fill stopped at depth 8 and the
    text did not: a 1-bit failure announced a degraded read and then raised. It
    now announces one and delivers one, at every depth.
    """
    corrupt = b"\x78\x9c" + b"\xff" * 20  # valid zlib header, garbage deflate
    with pytest.warns(PSDDecompressionWarning, match="channel replaced with black"):
        decompress(corrupt, Compression.ZIP, 4, 4, depth)
