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
import warnings
import zlib
from typing import Iterator

from psd_tools.constants import Compression
from psd_tools.psd.bin_utils import (
    be_array_from_bytes,
    be_array_to_bytes,
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

    From depth 8 up the affected channel is replaced with black pixels. Below
    it there is no substitute -- the fill is gated on ``depth >= 8``, a 1-bit
    channel having no byte-per-pixel form to fill -- so the warning is followed
    by a ``RuntimeError`` rather than a degraded read. Catch or filter this
    warning to detect silently degraded images::

        import warnings
        from psd_tools.compression import PSDDecompressionWarning

        with warnings.catch_warnings():
            warnings.simplefilter("error", PSDDecompressionWarning)
            psd = PSDImage.open("file.psd")
    """


_VALID_DEPTHS: frozenset[int] = frozenset((1, 8, 16, 32))
_MAX_DIMENSION: int = 300_000  # PSD/PSB hard limit per the Adobe spec

# Reject the black-fill fallback when a failed decode dwarfs its input (CWE-789).
# Set MAX_DEGRADED_BYTES to None to disable the guard (also disables the ratio check).
MAX_DEGRADED_BYTES: int | None = 16 * 1024 * 1024
MAX_DEGRADED_RATIO: int = 1000


def _channel_length(width: int, height: int, depth: int) -> int:
    """Bytes a channel of these dimensions occupies once decompressed.

    Shared by :func:`decompress`, which sizes every codec's output by it, and by
    :func:`decompressed_size_bound`, which has to predict that output without
    producing it. Note what it is *not*: at depth 1 it is one byte per pixel,
    eight times the packed size a row of ``width`` pixels really occupies, which
    is why the bound cannot be stated in pixels alone (#737).
    """
    return width * height * max(1, depth // 8)


def _rle_row_size(width: int, depth: int) -> int:
    """Bytes per row as :func:`decode_rle` reads and writes them.

    Floor division, and never zero: at depth 1 a row of fewer than eight pixels
    still occupies a byte. Shared with :func:`decompressed_size_bound` so the
    two cannot drift apart -- a bound on this codec has to track what the
    decoder reads, which is not quite what :func:`encode_rle` writes: that
    keeps its own expression, with the same floor but no clamp.
    """
    return max(width * depth // 8, 1)


def _warn_decompress_failure(
    codec: str,
    exc: Exception,
    width: int,
    height: int,
    depth: int,
    version: int,
) -> None:
    """Log and emit a PSDDecompressionWarning for a failed channel decode.

    The message states what actually follows, which depends on the depth: the
    black fill exists only from depth 8 up, and below it :func:`decompress`
    raises rather than substituting anything, so promising a degraded read
    there would describe a document the caller never receives.
    """
    outcome = (
        "channel replaced with black"
        if depth >= 8
        else "read abandoned; no black fill exists below depth 8"
    )
    msg = "%s decode failed (%s: %s); %s. width=%d height=%d depth=%d version=%d" % (
        codec,
        type(exc).__name__,
        exc,
        outcome,
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
    # documents. At depth 8 and up `decompress()` caught it as a length
    # mismatch; at depth 1 that check is skipped and the byte became eight more
    # float32 values than any estimate allowed for (#737).
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
    while not d.unconsumed_tail and len(out) <= max_length:
        chunk = d.decompress(b"", max_length + 1 - len(out))
        if not chunk:
            break
        out += chunk
    if d.unconsumed_tail or len(out) > max_length:
        raise ValueError(
            "Decompressed size exceeds expected maximum of %d bytes" % max_length
        )
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
) -> bytes:
    """Decompress raw data.

    :param data: compressed data bytes.
    :param compression: compression type,
            see :py:class:`~psd_tools.constants.Compression`.
    :param width: width in pixels; must be in [1, 300000].
    :param height: height in pixels; must be in [1, 300000].
    :param depth: bit depth of the pixel; must be one of 1, 8, 16, 32.
    :param version: psd file version.
    :return: decompressed data bytes.
    :raises ValueError: if *width*, *height*, or *depth* are out of range.
    """
    if width < 1 or width > _MAX_DIMENSION:
        raise ValueError("width %d out of range [1, %d]" % (width, _MAX_DIMENSION))
    if height < 1 or height > _MAX_DIMENSION:
        raise ValueError("height %d out of range [1, %d]" % (height, _MAX_DIMENSION))
    if depth not in _VALID_DEPTHS:
        raise ValueError("depth %d not in %s" % (depth, sorted(_VALID_DEPTHS)))

    length = _channel_length(width, height, depth)

    result: bytes | None = None
    if compression == Compression.RAW:
        result = data[:length]
    elif compression == Compression.RLE:
        try:
            result = decode_rle(data, width, height, depth, version)
        except (ValueError, IndexError) as e:
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

    if depth >= 8:
        if result is None:
            if (
                MAX_DEGRADED_BYTES is not None
                and length > MAX_DEGRADED_BYTES
                and length > len(data) * MAX_DEGRADED_RATIO
            ):
                raise ValueError(
                    "Refusing to allocate %d bytes for a channel that failed to "
                    "decode from %d input bytes (width=%d height=%d); set "
                    "psd_tools.compression.MAX_DEGRADED_BYTES = None to allow it."
                    % (length, len(data), width, height)
                )
            # Exactly `length`, which the mismatch check below demands of a
            # successful decode and this substitute has to honour too. It was
            # built as a PIL image whose mode was picked from the depth -- "L"
            # for 8, "RGBA" otherwise -- so depth 16 came back at four bytes per
            # pixel against a `length` of two, and every reader downstream saw a
            # channel twice its declared width (#737).
            result = bytes(length)
            logger.warning("Failed channel has been replaced by black")
        else:
            if len(result) != length:
                raise ValueError(
                    "Decompressed length mismatch: got %d, expected %d"
                    % (len(result), length)
                )

    if result is None:
        raise RuntimeError("decompress() produced no result for depth=%d" % depth)
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

    Answerable without decompressing anything, which is what makes it usable
    as an allocation guard's estimate:
    :py:func:`psd_tools.api.utils.check_pixel_size` has to reject a document
    *before* the buffer exists. It is reached today through
    :py:meth:`psd_tools.psd.image_data.ImageData.decompressed_size_bound`, from
    the depth-1 arm of ``psd_tools.api.numpy_io._image_data_planes()``, where
    the byte count and the pixel count part company -- ``np.unpackbits`` yields
    one value per *bit* -- and the pixel count alone under-counted the array
    eightfold (#737).

    ``length`` below is :py:func:`decompress`'s own ``width * height *
    max(1, depth // 8)``; the two are meant to be read together. For a
    well-formed body the bound is exact for RAW and RLE, and an over-estimate
    for the two ZIP codecs, whose inflated size cannot be known without
    inflating the stream. A malformed body only ever comes back smaller -- a
    truncated RLE byte-count table yields fewer rows than ``height`` -- which is
    the safe direction for a guard:

    - RAW returns ``data[:length]``, so the body's own length caps it. At depth
      8 and up a body shorter than ``length`` raises the mismatch check instead
      of returning, so the ``min`` only bites at depth 1, where that check is
      skipped.
    - RLE returns exactly ``height`` rows of ``max(width * depth // 8, 1)``
      bytes, each row padded or clipped to that size by ``decode()`` rather
      than raising. At depth 1 that is *below* ``length``: a row of ``width``
      pixels packs into ``width // 8`` bytes, not ``width``.
    - Both ZIP codecs are capped at ``length`` by ``_safe_zlib_decompress()``,
      and so is the black fill substituted for a channel that fails to decode.

    :param data: the compressed body; read for its length only.
    :param compression: compression type, see :py:class:`.Compression`.
    :param width: width in pixels.
    :param height: height in pixels. Pass ``height * channels`` wherever the
        caller decompresses every channel in one call, as
        :py:meth:`psd_tools.psd.image_data.ImageData.get_data` does.
    :param depth: bit depth of the pixel; one of 1, 8, 16, 32.
    :param version: psd file version. Accepted for symmetry with
        :py:func:`decompress`; the bound does not depend on it, the row
        byte-count table being read past rather than returned.
    :return: the largest number of bytes ``decompress()`` can return for these
        arguments.
    """
    length = _channel_length(width, height, depth)
    if compression == Compression.RAW:
        return min(len(data), length)
    if compression == Compression.RLE:
        return height * _rle_row_size(width, depth)
    return length


def encode_rle(data: bytes, width: int, height: int, depth: int, version: int) -> bytes:
    row_size = width * depth // 8
    with io.BytesIO(data) as fp:
        rows = [rle_impl.encode(fp.read(row_size)) for _ in range(height)]
    bytes_counts = array.array(("H", "I")[version - 1], map(len, rows))
    encoded = b"".join(rows)

    with io.BytesIO() as fp:
        write_be_array(fp, bytes_counts)
        fp.write(encoded)
        result = fp.getvalue()

    return result


def decode_rle(data: bytes, width: int, height: int, depth: int, version: int) -> bytes:
    try:
        row_size = _rle_row_size(width, depth)
        with io.BytesIO(data) as fp:
            bytes_counts = read_be_array(("H", "I")[version - 1], height, fp)
            return b"".join(
                rle_impl.decode(fp.read(count), row_size) for count in bytes_counts
            )
    except ValueError as e:
        logger.error(f"An error occurred during RLE decoding: {e}")
        logger.info(
            f"Decompression of RLE data failed: {width=} {height=} {depth=} {version=} size={len(data)}",
            exc_info=True,
        )
        raise


def encode_prediction(data: bytes | bytearray, w: int, h: int, depth: int) -> bytes:
    if depth == 8:
        arr = array.array("B", data)
        arr = _delta_encode(arr, 0x100, w, h)
        return be_array_to_bytes(arr)
    elif depth == 16:
        arr = array.array("H", data)
        arr = _delta_encode(arr, 0x10000, w, h)
        return be_array_to_bytes(arr)
    elif depth == 32:
        arr = array.array("B", data)
        arr = _shuffle_byte_order(arr, w, h)
        arr = _delta_encode(arr, 0x100, w * 4, h)
        return arr.tobytes()
    else:
        raise ValueError("Invalid pixel size %d" % (depth))


def decode_prediction(data: bytes, w: int, h: int, depth: int) -> bytes:
    if depth == 8:
        arr = be_array_from_bytes("B", data)
        arr = _delta_decode(arr, 0x100, w, h)
    elif depth == 16:
        arr = be_array_from_bytes("H", data)
        arr = _delta_decode(arr, 0x10000, w, h)
    elif depth == 32:
        arr = array.array("B", data)
        arr = _delta_decode(arr, 0x100, w * 4, h)
        arr = _restore_byte_order(arr, w, h)
    else:
        raise ValueError("Invalid pixel size %d" % (depth))

    return arr.tobytes()


def _delta_encode(arr: array.array, mod: int, w: int, h: int) -> array.array:
    arr.byteswap()
    for y in reversed(range(h)):
        offset = y * w
        for x in reversed(range(w - 1)):
            pos = offset + x
            next_value = (arr[pos + 1] - arr[pos]) % mod
            arr[pos + 1] = next_value
    return arr


def _delta_decode(arr: array.array, mod: int, w: int, h: int) -> array.array:
    for y in range(h):
        offset = y * w
        for x in range(w - 1):
            pos = offset + x
            next_value = (arr[pos + 1] + arr[pos]) % mod
            arr[pos + 1] = next_value
    arr.byteswap()
    return arr


def _shuffled_order(w: int, h: int) -> Iterator[int]:
    """
    Generator for the order of 4-byte values.

    32bit channels are also encoded using delta encoding,
    but it make no sense to apply delta compression to bytes.
    It is possible to apply delta compression to 2-byte or 4-byte
    words, but it seems it is not the best way either.
    In PSD, each 4-byte item is split into 4 bytes and these
    bytes are packed together: "123412341234" becomes "111222333444";
    delta compression is applied to the packed data.

    So we have to (a) decompress data from the delta compression
    and (b) recombine data back to 4-byte values.
    """
    rowsize = 4 * w
    for row in range(0, rowsize * h, rowsize):
        for offset in range(row, row + w):
            for x in range(offset, offset + rowsize, w):
                yield x


def _shuffle_byte_order(bytes_array: array.array, w: int, h: int) -> array.array:
    arr = bytes_array[:]
    for src, dst in enumerate(_shuffled_order(w, h)):
        arr[dst] = bytes_array[src]
    return arr


def _restore_byte_order(bytes_array: array.array, w: int, h: int) -> array.array:
    arr = bytes_array[:]
    for dst, src in enumerate(_shuffled_order(w, h)):
        arr[dst] = bytes_array[src]
    return arr
