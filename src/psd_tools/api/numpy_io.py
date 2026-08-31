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
from psd_tools.constants import ChannelID, ColorMode
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
    without reading the image data at all -- a mask, or a shape on a document
    with no transparency. Those allocate one plane whatever the colour mode, so
    estimating them at the stored width rejects requests that comfortably fit:
    ``numpy("mask")`` on a CMYK document allocates a quarter of what the header
    implies. That over-estimate predates the palette fix below for every
    multi-channel mode; it is corrected here rather than left to grow a third
    case.

    Otherwise the header's channel count is what the merged image data *stores*,
    and for every colour mode but one it is also what gets allocated. Indexed at
    depth 8
    is the exception: :func:`_parse_array` applies the palette to the whole
    buffer rather than to one plane, so ``(channels * h * w,)`` becomes
    ``(channels * h * w, 3)`` and the reshape below yields
    ``(h, w, 3 * channels)``. The header alone under-counted that threefold.

    Deliberately *not* ``max(channels, get_color_channels(psdimage))``, the
    shape #728 gave the compositor's guard. That one bounds a canvas built at
    the resolved width, so the wider of the pair is right there. This one bounds
    the stored array, whose width the header fixes -- and taking the wider of
    the pair here would over-estimate any file whose header declares fewer
    channels than its mode implies. Those parse fine and produce a narrow array:
    a one-channel RGB document returns ``(h, w, 1)`` and would have been
    rejected at four times its real size, which for a guard whose whole job is
    admitting sound files is a false positive rather than a safety margin.

    The palette is applied only in :func:`_parse_array`'s depth-8 branch, so a
    16- or 32-bit indexed document -- malformed, indexed being an 8-bit mode --
    keeps its stored width and must not be tripled either.

    Depth 1 is the case the pixel count cannot express at all, and it is
    settled first because it settles the width on its own. :func:`_parse_array`
    unpacks such a buffer with ``np.unpackbits``, one float32 per *bit*, so the
    array follows the byte count
    :py:func:`~psd_tools.compression.decompress` returns rather than the pixel
    count -- and at depth 1 those two disagree eightfold, ``length`` being one
    byte per pixel where a row of ``width`` pixels packs into ``width // 8``
    (#737).

    Which is why the question goes to
    :py:func:`~psd_tools.compression.decompressed_size_bound` rather than to a
    flat factor of eight. Both directions of that estimate have a real document
    behind them: a body written a byte per pixel is returned in full, since the
    length check is skipped below depth 8, and unpacks to eight planes; while
    ``colormodes/4x4_1bit_bitmap.psd`` is packed as Photoshop writes it, four
    bytes for four rows, and allocates two planes for a four-pixel width. A flat
    factor would have rejected the second at four times its size. The division
    rounds up, and never to zero: a width that is not a multiple of eight leaves
    a part-used plane, and a part-used plane still has to be paid for.

    What it does not do is repair that width. Those padding bits are returned as
    pixels, so a bitmap document whose width is not a multiple of eight comes
    back scrambled or does not reshape at all -- #768, whose fix will change the
    reshape this arithmetic is written against.

    This bounds the array that is returned, which is what
    :func:`~psd_tools.api.utils.check_pixel_size` estimates by construction. It
    does not model the transient peak: :func:`_parse_array` holds the raw bytes
    and two float32 arrays at once, and :func:`_remove_background` adds several
    more, so the true high-water mark is a small multiple of this for every
    colour mode -- a pre-existing property of this estimate rather than
    anything a colour mode or a depth causes.
    """
    if flat:
        return 1
    if psdimage.depth == 1:
        values = 8 * psdimage._record.image_data.decompressed_size_bound(
            psdimage._record.header
        )
        pixels = psdimage.width * psdimage.height
        # Never below one: an empty image data section bounds at zero bytes, and
        # while `check_pixel_size()` clamps its own `channels` argument, this
        # function's return value is read directly -- by the compositor's
        # sibling estimate and by tests -- so a zero plane count would be a
        # claim about the array rather than an artefact absorbed downstream.
        return max(1, (values + pixels - 1) // pixels)
    planes = psdimage.channels
    if psdimage.color_mode == ColorMode.INDEXED and psdimage.depth == 8:
        planes *= EXPECTED_CHANNELS[ColorMode.INDEXED]
    return planes


def get_image_data(psdimage: "PSDProtocol", channel: str | None) -> np.ndarray:
    # Decided before the guard runs rather than after, so the estimate can match
    # whichever branch is taken. The dimension checks inside check_pixel_size()
    # apply to both, so neither path escapes it.
    flat = (channel == "mask") or (
        channel == "shape" and not has_transparency(psdimage)
    )
    # The guard is here to reject a file before it allocates, so its estimate
    # must not fall below the array that follows. See _image_data_planes() for
    # why the header's own count is not that bound for an indexed document --
    # and why the wider-of-the-pair shape used in composite() is not either.
    check_pixel_size(
        psdimage.width,
        psdimage.height,
        _image_data_planes(psdimage, flat),
        max_alloc_bytes=psdimage._max_alloc_bytes,
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
        image_bytes, cast(Literal[1, 8, 16, 32], psdimage.depth), lut=lut
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
            _parse_array(c.get_data(), c.pixel_depth)  # type: ignore
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
    all. The alternative -- :py:data:`~psd_tools.api.utils.EXPECTED_CHANNELS`
    keyed on the pattern's color mode -- states the width a *document* in that
    mode carries, which is only incidentally the width this pattern stored.
    Multichannel is the mode that can never agree, its entry being 64, the
    format's maximum rather than any pattern's count; but any pattern storing
    fewer color planes than its mode's constant missed the split the same way,
    and the combined array was then rejected downstream as inconsistent with
    the canvas (#741).

    Measured over the 65 patterns Photoshop 2026 ships in
    ``Presets/Patterns/*.pat``: RGB writes slots ``(0, 1, 2)``, RGB with
    transparency ``(0, 1, 2, 25)``, grayscale ``(0,)``.

    That measurement is what the rule rests on, and it is the whole of what it
    rests on: a pattern that wrote its alpha into a color slot instead of a
    trailing one would be read as all color, which is the failure this fixes,
    facing the other way. Nothing in the corpus or in Photoshop's own presets
    is laid out that way, and for multichannel there is no constant to fall
    back on regardless.
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
    lut: np.ndarray | None = None,
) -> np.ndarray:
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
        return np.unpackbits(np.frombuffer(data, np.uint8)).astype(np.float32)
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
