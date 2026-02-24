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
from typing import Iterator, Union

from PIL import Image

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

    The affected channel is replaced with black pixels.  Catch or filter this
    warning to detect silently degraded images::

        import warnings
        from psd_tools.compression import PSDDecompressionWarning

        with warnings.catch_warnings():
            warnings.simplefilter("error", PSDDecompressionWarning)
            psd = PSDImage.open("file.psd")
    """


_VALID_DEPTHS: frozenset[int] = frozenset((1, 8, 16, 32))
_MAX_DIMENSION: int = 300_000  # PSD/PSB hard limit per the Adobe spec


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
        % (codec, type(exc).__name__, exc, width, height, depth, version)
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
    out = d.decompress(data, max_length + 1)
    if d.unconsumed_tail:
        raise ValueError(
            "Decompressed size exceeds expected maximum of %d bytes" % max_length
        )
    out += d.flush()
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

    length = width * height * max(1, depth // 8)

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
            mode = "L" if depth == 8 else "RGB" if depth == 24 else "RGBA"
            result = Image.new(mode, (width, height), color=0).tobytes()
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
        row_size = max(width * depth // 8, 1)
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


def encode_prediction(
    data: Union[bytes, bytearray], w: int, h: int, depth: int
) -> bytes:
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
