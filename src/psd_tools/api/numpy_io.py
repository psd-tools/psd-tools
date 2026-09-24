import logging
import warnings
from collections.abc import Collection
from typing import TYPE_CHECKING, Any, Callable, Literal, cast

import numpy as np

if TYPE_CHECKING:
    from psd_tools.api.protocols import LayerProtocol, PSDProtocol

from psd_tools.api.utils import (
    EXPECTED_CHANNELS,
    check_pixel_size,
    get_color_channels,
    get_transparency_index,
    has_transparency,
)

# The canonical padded row size, rather than a fourth copy of the arithmetic:
# the write path has to agree with the codec byte for byte or the section comes
# out a byte a row short of its declared length.
from psd_tools.compression import PSDDecompressionWarning, _row_size
from psd_tools.constants import ChannelID, ColorMode, Compression
from psd_tools.psd.patterns import Pattern

logger = logging.getLogger(__name__)


def get_array(
    layer: "LayerProtocol | PSDProtocol", channel: str | None, **kwargs: Any
) -> np.ndarray | None:
    # Import at runtime to avoid circular imports
    from psd_tools.api.layers import Layer  # noqa: PLC0415
    from psd_tools.api.psd_image import PSDImage  # noqa: PLC0415

    if isinstance(layer, PSDImage):
        return get_image_data(layer, channel)
    elif isinstance(layer, Layer):
        return get_layer_data(layer, channel, **kwargs)
    raise TypeError(
        f"Expected LayerProtocol or PSDProtocol, got {type(layer).__name__}"
    )


def _image_data_planes(psdimage: "PSDProtocol", flat: bool = False) -> int:
    """Planes :func:`get_image_data` will allocate, for its allocation guard.

    ``flat`` marks the paths that return a synthesised ``(h, w, 1)`` array
    without reading the image data -- a mask, or a shape on a document with no
    transparency. Those allocate one plane whatever the colour mode.

    Otherwise the header's channel count is what the merged image data stores,
    and for every colour mode but one it is what gets allocated. Indexed at
    depth 8 is the exception: :func:`_parse_array` applies the palette to the
    whole buffer, so the result is ``(h, w, 3 * channels)``. Only that branch
    applies it, so a malformed 16- or 32-bit indexed document keeps its stored
    width and must not be tripled.

    Deliberately *not* ``max(channels, get_color_channels(psdimage))``, the
    shape the compositor's guard uses. That one bounds a canvas built at the
    resolved width; this one bounds the stored array, whose width the header
    fixes. Taking the wider of the pair would reject a one-channel RGB document
    at four times its real size -- a false positive, not a safety margin.

    This bounds the array that is returned; the transient peak on top of it is
    :func:`_image_data_peak_bytes`'s subject, and is what the guard is given
    (#767). Keep the two separate: the plane count is a property of the format
    and the transients are a property of the code, and they go stale for
    different reasons.
    """
    if flat:
        return 1
    planes = psdimage.channels
    if psdimage.color_mode == ColorMode.INDEXED and psdimage.depth == 8:
        planes *= EXPECTED_CHANNELS[ColorMode.INDEXED]
    return planes


# What :func:`_parse_array` holds *on top of* the array it returns, in bytes per
# pixel per plane. Each entry is a count of the arrays alive at once in that
# depth's branch, not a safety factor:
#
#   depth 1   ``bits`` and ``1 - bits``, both uint8, while ``.astype`` builds the
#             float32 result from them.
#   depth 8   the ``.astype`` result, while ``/ 255.0`` builds the one returned.
#             The palette adds a third, ``lut[parsed]``, counted separately below
#             because it is uint8 rather than float32.
#   depth 16  the same pair, rescaling by 65535 instead.
#   depth 32  nothing. 32-bit data needs no rescale, so ``.astype`` alone
#             produces the array that is returned.
#
# ``np.frombuffer`` is a view and allocates nothing; so are the ``reshape``,
# ``transpose`` and ``ravel`` that follow.
_PARSE_TRANSIENT: dict[int, int] = {1: 2, 8: 4, 16: 4, 32: 0}

