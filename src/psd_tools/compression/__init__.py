"""
Image compression utilities for PSD channel data.

This subpackage provides compression and decompression codecs for raw pixel
data in PSD files. Adobe Photoshop supports multiple compression methods for
channel data to reduce file size.

Supported compression methods:

- **RAW** (``Compression.RAW``): Uncompressed raw pixel data
- **RLE** (``Compression.RLE``): Apple PackBits run-length encoding
- **ZIP** (``Compression.ZIP``): ZIP/Deflate compression without prediction
- **ZIP_WITH_PREDICTION** (``Compression.ZIP_WITH_PREDICTION``): ZIP with delta encoding

The RLE codec includes both a pure Python implementation and a Cython-optimized
version (``_rle.pyx``) that provides significant performance improvements. The
Cython version is used automatically when available, with graceful fallback to
pure Python.

Key functions:

- :py:func:`compress`: Compress raw pixel data using specified method
- :py:func:`decompress`: Decompress pixel data back to raw bytes
- :py:func:`decompressed_size_bound`: Upper bound on what :py:func:`decompress`
  will return, without decompressing anything
- :py:func:`encode_rle`: RLE encoding for a single channel
- :py:func:`decode_rle`: RLE decoding for a single channel

Example usage::

    from psd_tools.compression import compress, decompress
    from psd_tools.constants import Compression

    # Compress raw channel data
    compressed = compress(
        data=raw_pixels,
        compression=Compression.RLE,
        width=100,
        height=100,
        depth=8,
        version=1
    )

    # Decompress back to raw data
    raw_pixels = decompress(
        data=compressed,
        compression=Compression.RLE,
        width=100,
        height=100,
        depth=8,
        version=1
    )

Performance notes:

- RLE is most effective for images with large uniform areas
- ZIP with prediction works well for continuous-tone images
- The Cython RLE codec can be 10-100x faster than pure Python
- Compression method is chosen per-channel when saving PSD files

The compression module handles various bit depths (8, 16, 32-bit per channel)
and implements delta encoding for improved compression ratios on certain
image types.
"""

import array
import io
import logging
import operator
import warnings
import zlib

import numpy as np

from psd_tools.constants import Compression
from psd_tools.psd.parse_limits import ParseLimitError
from psd_tools.psd.bin_utils import (
    read_be_array,
    write_be_array,
)

try:
    from . import _rle as rle_impl  # type: ignore[import-not-found,attr-defined]
except ImportError:
    from . import rle as rle_impl

logger = logging.getLogger(__name__)


class PSDDecompressionWarning(UserWarning):
    """Issued when channel data cannot be fully decompressed.

    The affected channel is replaced with black pixels, at every depth --
    ``length`` bytes of whichever value that depth spells black as, zero from
    depth 8 up and ``0xff`` at depth 1, where an inked pixel is a *set* bit.
    Catch or filter this warning to detect silently degraded images::

        import warnings
        from psd_tools.compression import PSDDecompressionWarning

        with warnings.catch_warnings():
            warnings.simplefilter("error", PSDDecompressionWarning)
            psd = PSDImage.open("file.psd")
    """


class DecompressionLimitError(ValueError):
    """Raised before decoding when channel output exceeds a byte limit."""


_VALID_DEPTHS: frozenset[int] = frozenset((1, 8, 16, 32))
_MAX_DIMENSION: int = 300_000  # PSD/PSB hard limit per the Adobe spec

# Reject excessive RLE expansion and failed-decode black fills (CWE-789).
# Set MAX_DEGRADED_BYTES to None to disable the guard (also disables the ratio check).
MAX_DEGRADED_BYTES: int | None = 16 * 1024 * 1024
MAX_DEGRADED_RATIO: int = 1000


def _validate_dimensions(width: int, height: int, depth: int) -> None:
    if width < 1 or width > _MAX_DIMENSION:
        raise ValueError("width %d out of range [1, %d]" % (width, _MAX_DIMENSION))
    if height < 1 or height > _MAX_DIMENSION:
        raise ValueError("height %d out of range [1, %d]" % (height, _MAX_DIMENSION))
    if depth not in _VALID_DEPTHS:
        raise ValueError("depth %d not in %s" % (depth, sorted(_VALID_DEPTHS)))


def _check_output_limit(length: int, max_output_bytes: int | None) -> None:
    if max_output_bytes is None:
        return
    if isinstance(max_output_bytes, bool):
        raise TypeError("max_output_bytes must be a positive integer or None")
    try:
        limit = operator.index(max_output_bytes)
    except TypeError:
        raise TypeError("max_output_bytes must be a positive integer or None") from None
    if limit <= 0:
        raise ValueError("max_output_bytes must be a positive integer or None")
    if length > limit:
        raise DecompressionLimitError(
            "Decompressed output bound of %d bytes exceeds max_output_bytes=%d"
            % (length, limit)
        )


