import logging
from typing import TYPE_CHECKING, Any, Callable, Literal, cast

import numpy as np

if TYPE_CHECKING:
    from psd_tools.api.protocols import LayerProtocol, PSDProtocol

from psd_tools.api.utils import (
    EXPECTED_CHANNELS,
    check_pixel_size,
    get_transparency_index,
    has_transparency,
)
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
