"""
PIL IO module.
"""

import io
import logging
from typing import TYPE_CHECKING, cast

from PIL import Image, ImageChops, ImageMath

from psd_tools.api.utils import (
    check_pixel_size,
    get_transparency_index,
    has_transparency,
)
from psd_tools.constants import ChannelID, ColorMode, Compression, Resource
from psd_tools.psd.image_resources import ThumbnailResource, ThumbnailResourceV4
from psd_tools.psd.patterns import Pattern

if TYPE_CHECKING:
    from psd_tools.api.protocols import LayerProtocol, PSDProtocol

logger = logging.getLogger(__name__)


def get_color_mode(mode: str) -> ColorMode:
    """Convert PIL mode to ColorMode."""
    name = mode.upper()
    name = name.rstrip("A")  # Trim alpha.
    name = {"1": "BITMAP", "L": "GRAYSCALE"}.get(name, name)
    return getattr(ColorMode, name)


def get_pil_mode(color_mode: ColorMode, alpha: bool = False) -> str:
    """Get PIL mode from ColorMode."""
    name = {
        ColorMode.GRAYSCALE: "L",
        ColorMode.BITMAP: "1",
        ColorMode.DUOTONE: "L",
        ColorMode.INDEXED: "P",
        ColorMode.MULTICHANNEL: "L",  # TODO: Cannot support in PIL.
    }.get(color_mode, color_mode.name)
    if alpha and name in ("L", "RGB"):
        name += "A"
    return name


def get_pil_channels(pil_mode: str) -> int:
    """Get the number of channels for PIL modes."""
    return {
        "1": 1,
        "L": 1,
        "P": 1,
        "RGB": 3,
        "CMYK": 4,
        "YCbCr": 3,
        "LAB": 3,
        "HSV": 3,
        "I": 1,
        "F": 1,
    }.get(pil_mode, 3)


def get_pil_depth(pil_mode: str) -> int:
    """Get the depth of image for PIL modes."""
    return {
        # Bitmap images are converted to grayscale when the layer is created from pil object
        "1": 8,
        "L": 8,
        "P": 8,
        "RGB": 8,
        "CMYK": 8,
        "YCbCr": 8,
        "LAB": 8,
        "HSV": 8,
        "I": 32,
        "F": 32,
    }.get(pil_mode, 8)


# The "I"/"F" image and the second one `.point()` builds from it, four bytes per
# pixel each, alive together with the "L" they narrow to. Flat rather than
# per-channel: the loop converts one channel at a time, so only one such pair
# exists at any moment however many channels the document stores. Measured at
# 9.0 bytes per pixel in isolation, of which the retained "L" is counted with
# the other converted channels below.
_CONVERSION_TRANSIENT: int = 8

# `_remove_white_background()`, in bytes per pixel: the four bands `split()`
# hands back, the `ImageMath` expression promoting each of three to "I" at four
# bytes a pixel, the three "L" results, and the `merge()` that reassembles them.
# Measured at 23.8 in isolation; rounded well up because PIL's buffers are
# C-side and the instrument that reads them is coarser than the one numpy gets.
_WHITE_BACKGROUND_TRANSIENT: int = 35

# PIL rounds each image up to its arena's block granularity, so the process grows
# by a little more than the bytes the images ask for. Every other term here
# counts requested bytes, as the numpy model does; this one covers the
# difference, measured at no more than 0.23 bytes per pixel over the whole
# colour-mode/depth/compression matrix.
_ALLOCATOR_SLACK: int = 1

# Bytes live at the codec's own peak, as a multiple of the decompressed size.
# One step wider than the numpy path's table throughout, because this path asks
# `get_data()` to split the buffer per channel and the split is a second copy.
_DECOMPRESS_PEAK: dict[Compression, int] = {
    Compression.RAW: 2,
    Compression.RLE: 3,
    Compression.ZIP: 3,
    Compression.ZIP_WITH_PREDICTION: 4,
}