def _check_expansion(length: int, input_length: int, reason: str) -> None:
    if (
        MAX_DEGRADED_BYTES is not None
        and length > MAX_DEGRADED_BYTES
        and length > input_length * MAX_DEGRADED_RATIO
    ):
        raise DecompressionLimitError(
            "Refusing to allocate %d bytes for %s from %d input bytes; set "
            "psd_tools.compression.MAX_DEGRADED_BYTES = None to allow it."
            % (length, reason, input_length)
        )


def _row_size(width: int, depth: int) -> int:
    """Bytes one row of *width* pixels occupies at *depth*.

    Rounded **up**: a row is padded to a byte boundary, so 20 pixels at depth 1
    occupy three bytes, the last of them four pixels and four bits of padding
    (#768). From depth 8 up the division is exact.
    """
    return (width * depth + 7) // 8


def _channel_length(width: int, height: int, depth: int) -> int:
    """Bytes a channel of these dimensions occupies once decompressed.

    Shared by :func:`decompress`, which sizes every codec's output by it, and by
    :func:`decompressed_size_bound`, which has to predict that output without
    producing it. Rows all the way down: ``height`` of them, each
    :func:`_row_size` wide.
    """
    return height * _row_size(width, depth)


def _warn_decompress_failure(
    codec: str,
    exc: Exception,
    width: int,
    height: int,
    depth: int,
    version: int,
) -> None:
    """Log and emit a PSDDecompressionWarning for a failed channel decode."""
    msg = (
        "%s decode failed (%s: %s); channel replaced with black. "
        "width=%d height=%d depth=%d version=%d"
    ) % (
        codec,
        type(exc).__name__,
        exc,
        width,
        height,
        depth,
        version,
    )
    logger.warning(msg)
    warnings.warn(msg, PSDDecompressionWarning, stacklevel=3)


def _safe_zlib_decompress(data: bytes, max_length: int) -> bytes:
    """Decompress *data* with a hard upper bound on output size.

    Unlike :func:`zlib.decompress`, this function raises :exc:`ValueError`
    if the decompressed output would exceed *max_length* bytes, preventing
    memory exhaustion from crafted ZIP-bomb payloads.
    """
    d = zlib.decompressobj()
    # One byte more than the limit, so that a stream which really is oversize
    # gives that byte away instead of ending exactly at the boundary. It has to
    # be rejected as well: without the length test a stream inflating to
    # precisely `max_length + 1` was consumed whole, left no
    # `unconsumed_tail`, and was returned a byte over the ceiling this function
    # documents -- caught downstream as a length mismatch from depth 8 up, and
    # at depth 1, where that check is skipped, unpacked into eight float32
    # values no estimate allowed for (#737). Such a stream never reaches either
    # now: it is refused here, and `decompress()` gives the caller a black
    # channel in its place, at depth 1 as at any other since #768.
    out = d.decompress(data, max_length + 1)
    # Then drain whatever the codec still holds, bounded the same way, rather
    # than calling `flush()`: output can outlive its input, a match being
    # expanded from state as it is written, so inflate can in principle stop
    # with the input consumed and bytes still pending -- and `flush()` emits
    # that remainder with no ceiling at all, which is the allocation this
    # function exists to prevent. CPython appears never to do it (it leaves the
    # unread input, the trailing adler32 at the least, in `unconsumed_tail`
    # whenever output is pending; 140k crafted and truncated streams produced
    # no such case, and 36k inputs agree byte for byte and exception for
    # exception with the `flush()` form). The loop is so that the ceiling does
    # not rest on that.
    #
    # Collected rather than concatenated: `out += chunk` on a `bytes` copies the
    # whole buffer every iteration. Accumulating into a `bytearray` from the
    # start would instead copy every ZIP channel in the file one extra time on
    # the way out -- on the path where the loop yields nothing, which is every
    # path measured -- so the join happens only if the loop produced something.
    extra: list[bytes] = []
    total = len(out)
    while not d.unconsumed_tail and total <= max_length:
        chunk = d.decompress(b"", max_length + 1 - total)
        if not chunk:
            break
        extra.append(chunk)
        total += len(chunk)
    if d.unconsumed_tail or total > max_length:
        raise ValueError(
            "Decompressed size exceeds expected maximum of %d bytes" % max_length
        )
    if extra:
        return b"".join([out, *extra])
    return out