# The uint8 array the palette lookup materialises before it is widened, one byte
# per pixel per plane -- ``lut[parsed]`` is already three planes wide.
_PALETTE_TRANSIENT: int = 1

# :func:`_remove_background`'s own temporaries, in bytes per pixel: up to four
# float32 arrays of the three colour planes (4 x 3 x 4) and a boolean mask of the
# same shape (3 x 1), rounded up from 51. Flat rather than per-plane because it
# always works on exactly three colour planes however wide the document is.
#
# This is the one term that is not the same everywhere, and it is sized on the
# widest platform rather than on the one it was developed on. Measured at 39
# bytes a pixel on macOS/CPython 3.10 -- three arrays, each freed before the next
# was taken -- and at 48 on Linux and on Windows, at every Python from 3.10 to
# 3.14 and with or without the composite extra. A guard that holds only where
# its author ran it is not a guard, so 48 is what this covers.
#
# Measured with every alpha non-zero, which is the worst case for its
# boolean-indexed copies: a payload that leaves most of the alpha at zero selects
# few elements and hides most of this.
_BACKGROUND_TRANSIENT: int = 52

# Bytes live at the codec's own peak, as a multiple of the decompressed size.
# ``ImageData.get_data()`` runs after the guard, so this is inside what the guard
# has to bound. RAW hands back the bytes read at open time -- the same object,
# when the body is exactly the declared length -- while the other three build
# their result: RLE joins materialised rows, and prediction adds an
# ``array.array`` pass and a byte-order pass on top of the inflate. Measured
# 1.0x / 2.0x / 2.1x / 3.1x, each rounded up.
_DECOMPRESS_PEAK: dict[Compression, int] = {
    Compression.RAW: 1,
    Compression.RLE: 3,
    Compression.ZIP: 3,
    Compression.ZIP_WITH_PREDICTION: 4,
}


