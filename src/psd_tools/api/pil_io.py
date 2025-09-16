"""
PIL IO module.
"""

from __future__ import annotations

import io
import logging
from typing import Any

from PIL import Image
from PIL.Image import Image as PILImage

from psd_tools.api.numpy_io import get_transparency_index, has_transparency
from psd_tools.constants import ChannelID, ColorMode, Resource
from psd_tools.psd.image_resources import ThumbnailResource, ThumbnailResourceV4
from psd_tools.psd.patterns import Pattern

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


def convert_image_data_to_pil(
    psd: Any, channel: int | None, apply_icc: bool
) -> PILImage | None:
    """Convert ImageData to PIL Image."""

    assert channel is None or channel < psd.channels, (
        "Invalid channel specified: %s" % channel
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
        image = _create_image(size, channel_data[channel], psd.depth)

    if not image:
        return None

    image = post_process(image, alpha, icc)
    return _remove_white_background(image)


# TODO: Type hint for layer.
def convert_layer_to_pil(
    layer: Any, channel: int | None, apply_icc: bool
) -> PILImage | None:
    """Convert Layer to PIL Image."""
    alpha = None
    icc = None
    image = None
    if channel is None:
        image = _merge_channels(layer)
        alpha = _get_channel(layer, ChannelID.TRANSPARENCY_MASK)
        if apply_icc and (Resource.ICC_PROFILE in layer._psd.image_resources):
            icc = layer._psd.image_resources.get_data(Resource.ICC_PROFILE)
    else:
        image = _get_channel(layer, channel)

    if not image or (channel is not None and channel < 0):
        return image  # Return None, alpha or mask.

    return post_process(image, alpha, icc)


def post_process(
    image: PILImage, alpha: PILImage | None, icc_profile: bytes | None = None
) -> PILImage:
    # Fix inverted CMYK.
    if image.mode == "CMYK":
        from PIL import ImageChops

        image = ImageChops.invert(image)

    if icc_profile:
        image = _apply_icc(image, icc_profile)

    # In Pillow, alpha channel is only available in RGB or L.
    if alpha and image.mode in ("RGB", "L"):
        image.putalpha(alpha)
    return image


def convert_pattern_to_pil(pattern: Pattern) -> PILImage:
    """Convert Pattern to PIL Image."""
    mode = get_pil_mode(pattern.image_mode)
    # The order is different here.
    size = pattern.data.rectangle[3], pattern.data.rectangle[2]
    channels = [
        _create_image(size, c.get_data(), c.pixel_depth).convert("L")
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
) -> PILImage:
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


def _merge_channels(layer: Any) -> PILImage | None:
    mode = get_pil_mode(layer._psd.color_mode)
    channels = [
        _get_channel(layer, info.id)
        for info in layer._record.channel_info
        if info.id >= 0
    ]
    if any(image is None for image in channels):
        return None
    channels = _check_channels(channels, layer._psd.color_mode)
    return Image.merge(mode, channels)  # type: ignore


def _get_channel(layer: Any, channel: int) -> PILImage | None:
    if channel == ChannelID.USER_LAYER_MASK:
        width = layer.mask._data.right - layer.mask._data.left
        height = layer.mask._data.bottom - layer.mask._data.top
    elif channel == ChannelID.REAL_USER_LAYER_MASK:
        width = layer.mask._data.real_right - layer.mask._data.real_left
        height = layer.mask._data.real_bottom - layer.mask._data.real_top
    else:
        width, height = layer.width, layer.height

    index = {info.id: i for i, info in enumerate(layer._record.channel_info)}
    if channel not in index:
        return None
    depth = layer._psd.depth
    channel_data = layer._channels[index[channel]]
    if width == 0 or height == 0 or len(channel_data.data) == 0:
        return None
    channel_bytes = channel_data.get_data(width, height, depth, layer._psd.version)
    return _create_image((width, height), channel_bytes, depth)


def _create_image(size: tuple[int, int], data: bytes, depth: int) -> PILImage:
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


def _check_channels(channels, color_mode):
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


def _apply_icc(image: PILImage, icc_profile: bytes) -> PILImage:
    """Apply ICC Color profile."""
    try:
        from PIL import ImageCms
    except ImportError:
        logger.warning("ICC profile found but not supported. Install little-cms.")
        return image

    try:
        with io.BytesIO(icc_profile) as f:
            in_profile = ImageCms.ImageCmsProfile(f)
        out_profile = ImageCms.createProfile("sRGB")
        outputMode = image.mode if image.mode in ("L", "LA", "RGBA") else "RGB"
        result = ImageCms.profileToProfile(
            image, in_profile, out_profile, outputMode=outputMode
        )
    except ImageCms.PyCMSError as e:
        logger.error("Failed to apply ICC profile: %s" % (e))
        return image

    if result is None:
        logger.error("Failed to apply ICC profile.")
        return image

    return result


def _remove_white_background(image: PILImage) -> PILImage:
    """Remove white background in the preview image."""
    from PIL import ImageMath

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
                    + args["float"](args["x"]) * args["float"](1 - args["min"](args["a"], 1)),
                    "L",
                ),
                x=x,
                a=a,
            )
            for x in bands[:3]
        ]
        return Image.merge(bands=rgb + [a], mode="RGBA")

    return image