def compress(
    data: bytes,
    compression: Compression,
    width: int,
    height: int,
    depth: int,
    version: int = 1,
) -> bytes:
    """Compress raw data.

    :param data: raw data bytes to write.
    :param compression: compression type, see :py:class:`.Compression`.
    :param width: width.
    :param height: height.
    :param depth: bit depth of the pixel.
    :param version: psd file version.
    :return: compressed data bytes.
    """
    if compression == Compression.RAW:
        result = data
    elif compression == Compression.RLE:
        result = encode_rle(data, width, height, depth, version)
    elif compression == Compression.ZIP:
        result = zlib.compress(data)
    else:
        encoded = encode_prediction(data, width, height, depth)
        result = zlib.compress(encoded)

    return result


def decompress(
    data: bytes,
    compression: Compression,
    width: int,
    height: int,
    depth: int,
    version: int = 1,
    *,
    max_output_bytes: int | None = None,
) -> bytes:
    """Decompress raw data.

    :param data: compressed data bytes.
    :param compression: compression type,
            see :py:class:`~psd_tools.constants.Compression`.
    :param width: width in pixels; must be in [1, 300000].
    :param height: height in pixels; must be in [1, 300000].
    :param depth: bit depth of the pixel; must be one of 1, 8, 16, 32.
    :param version: psd file version.
    :param max_output_bytes: positive output-byte ceiling; None disables it.
    :return: decompressed data bytes.
    :raises ValueError: if *width*, *height*, or *depth* are out of range.
    :raises DecompressionLimitError: if an output or expansion limit is exceeded.
    """
    _validate_dimensions(width, height, depth)

    length = _channel_length(width, height, depth)
    _check_output_limit(
        min(len(data), length) if compression == Compression.RAW else length,
        max_output_bytes,
    )

    result: bytes | None = None
    if compression == Compression.RAW:
        result = data[:length]
    elif compression == Compression.RLE:
        try:
            result = decode_rle(data, width, height, depth, version)
        except (ParseLimitError, DecompressionLimitError):
            raise
        except (ValueError, IndexError, OSError) as e:
            _warn_decompress_failure("RLE", e, width, height, depth, version)
            result = None
    elif compression == Compression.ZIP:
        try:
            result = _safe_zlib_decompress(data, length)
        except (ValueError, zlib.error) as e:
            _warn_decompress_failure("ZIP", e, width, height, depth, version)
            result = None
    else:
        try:
            decompressed = _safe_zlib_decompress(data, length)
            result = decode_prediction(decompressed, width, height, depth)
        except (ValueError, zlib.error) as e:
            _warn_decompress_failure(
                "ZIP_WITH_PREDICTION", e, width, height, depth, version
            )
            result = None

    if result is None:
        # At every depth: `length` counts packed rows, so a channel of
        # `length` black bytes exists at depth 1 as much as at depth 8 and the
        # fill does not have to stop where byte-per-pixel arithmetic would
        # (#768).
        _check_expansion(length, len(data), "a channel that failed to decode")
        # Exactly `length`, which the mismatch check opposite demands of a
        # successful decode and this substitute has to honour too. It was
        # built as a PIL image whose mode was picked from the depth -- "L"
        # for 8, "RGBA" otherwise -- so depth 16 came back at four bytes per
        # pixel against a `length` of two, and every reader downstream saw a
        # channel twice its declared width (#737).
        #
        # Black is not zero at every depth. A bitmap-mode document stores its
        # inked pixels *set* -- the ground truth Photoshop writes, and what
        # `pil_io._create_image()`'s inverted "1;I" raw mode reads -- so at
        # depth 1 the black byte is 0xff and zeroes would substitute a blank
        # white channel instead.
        result = b"\xff" * length if depth == 1 else bytes(length)
        logger.warning("Failed channel has been replaced by black")
    elif depth >= 8 and len(result) != length:
        # Still gated: a short 1-bit body is returned as it stands rather than
        # rejected, which is what it has always done. Raising on it would be a
        # new exception on a read path, not a fix to one.
        raise ValueError(
            "Decompressed length mismatch: got %d, expected %d" % (len(result), length)
        )

    return result


def decompressed_size_bound(
    data: bytes,
    compression: Compression,
    width: int,
    height: int,
    depth: int,
    version: int = 1,
) -> int:
    """Upper bound on the number of bytes :py:func:`decompress` will return.

    Answerable without decompressing, so an allocation guard can reject a
    document *before* the buffer exists.

    ``length`` is :py:func:`decompress`'s own ``height`` rows of
    :func:`_row_size`. The bound is exact for RAW and RLE and an over-estimate
    for the two ZIP codecs; a malformed body only comes back smaller, which is
    the safe direction for a guard.

    ZIP is bounded only because ``_safe_zlib_decompress()`` is given ``length``
    as its ceiling, as is the black fill for a channel that fails to decode;
    loosen either and this stops being an upper bound.

    RAW under-runs by design (``data[:length]``), hence the ``min`` on its
    branch alone. A ZIP body can also inflate short; ``decompress()``'s mismatch
    check rejects that at depth 8 and up, so it reaches a caller at depth 1
    only. RLE is exact whenever it returns, padding or clipping each row.
    """
    length = _channel_length(width, height, depth)
    if compression == Compression.RAW:
        return min(len(data), length)
    return length