def _image_data_peak_bytes(psdimage: "PSDProtocol", flat: bool = False) -> int:
    """Bytes :func:`get_image_data` allocates at its high-water mark.

    :func:`_image_data_planes` sizes the array that comes back;
    :func:`~psd_tools.api.utils.check_pixel_size` is given this instead, because
    a budget that only bounds the result is one the peak walks straight through
    (#767).

    The three phases -- decompressing the channel buffer, parsing it into
    float32, removing the white background -- run one after another, so the
    widest of them bounds all three. Summing them instead would reject documents
    that never hold two phases at once. What *is* live across the last two is the
    decompressed buffer itself, so that is added to each rather than maxed with
    them.

    Measured with ``tracemalloc``, which sees numpy's allocations, over every
    colour mode, depth, channel count and compression method. The fit is exact
    on the platform it was developed on and an upper bound elsewhere: every term
    but :data:`_BACKGROUND_TRANSIENT` measures the same everywhere, and that one
    is sized on the widest platform, so a document admitted here is one whose
    peak fits on any of them. Two deliberate exclusions:

    - Per-object allocator overhead. This and ``tracemalloc`` both count
      requested bytes; what the allocator rounds each request up to is neither
      modelled nor modellable here.
    - The source buffer is counted even for RAW, where ``get_data()`` usually
      returns the very bytes object read at open time and allocates nothing.
      It only usually does: a body longer than the declared length is sliced,
      and this guard exists for files that are not well formed
      (GHSA-8q6g-vjhf-jp8m). The cost of counting it is a 2x over-estimate on a
      32-bit RAW document, where there is no parse transient to dwarf it.
    """
    pixels = psdimage.width * psdimage.height
    if flat:
        # `np.ones((h, w, 1))` and nothing else -- the image data is never read,
        # so there is no buffer to decompress and no transient above it.
        return pixels * 4

    planes = _image_data_planes(psdimage, flat)
    depth = psdimage.depth
    returned = pixels * planes * 4

    # Rounded up per row: a 1-bit row of `width` pixels occupies
    # `ceil(width / 8)` bytes, padding included.
    source = ((psdimage.width * depth + 7) // 8) * psdimage.height * psdimage.channels

    parse = _PARSE_TRANSIENT[depth]
    if psdimage.color_mode == ColorMode.INDEXED and depth == 8:
        parse += _PALETTE_TRANSIENT
    # `_remove_background()`'s own condition, spelled against the plane count it
    # actually tests: `data.shape[2] > 3` on an RGB document.
    background = (
        _BACKGROUND_TRANSIENT
        if psdimage.color_mode == ColorMode.RGB and planes > 3
        else 0
    )
    compression = psdimage._record.image_data.compression

    return max(
        _DECOMPRESS_PEAK[compression] * source,
        source + returned + pixels * planes * parse,
        source + returned + pixels * background,
    )


def get_image_data(psdimage: "PSDProtocol", channel: str | None) -> np.ndarray:
    # Decided before the guard runs rather than after, so the estimate can match
    # whichever branch is taken. The dimension checks inside check_pixel_size()
    # apply to both, so neither path escapes it.
    flat = (channel == "mask") or (
        channel == "shape" and not has_transparency(psdimage)
    )
    # The guard is here to reject a file before it allocates, so its estimate
    # must not fall below what follows -- which is more than the array returned,
    # this path holding two float32 arrays at once while it parses and several
    # more while it removes the background (#767). _image_data_peak_bytes() is
    # that bound; the plane count still rides along, naming the shape in the
    # error message. See _image_data_planes() for why the header's own count is
    # not the array's width for an indexed document -- and why the
    # wider-of-the-pair shape used in composite() is not either.
    check_pixel_size(
        psdimage.width,
        psdimage.height,
        _image_data_planes(psdimage, flat),
        max_alloc_bytes=psdimage._max_alloc_bytes,
        estimated_bytes=_image_data_peak_bytes(psdimage, flat),
    )

    if flat:
        return np.ones((psdimage.height, psdimage.width, 1), dtype=np.float32)

    lut = None
    if psdimage.color_mode == ColorMode.INDEXED:
        lut = np.frombuffer(psdimage._record.color_mode_data.value, np.uint8)
        lut = lut.reshape((3, -1)).transpose()
    image_bytes = psdimage._record.image_data.get_data(psdimage._record.header, False)
    if not isinstance(image_bytes, bytes):
        raise TypeError(f"Expected bytes, got {type(image_bytes).__name__}")
    array = _parse_array(
        image_bytes,
        cast(Literal[1, 8, 16, 32], psdimage.depth),
        psdimage.width,
        lut=lut,
    )
    if lut is not None:
        array = array.reshape((psdimage.height, psdimage.width, -1))
    else:
        array = array.reshape((-1, psdimage.height, psdimage.width)).transpose(
            (1, 2, 0)
        )
    array = _remove_background(array, psdimage)

    if channel == "shape":
        return np.expand_dims(array[:, :, get_transparency_index(psdimage)], 2)
    elif channel == "color":
        if psdimage.color_mode == ColorMode.MULTICHANNEL:
            return array
        # TODO: psd.color_mode == ColorMode.INDEXED --> Convert?
        return array[:, :, : EXPECTED_CHANNELS[psdimage.color_mode]]

    return array


def get_layer_data(
    layer: "LayerProtocol", channel: str | None, real_mask: bool = True
) -> np.ndarray | None:
    def _find_channel(
        layer: "LayerProtocol",
        width: int,
        height: int,
        condition: Callable[[Any], bool],
    ) -> np.ndarray | None:
        depth, version = layer._psd.depth, layer._psd.version
        iterator = zip(layer._record.channel_info, layer._channels)
        channels = [
            _parse_array(
                data.get_data(width, height, depth, version),
                cast(Literal[1, 8, 16, 32], depth),
                width,
            )
            for info, data in iterator
            if condition(info) and len(data.data) > 0
        ]
        if len(channels) and channels[0].size > 0:
            result = np.stack(channels, axis=1).reshape((height, width, -1))
            expected_channels = EXPECTED_CHANNELS.get(layer._psd.color_mode)
            if expected_channels is not None and result.shape[2] > expected_channels:
                logger.debug("Extra channel found")
                return result[:, :, :expected_channels]
            return result
        return None

    if channel == "color":
        return _find_channel(layer, layer.width, layer.height, lambda x: x.id >= 0)
    elif channel == "shape":
        return _find_channel(
            layer,
            layer.width,
            layer.height,
            lambda x: x.id == ChannelID.TRANSPARENCY_MASK,
        )
    elif channel == "mask":
        if layer.mask is None:
            return None
        if layer.mask.has_real() and real_mask:
            channel_id = ChannelID.REAL_USER_LAYER_MASK
        else:
            channel_id = ChannelID.USER_LAYER_MASK
        return _find_channel(
            layer, layer.mask.width, layer.mask.height, lambda x: x.id == channel_id
        )

    color = _find_channel(layer, layer.width, layer.height, lambda x: x.id >= 0)
    shape = _find_channel(
        layer, layer.width, layer.height, lambda x: x.id == ChannelID.TRANSPARENCY_MASK
    )
    if shape is None:
        return color
    return np.concatenate([color, shape], axis=2)


def get_pattern(pattern: Pattern) -> np.ndarray:
    """Get pattern array."""
    top, left, bottom, right = pattern.data.rectangle
    height, width = bottom - top, right - left
    return np.stack(
        [
            # The channel's own rectangle, which is what
            # `VirtualMemoryArray.get_data()` decompressed against; the
            # pattern's is only incidentally the same one.
            _parse_array(
                c.get_data(),  # type: ignore[arg-type]
                c.pixel_depth,  # type: ignore[arg-type]
                (c.rectangle[3] - c.rectangle[1]) if c.rectangle else width,
            )
            for c in pattern.data.channels
            if c.is_written
        ],
        axis=1,
    ).reshape((height, width, -1))


def get_pattern_color_channels(pattern: Pattern) -> int:
    """Number of leading planes in :py:func:`get_pattern`'s array that are color.

    A pattern's channel list is a fixed set of slots rather than a list of the
    channels it uses: ``len(channels) - 2`` color slots -- 24 as Photoshop
    writes them, whatever the pattern's mode -- and then two more, the last of
    which holds transparency. So the count is the number of written slots in
    the color region, contiguous or not; :py:func:`get_pattern` skips the
    unwritten ones and stacks the rest in slot order, which puts those planes
    at the front of its array and any alpha at the back.

    Reading the boundary off the slot layout is what makes it answerable at
    all. :py:data:`~psd_tools.api.utils.EXPECTED_CHANNELS` keyed on the
    pattern's color mode states the width a *document* in that mode carries,
    which is only incidentally the width this pattern stored (#741).

    The rule rests on how Photoshop's shipped presets are laid out -- alpha in
    a trailing slot, never a color one. A pattern written the other way would
    be read as all color; nothing in the corpus or in those presets is, and for
    multichannel there is no constant to fall back on regardless.
    """
    channels = pattern.data.channels
    color_slots = max(len(channels) - 2, 0)
    count = sum(1 for c in channels[:color_slots] if c.is_written)
    # A file that writes nothing into the color slots says nothing about where
    # its boundary is, so take every written plane as color and split nothing:
    # a pattern rendered without its alpha beats one that cannot be read.
    return count or sum(1 for c in channels if c.is_written)


def _parse_array(
    data: bytes | bytearray,
    depth: Literal[1, 8, 16, 32],
    width: int,
    lut: np.ndarray | None = None,
) -> np.ndarray:
    """Flatten a channel buffer into ``float32`` values in ``[0, 1]``.

    *width* is used only at depth 1, and only there is it needed: every other
    depth stores a whole number of bytes per pixel, so the buffer is a value
    sequence and the caller's own ``reshape`` supplies the geometry. A 1-bit
    row is padded to a byte boundary instead, so the row has to be found here
    -- ``np.unpackbits`` alone yields ``8 * ceil(width / 8)`` values per row,
    which either does not divide by ``width`` or divides into the wrong shape
    (#768).
    """
    if depth == 8:
        parsed = np.frombuffer(data, ">u1")
        if lut is not None:
            parsed = lut[parsed]
        return parsed.astype(np.float32) / 255.0
    elif depth == 16:
        return np.frombuffer(data, ">u2").astype(np.float32) / 65535.0
    elif depth == 32:
        # The conversion the other three branches get for free from their own
        # rescaling, spelled out here because 32-bit data needs no rescaling.
        # Without it this branch alone returned an array that was neither
        # writeable -- `np.frombuffer` over immutable `bytes` is read-only, and
        # `_remove_background()` writes in place, so a 32-bit RGB document with
        # transparency raised `assignment destination is read-only` -- nor
        # `np.float32`, since it kept the file's big-endian byte order where
        # every other depth returns the native dtype (#738).
        return np.frombuffer(data, ">f4").astype(np.float32)
    elif depth == 1:
        # Clamped so a zero width divides: `decompress()` rejects one before it
        # can reach here, but this takes its width from the caller and a
        # ZeroDivisionError is a poor way to say so. `count=0` then trims every
        # row to nothing, which is the right answer for a channel of no pixels.
        row_size = max((width + 7) // 8, 1)
        packed = np.frombuffer(data, np.uint8)
        # Whole rows only. A body that ends mid-row is one the geometry cannot
        # be recovered from, and dropping the remainder degrades the read
        # rather than making the reshape below unsatisfiable.
        packed = packed[: row_size * (packed.size // row_size)]
        bits = np.unpackbits(packed.reshape(-1, row_size), axis=1, count=width)
        # A set bit is *black*: Photoshop writes a bitmap-mode document with the
        # inked pixels set, which is why `pil_io._create_image()` reads it
        # through the inverted raw mode "1;I". This branch returned the bit as
        # it stood, so every 1-bit document composited as its own negative.
        return (1 - bits).astype(np.float32).ravel()
    else:
        raise ValueError("Unsupported depth: %g" % depth)


def _remove_background(data: np.ndarray, psdimage: "PSDProtocol") -> np.ndarray:
    """ImageData preview is rendered on a white background."""
    if psdimage.color_mode == ColorMode.RGB and data.shape[2] > 3:
        color = data[:, :, :3]
        alpha = data[:, :, 3:4]
        a = np.repeat(alpha, color.shape[2], axis=2)
        color[a > 0] = (color + alpha - 1)[a > 0] / a[a > 0]
        data[:, :, :3] = color
    return data


def _fit(array: np.ndarray, height: int, width: int, fill: float) -> np.ndarray:
    """Crop or pad *array* to the header's geometry.

    The compositor's viewport is the document's viewbox, so nothing in the
    corpus arrives at another size. It is here so that the section
    :func:`encode_image_data` produces is the declared length *structurally*
    rather than incidentally -- a preview one row short is the defect this
    whole path exists to stop writing (#866).
    """
    if array.shape[0] == height and array.shape[1] == width:
        return array
    logger.debug(
        "Composited %s where the header declares (%d, %d); fitting.",
        array.shape[:2],
        height,
        width,
    )
    fitted = np.full((height, width, array.shape[2]), fill, dtype=np.float32)
    rows, columns = min(height, array.shape[0]), min(width, array.shape[1])
    fitted[:rows, :columns] = array[:rows, :columns]
    return fitted


def _encode_array(plane: np.ndarray, depth: Literal[1, 8, 16, 32], width: int) -> bytes:
    """Pack one ``float32`` plane into the bytes the file stores.

    The inverse of :func:`_parse_array`, and it has to stay one: whatever the
    reader does to a stored value on the way in, this undoes on the way out.
    *width* is used at depth 1 alone, for the same reason it is needed there --
    a 1-bit row is padded to a byte boundary, so the row has to be found before
    the bits can be packed.

    The three integer depths clip before they cast, for the reason
    :func:`~psd_tools.composite.composite.composite_pil` clips its own array:
    numpy *wraps* an out-of-range float, so a component at 1.2 would be stored
    as a dark colour rather than a saturated one. Depth 32 does not, because
    its cast is a float-to-float one that cannot wrap, and because a 32-bit
    channel is the one place the format has room above 1.0 --
    ``colormodes/4x4_32bit_rgb.psd`` stores 1.0000098. Neither form catches a
    NaN, which numpy passes through every one of these.
    """
    clipped = np.clip(plane, 0.0, 1.0)
    if depth == 8:
        return np.rint(clipped * 255.0).astype(">u1").tobytes()
    elif depth == 16:
        return np.rint(clipped * 65535.0).astype(">u2").tobytes()
    elif depth == 32:
        # No rescale, matching the read: 32-bit channels are stored as floats
        # in [0, 1]. Every 32-bit fixture in the corpus is.
        return plane.astype(">f4").tobytes()
    elif depth == 1:
        if width <= 0:
            return b""
        # A *set* bit is black, the inverse of the value's sense. `packbits`
        # zeroes each row's trailing pad bits; Photoshop does not always, and
        # it makes no difference -- the readers trim the row to `width` -- so
        # the padding is not something a byte-for-byte test can pin down.
        bits = 1 - np.rint(clipped).astype(np.uint8)
        return np.packbits(bits.reshape(-1, width), axis=1).tobytes()
    raise ValueError("Unsupported depth: %g" % depth)


def _stored_planes(
    psdimage: "PSDProtocol", wanted: Collection[int]
) -> dict[int, bytes]:
    """The document's current merged planes, for the channels nothing rebuilds.

    A spot channel, or an alpha channel that is not the composite's
    transparency, is not the compositor's output: there is nothing to
    regenerate it from, so a save preserves what is already there.

    Only *wanted* is kept. ``get_data()`` decompresses the whole section --
    one decode covers every channel and there is no way to ask it for fewer
    -- but holding the colour planes past it would retain 67 MB on
    ``cmyk-alpha-spot.psd`` that nothing goes on to read.

    Nothing is carried from a preview that could not be read. That takes two
    checks, because the codec has two ways of failing: it raises on a length
    it cannot reconcile, and it *succeeds* with black where a channel fails to
    decode, which a length check cannot see. So the read is done with the
    decompression warning promoted to an error -- a save that regenerates the
    preview is the wrong place to launder a decode failure into a file, and
    the wrong place to raise one either.

    ``catch_warnings()`` is process-global and not thread-safe: for the length
    of the read, another thread's decode warning is an error too. The scope is
    a few statements and the alternative is carrying black, so it is the
    lesser of the two.
    """
    if not wanted:
        return {}
    header = psdimage._record.header
    plane_length = _row_size(header.width, header.depth) * header.height
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", PSDDecompressionWarning)
            planes = psdimage._record.image_data.get_data(header)
    except (PSDDecompressionWarning, ValueError, TypeError, OSError) as e:
        # Narrow on purpose. A blanket `except` would turn any unrelated
        # warning into a silently dropped channel wherever the caller runs
        # under `-W error` -- writing zeros over a spot channel and saying
        # nothing, which is the one failure this function must not have.
        logger.debug("Cannot carry the stored preview forward: %s", e)
        return {}
    if not isinstance(planes, list):
        return {}
    return {
        index: planes[index]
        for index in wanted
        if index < len(planes) and len(planes[index]) == plane_length
    }


# An indexed document's color table: 256 entries over three planes.
_COLOR_TABLE_SIZE: int = 768


def _to_indices(color: np.ndarray, psdimage: "PSDProtocol") -> np.ndarray | None:
    """Map an indexed document's color planes back onto its own color table.

    :func:`_parse_array` expands a stored index through the table, so the
    inverse has to collapse a colour back to an index -- and against *this*
    document's table. ``PIL.Image.convert("P")``, which the preview used to go
    through, quantizes to PIL's own web palette instead, which is why an
    indexed document came back in unrelated colours rather than merely
    requantized.

    ``None`` where the document has no full table to quantize against.
    ``ColorModeData.interleave()`` reads 256 entries out of three planes
    unguarded, so a short one is an ``IndexError`` rather than a poor
    palette -- and a save that aborts is worse than one that leaves the
    stored plane alone, which is what the caller does with ``None``.
    """
    from PIL import Image  # noqa: PLC0415

    table = psdimage._record.color_mode_data.value
    if len(table) < _COLOR_TABLE_SIZE:
        logger.warning(
            "Indexed document has a %d-byte color table, not %d; keeping the "
            "stored index plane rather than quantizing against a partial one.",
            len(table),
            _COLOR_TABLE_SIZE,
        )
        return None
    palette = Image.new("P", (1, 1))
    palette.putpalette(psdimage._record.color_mode_data.interleave())
    rgb = np.rint(np.clip(color[:, :, :3], 0.0, 1.0) * 255.0).astype(np.uint8)
    indexed = Image.fromarray(rgb, "RGB").quantize(
        palette=palette, dither=Image.Dither.NONE
    )
    return np.asarray(indexed, dtype=np.float32)[:, :, np.newaxis] / 255.0


def encode_image_data(
    psdimage: "PSDProtocol", color: np.ndarray, alpha: np.ndarray
) -> list[bytes]:
    """Turn a composited document into the merged image data section's planes.

    The inverse of :func:`get_image_data`, and the reason it is spelled as one:
    :py:meth:`~psd_tools.api.psd_image.PSDImage.save` used to regenerate the
    preview by rendering it to a PIL image and splitting that, which described
    PIL rather than the document. ``PIL.Image.tobytes()`` is one byte per
    channel whatever the header's depth says, PIL's mode holds no spot channel
    and no second alpha, and the conventions it stores a value in are its own
    -- so a 16-bit document got a section half its declared length, a
    multichannel one lost every plane but the first, a bitmap one came back
    inverted, and a profiled one was converted to sRGB and back (#866).

    *color* and *alpha* are :py:func:`psd_tools.composite.composite`'s arrays,
    in the document's own color space; the planes returned are in the file's,
    in header channel order, each :func:`_encode_array`-packed at the header's
    depth. Feed them to
    :py:meth:`~psd_tools.psd.image_data.ImageData.set_data`.

    :param psdimage: the document the planes are being written for.
    :param color: ``(height, width, color_channels)`` in [0, 1].
    :param alpha: ``(height, width, 1)`` in [0, 1].
    :return: one ``bytes`` per channel the header declares.
    """
    header = psdimage._record.header
    depth = cast(Literal[1, 8, 16, 32], header.depth)
    height, width, channels = header.height, header.width, header.channels

    color = _fit(color, height, width, 1.0)
    alpha = _fit(alpha, height, width, 0.0)
    color_planes = get_color_channels(psdimage)
    if color.shape[2] != color_planes:
        logger.debug(
            "Composited %d color planes where the document carries %d; fitting.",
            color.shape[2],
            color_planes,
        )
        widened = np.ones((height, width, color_planes), dtype=np.float32)
        kept = min(color_planes, color.shape[2])
        widened[:, :, :kept] = color[:, :, :kept]
        color = widened
    # Indexed at depth 16 or 32 is left alone, mirroring the reader: only its
    # depth-8 branch applies the palette, so only that one has an inverse.
    if psdimage.color_mode == ColorMode.INDEXED and depth == 8:
        collapsed = _to_indices(color, psdimage)
        if collapsed is None:
            return _stored_or_empty(psdimage, range(channels))
        color = collapsed

    # Channel order is the header's: the color planes first, then the
    # transparency channel wherever the document keeps it.
    arrays: dict[int, np.ndarray] = {
        index: color[:, :, index] for index in range(min(color.shape[2], channels))
    }
    transparency = _transparency_slot(psdimage, color_planes)
    if transparency >= 0:
        arrays[transparency] = alpha[:, :, 0]

    carried = _stored_planes(psdimage, [i for i in range(channels) if i not in arrays])
    _restore_background(arrays, psdimage, transparency)

    empty = None
    planes: list[bytes] = []
    for index in range(channels):
        if index in arrays:
            planes.append(_encode_array(arrays[index], depth, width))
        elif index in carried:
            planes.append(carried[index])
        else:
            # Built once, and only if a channel actually needs it: on a large
            # document this is a whole plane of zeros nobody may want.
            if empty is None:
                empty = b"\x00" * (_row_size(width, depth) * height)
            planes.append(empty)
    return planes


def _stored_or_empty(psdimage: "PSDProtocol", indices: Collection[int]) -> list[bytes]:
    """Every plane carried over, or zero-filled where it cannot be.

    The whole-section fallback, for when the composite cannot be expressed in
    the document's channels at all. Leaving the stored preview as it stands
    beats aborting the save or writing a section in the wrong encoding.
    """
    header = psdimage._record.header
    carried = _stored_planes(psdimage, indices)
    empty = b"\x00" * (_row_size(header.width, header.depth) * header.height)
    return [carried.get(index, empty) for index in indices]


def _transparency_slot(psdimage: "PSDProtocol", color_planes: int) -> int:
    """Which stored channel the composite's alpha belongs in, or -1 for none.

    :func:`~psd_tools.api.utils.get_transparency_index` where it can name one.
    Where it cannot -- a document with no ``ALPHA_IDENTIFIERS`` resource --
    the channel past the color planes is the answer only if it is the *single*
    extra channel the document has: that is the one
    :func:`~psd_tools.api.utils.has_transparency` was looking at when it said
    the document has transparency at all, and with nothing else beside it
    there is nothing else it could be. Declining to write it there left a
    document whose stored alpha was stale, which for one built by
    :py:meth:`~psd_tools.api.psd_image.PSDImage.frompil` from a transparent
    image means saving it back as fully transparent.

    Two or more extra channels and no identifiers to tell them apart --
    ``cmyk-spot.psd``, three of them -- names no slot at all. The alpha is
    dropped and every spot channel is carried over intact, which is the
    reading that cannot destroy data: the alternative overwrites one of three
    channels chosen by position alone.
    """
    if not has_transparency(psdimage):
        return -1
    index = get_transparency_index(psdimage)
    if 0 <= index < psdimage.channels:
        return index
    return color_planes if psdimage.channels == color_planes + 1 else -1


def _restore_background(
    arrays: dict[int, np.ndarray], psdimage: "PSDProtocol", transparency: int
) -> None:
    """Composite the color planes back onto the white the preview is stored on.

    Photoshop stores the merged preview already composited over white -- a
    fully transparent pixel reads back white in every Photoshop-authored
    fixture that has one -- and both readers undo it on the way in. Writing
    the unpremultiplied colour instead, which is what going through a PIL
    ``RGBA`` image did, left the reader to divide by an alpha the values had
    never been multiplied by.

    Matted against the *transparency* plane, and only where the document has
    one. ``_remove_background()`` reads plane 3 by position instead, whatever
    the alpha identifiers say, and matching that was wrong in both
    directions: an RGB document whose fourth channel is a spot channel got
    its colour matted against ink coverage -- a layer at ``(51, 102, 153)``
    over a spot plane of 128 was stored as ``(153, 178, 204)`` -- and one
    whose transparency sits past plane 3 was matted against the wrong
    channel. The reader's positional assumption is a defect of its own
    (#868); reproducing it here would have written it into files.

    Grayscale is left as composited, because that is what the readers expect:
    neither ``_remove_background()`` nor ``pil_io._remove_white_background()``
    touches an ``LA`` document, although Photoshop stores one over white like
    any other (``gray0.psd`` is white at all 123,854 of its transparent
    pixels). That asymmetry is #868 as well.

    Where the alpha is zero the read leaves the stored value alone, so the
    inverse there is the colour itself rather than the white this would
    otherwise put down. The two agree in practice -- the compositor returns
    white at a fully transparent pixel, its backdrop -- but only the explicit
    form is actually the inverse.
    """
    if psdimage.color_mode != ColorMode.RGB or transparency < 0:
        return
    alpha = arrays.get(transparency)
    if alpha is None:
        return
    opaque = alpha > 0
    for index in range(min(3, psdimage.channels)):
        if index in arrays and index != transparency:
            plane = arrays[index]
            arrays[index] = np.where(opaque, plane * alpha + (1.0 - alpha), plane)