def _image_data_peak_bytes(
    psd: "PSDProtocol", channel: int | None, apply_icc: bool
) -> int:
    """Bytes :func:`convert_image_data_to_pil` allocates at its high-water mark.

    The counterpart to :func:`~psd_tools.api.numpy_io._image_data_peak_bytes`,
    and it corrects this path's estimate in *both* directions (#767).

    The old estimate was ``width * height * channels * 4``, four bytes per pixel
    per stored channel -- a float32 plane, which is what the numpy path returns
    and what this one never holds. ``_create_image()`` yields "L", "P" or "1",
    and PIL stores a byte per pixel in all three. It was wrong in both
    directions and by different amounts: a multi-band 8-bit document was turned
    away below its budget, while the 16- and 32-bit branches, which build an
    "I"/"F" image and then a second through ``.point()``, ran straight past it,
    as did anything whose alpha channel sends it through
    ``_remove_white_background()``. Correcting it moves both ways -- a little
    looser on 8-bit RGB and LAB, several times tighter at depth 16 and 32 and on
    RGBA at any depth.

    Phase-maxed like the numpy model, over the same three-stage shape:
    decompress, convert each channel, assemble. Every term is gated on the
    branch that allocates it -- indexed and multichannel documents take
    ``channels[0]`` and never merge, ``post_process()`` is a no-op without CMYK,
    a profile or an alpha channel, and the white background is removed only from
    an RGBA result. Ungated, those terms would make this *tighter* than the
    estimate it replaces on exactly the 8-bit documents it is meant to stop
    over-counting.

    PIL's buffers are C-side and invisible to ``tracemalloc``, so unlike the
    numpy model this is an analytic count of the images the path holds, with each
    phase measured in isolation rather than fitted to a whole-call figure -- a
    whole-call RSS delta cannot see a phase that reuses what the phase before it
    released. The same two exclusions apply as on the numpy side: per-object
    allocator overhead, and the RAW source buffer being counted even where
    ``get_data()`` would not re-allocate it.
    """
    pixels = psd.width * psd.height
    depth = psd.depth
    # Rounded up per row, as the format pads a 1-bit row to a byte boundary.
    source = ((psd.width * depth + 7) // 8) * psd.height * psd.channels
    conversion = _CONVERSION_TRANSIENT if depth in (16, 32) else 0
    decompress = _DECOMPRESS_PEAK[psd._record.image_data.compression] * source

    if channel is not None:
        # One `_create_image()` and no assembly: nothing is merged, there is no
        # alpha to put, and `_remove_white_background()` cannot fire on one band.
        return max(decompress, source + pixels * (1 + conversion))

    mode = get_pil_mode(psd.color_mode)
    bands = get_pil_channels(mode)
    alpha = has_transparency(psd)
    # Indexed and multichannel documents keep `channels[0]` and never merge.
    merged = (
        0 if psd.color_mode in (ColorMode.INDEXED, ColorMode.MULTICHANNEL) else bands
    )
    icc = apply_icc and Resource.ICC_PROFILE in psd.image_resources
    # A profile rewrites the image to RGB, so what `putalpha()` and the white
    # background see afterwards is not the mode the colour mode implies: a CMYK
    # or grayscale document with a profile *and* an alpha channel comes out RGBA
    # like any other, and is charged accordingly.
    final_bands = 3 if icc else bands
    widened = alpha and (icc or mode in ("RGB", "L"))
    # `post_process()`'s three widenings, whichever of them this document
    # reaches. They run in sequence and each frees what it replaced, so the
    # widest bounds the phase: the CMYK inversion is a second image of the same
    # mode; `_apply_icc()` holds its input alongside the RGB it writes;
    # `putalpha()` converts in place and holds the mode it is leaving alongside
    # the one it is building.
    post = max(
        bands if mode == "CMYK" else 0,
        bands + 3 if icc else 0,
        2 * final_bands + 1 if widened else 0,
    )
    # `_remove_white_background()` only ever sees an RGBA image -- which is to
    # say a three-band one that `putalpha()` has just widened.
    white_background = (
        _WHITE_BACKGROUND_TRANSIENT if widened and final_bands == 3 else 0
    )

    # One narrow image per stored channel, held in `channels` to the end, and
    # the decompressed buffer it was built from, held just as long.
    retained = source + pixels * (psd.channels + _ALLOCATOR_SLACK)
    return max(
        decompress,
        retained + pixels * conversion,
        retained + pixels * (merged + post),
        retained + pixels * (merged + 1 + white_background),
    )


def convert_image_data_to_pil(
    psd: "PSDProtocol", channel: int | None, apply_icc: bool
) -> Image.Image | None:
    """Convert ImageData to PIL Image.

    :raises ValueError: If an invalid channel is specified
    """
    # The header's own channel count, with none of the corrections the numpy
    # path needs (:func:`~psd_tools.api.numpy_io._image_data_planes`), because
    # PIL allocates a plane per stored channel at every depth and mode. It sizes
    # nothing here -- `_image_data_peak_bytes()` does that -- but it still names
    # the shape the error message reports.
    check_pixel_size(
        psd.width,
        psd.height,
        psd.channels,
        max_alloc_bytes=psd._max_alloc_bytes,
        estimated_bytes=_image_data_peak_bytes(psd, channel, apply_icc),
    )

    if channel is not None and channel >= psd.channels:
        raise ValueError(
            f"Invalid channel specified: {channel} (max {psd.channels - 1})"
        )

    # Support alpha channel via ChannelID enum.
    if channel == ChannelID.TRANSPARENCY_MASK:
        channel = get_pil_channels(get_pil_mode(psd.color_mode))
        if channel >= psd.channels:
            return None

    alpha = None
    icc = None
    channel_data = psd._record.image_data.get_data(psd._record.header)
    size = (psd.width, psd.height)
    if channel is None:
        if not isinstance(channel_data, list):
            raise TypeError(
                f"Expected list of channel data, got {type(channel_data).__name__}"
            )
        channels = [_create_image(size, c, psd.depth) for c in channel_data]

        if has_transparency(psd):
            alpha = channels[get_transparency_index(psd)]

        if psd.color_mode == ColorMode.INDEXED:
            image = channels[0]
            image.putpalette(psd._record.color_mode_data.interleave())
        elif psd.color_mode == ColorMode.MULTICHANNEL:
            image = channels[0]  # Multi-channel mode is a collection of alpha.
        else:
            mode = get_pil_mode(psd.color_mode)
            image = Image.merge(mode, channels[: get_pil_channels(mode)])

        if apply_icc and (Resource.ICC_PROFILE in psd.image_resources):
            icc = psd.image_resources.get_data(Resource.ICC_PROFILE)
    else:
        if not isinstance(channel_data, list):
            raise TypeError(
                f"Expected list of channel data, got {type(channel_data).__name__}"
            )
        image = _create_image(size, channel_data[channel], psd.depth)

    if not image:
        return None

    image = post_process(image, alpha, icc)
    return _remove_white_background(image)


def convert_layer_to_pil(
    layer: "LayerProtocol", channel: int | None, apply_icc: bool
) -> Image.Image | None:
    """Convert Layer to PIL Image."""
    alpha = None
    icc = None
    image = None
    if channel is None:
        image = _merge_channels(layer)
        alpha = _get_channel(layer, ChannelID.TRANSPARENCY_MASK)
        if (
            apply_icc
            and layer._psd is not None
            and (Resource.ICC_PROFILE in layer._psd.image_resources)
        ):
            icc = layer._psd.image_resources.get_data(Resource.ICC_PROFILE)
    else:
        image = _get_channel(layer, channel)

    if not image or (channel is not None and channel < 0):
        return image  # Return None, alpha or mask.

    return post_process(image, alpha, icc)


def post_process(
    image: Image.Image,
    alpha: Image.Image | None,
    icc_profile: bytes | None = None,
) -> Image.Image:
    # Fix inverted CMYK.
    if image.mode == "CMYK":
        image = ImageChops.invert(image)

    if icc_profile:
        image = _apply_icc(image, icc_profile)

    # In Pillow, alpha channel is only available in RGB or L.
    if alpha and image.mode in ("RGB", "L"):
        image.putalpha(alpha)
    return image


def convert_pattern_to_pil(pattern: Pattern) -> Image.Image:
    """Convert Pattern to PIL Image."""
    mode = get_pil_mode(pattern.image_mode)
    # The order is different here.
    top, left, bottom, right = pattern.data.rectangle
    size = right - left, bottom - top
    channels = [
        _create_image(size, c.get_data() or b"", c.pixel_depth or 8).convert("L")
        for c in pattern.data.channels
        if c.is_written
    ]
    alpha = None
    channel_size = get_pil_channels(mode)
    if mode in ("RGB", "L") and len(channels) > channel_size:
        alpha = channels[channel_size]
    if mode == "P":
        image = channels[0]
        image.putpalette([x for rgb in pattern.color_table for x in rgb])
    else:
        image = Image.merge(mode, channels[:channel_size])

    return post_process(image, alpha, None)  # TODO: icc support?


def convert_thumbnail_to_pil(
    thumbnail: ThumbnailResource | ThumbnailResourceV4,
) -> Image.Image:
    """Convert thumbnail resource."""
    if thumbnail.fmt == 0:
        image = Image.frombytes(
            "RGBX",
            (thumbnail.width, thumbnail.height),
            thumbnail.data,
            "raw",
            thumbnail._RAW_MODE,
            thumbnail.row,
        )
    elif thumbnail.fmt == 1:
        with io.BytesIO(thumbnail.data) as f:
            image = Image.open(f)
            image.load()
    else:
        raise ValueError("Unknown thumbnail format %d" % (thumbnail.fmt))
    return image


def _merge_channels(layer: "LayerProtocol") -> Image.Image | None:
    if layer._psd is None:
        return None
    mode = get_pil_mode(layer._psd.color_mode)
    channel_images = [
        _get_channel(layer, info.id)
        for info in layer._record.channel_info
        if info.id >= 0
    ]
    if any(image is None for image in channel_images):
        return None
    channels = _check_channels(
        [img for img in channel_images if img is not None], layer._psd.color_mode
    )
    return Image.merge(mode, channels)  # type: ignore


def _get_channel(layer: "LayerProtocol", channel: int) -> Image.Image | None:
    if layer._psd is None:
        return None
    if channel == ChannelID.USER_LAYER_MASK:
        if layer.mask is None:
            logger.info("Layer has no mask.")
            return None
        width = layer.mask.data.width
        height = layer.mask.data.height
    elif channel == ChannelID.REAL_USER_LAYER_MASK:
        if layer.mask is None:
            logger.info("Layer has no real mask.")
            return None
        width = layer.mask.data.real_width
        height = layer.mask.data.real_height
    else:
        width, height = layer.width, layer.height

    index = {info.id: i for i, info in enumerate(layer._record.channel_info)}
    if channel not in index:
        return None
    depth = layer._psd.depth
    channel_data = layer._channels[index[cast(ChannelID, channel)]]
    if width == 0 or height == 0 or len(channel_data.data) == 0:
        return None
    channel_bytes = channel_data.get_data(width, height, depth, layer._psd.version)
    return _create_image((width, height), channel_bytes, depth)


def _create_image(size: tuple[int, int], data: bytes, depth: int) -> Image.Image:
    if depth == 8:
        return Image.frombytes("L", size, data, "raw")
    elif depth == 16:
        image = Image.frombytes("I", size, data, "raw", "I;16B")
        return image.point(lambda x: x * (1.0 / 256.0)).convert("L")
    elif depth == 32:
        image = Image.frombytes("F", size, data, "raw", "F;32BF")
        # TODO: Check grayscale range.
        return image.point(lambda x: x * (256.0)).convert("L")
    elif depth == 1:
        return Image.frombytes("1", size, data, "raw", "1;I")
    else:
        raise ValueError("Unsupported depth: %g" % depth)


def _check_channels(
    channels: list[Image.Image], color_mode: ColorMode
) -> list[Image.Image]:
    expected_channels = ColorMode.channels(color_mode)
    if len(channels) > expected_channels:
        # Seems possible when FilterMask is attached.
        logger.debug(
            "Channels mismatch: expected %g != given %g"
            % (expected_channels, len(channels))
        )
        channels = channels[:expected_channels]
    elif len(channels) < expected_channels:
        raise ValueError(
            "Channels mismatch: expected %g != given %g"
            % (expected_channels, len(channels))
        )
    return channels


def _apply_icc(image: Image.Image, icc_profile: bytes) -> Image.Image:
    """Apply ICC Color profile."""
    try:
        from PIL import ImageCms  # noqa: PLC0415
    except ImportError:
        logger.warning("ICC profile found but not supported. Install little-cms.")
        return image

    try:
        with io.BytesIO(icc_profile) as f:
            in_profile = ImageCms.ImageCmsProfile(f)
        out_profile = ImageCms.createProfile("sRGB")

        alpha = None
        if image.mode in ("RGBA", "LA"):
            alpha = image.getchannel("A")

        working_image = (
            image
            if "A" not in image.mode
            else image.convert(image.mode.replace("A", ""))
        )

        result = ImageCms.profileToProfile(
            working_image, in_profile, out_profile, outputMode="RGB"
        )

    except ImageCms.PyCMSError as e:
        logger.error("Failed to apply ICC profile: %s" % (e))
        return image

    if result is None:
        logger.error("Failed to apply ICC profile.")
        return image

    if alpha is not None:
        result.putalpha(alpha)

    logger.debug(f"input mode: {image.mode}, output mode: {result.mode}")
    return result


def _remove_white_background(image: Image.Image) -> Image.Image:
    """Remove white background in the preview image."""
    if image.mode == "RGBA":
        bands = image.split()
        a = bands[3]
        rgb = [
            ImageMath.lambda_eval(
                lambda args: args["convert"](
                    args["float"](args["x"] + args["a"] - 255)
                    * 255.0
                    / args["float"](args["max"](args["a"], 1))
                    * args["float"](args["min"](args["a"], 1))
                    + args["float"](args["x"])
                    * args["float"](1 - args["min"](args["a"], 1)),
                    "L",
                ),
                x=x,
                a=a,
            )
            for x in bands[:3]
        ]
        return Image.merge(bands=rgb + [a], mode="RGBA")

    return image