def encode_rle(data: bytes, width: int, height: int, depth: int, version: int) -> bytes:
    row_size = _row_size(width, depth)
    with io.BytesIO(data) as fp:
        rows = [rle_impl.encode(fp.read(row_size)) for _ in range(height)]
    bytes_counts = array.array(("H", "I")[version - 1], map(len, rows))
    encoded = b"".join(rows)

    with io.BytesIO() as fp:
        write_be_array(fp, bytes_counts)
        fp.write(encoded)
        result = fp.getvalue()

    return result


def decode_rle(
    data: bytes,
    width: int,
    height: int,
    depth: int,
    version: int,
    *,
    max_output_bytes: int | None = None,
) -> bytes:
    """Decode RLE rows, checking output limits before reading or allocating.

    ``max_output_bytes`` is a positive byte ceiling or ``None`` to disable it.
    Excessive expansion is also rejected by ``MAX_DEGRADED_BYTES`` and
    ``MAX_DEGRADED_RATIO``, including zero-padding of incomplete rows.
    """
    _validate_dimensions(width, height, depth)
    if version not in (1, 2):
        raise ValueError("version must be 1 or 2")
    length = _channel_length(width, height, depth)
    _check_output_limit(length, max_output_bytes)
    _check_expansion(length, len(data), "RLE output")
    try:
        row_size = _row_size(width, depth)
        with io.BytesIO(data) as fp:
            bytes_counts = read_be_array(("H", "I")[version - 1], height, fp)
            return b"".join(
                rle_impl.decode(fp.read(count), row_size) for count in bytes_counts
            )
    except ValueError as e:
        logger.error(f"An error occurred during RLE decoding: {e}")
        logger.debug(
            f"Decompression of RLE data failed: {width=} {height=} {depth=} {version=} size={len(data)}",
            exc_info=True,
        )
        raise


def encode_prediction(data: bytes | bytearray, w: int, h: int, depth: int) -> bytes:
    """Encode data for ZIP with prediction.

    Bytes past ``w * h`` samples are appended unchanged.
    """
    if depth not in (8, 16, 32):
        raise ValueError("Invalid pixel size %d" % (depth))
    size = w * h * depth // 8
    if depth == 8:
        rows = np.frombuffer(data, np.uint8, count=size).reshape(h, w)
        encoded = _delta_encode(rows)
    elif depth == 16:
        rows = np.frombuffer(data, ">u2", count=w * h).reshape(h, w)
        encoded = _delta_encode(rows.astype(np.uint16)).astype(">u2")
    else:
        # Each row's 4-byte samples are split into four byte planes, and the
        # delta runs across the whole row of planes.
        samples = np.frombuffer(data, np.uint8, count=size).reshape(h, w, 4)
        planes = samples.transpose(0, 2, 1).reshape(h, 4 * w)
        encoded = _delta_encode(planes)
    return encoded.tobytes() + bytes(data[size:])


def decode_prediction(data: bytes, w: int, h: int, depth: int) -> bytes:
    """Decode ZIP-with-prediction data.

    Bytes past ``w * h`` samples are ignored; a short *data* raises ValueError.
    """
    if depth == 8:
        rows = np.frombuffer(data, np.uint8, count=w * h).reshape(h, w)
        return _delta_decode(rows).tobytes()
    elif depth == 16:
        rows = np.frombuffer(data, ">u2", count=w * h).reshape(h, w)
        return _delta_decode(rows.astype(np.uint16)).astype(">u2").tobytes()
    elif depth == 32:
        planes = np.frombuffer(data, np.uint8, count=4 * w * h).reshape(h, 4 * w)
        return _delta_decode(planes).reshape(h, 4, w).transpose(0, 2, 1).tobytes()
    else:
        raise ValueError("Invalid pixel size %d" % (depth))


def _delta_encode(rows: "np.ndarray") -> "np.ndarray":
    """Difference along each row, wrapping at the dtype width."""
    out = np.empty_like(rows)
    out[:, :1] = rows[:, :1]
    np.subtract(rows[:, 1:], rows[:, :-1], out=out[:, 1:])
    return out


def _delta_decode(rows: "np.ndarray") -> "np.ndarray":
    """Running sum along each row, wrapping at the dtype width."""
    return np.cumsum(rows, axis=1, dtype=rows.dtype)
