import logging
from typing import TYPE_CHECKING, Any, Callable, Literal, Optional, Union, cast

import numpy as np

if TYPE_CHECKING:
    from psd_tools.api.protocols import LayerProtocol, PSDProtocol

from psd_tools.api.utils import (
    EXPECTED_CHANNELS,
    get_transparency_index,
    has_transparency,
)
from psd_tools.constants import ChannelID, ColorMode
from psd_tools.psd.patterns import Pattern

logger = logging.getLogger(__name__)


def get_array(
    layer: Union["LayerProtocol", "PSDProtocol"], channel: Optional[str], **kwargs: Any
) -> Optional[np.ndarray]:
    # Import at runtime to avoid circular imports
    from psd_tools.api.layers import Layer
    from psd_tools.api.psd_image import PSDImage

    if isinstance(layer, PSDImage):
        return get_image_data(layer, channel)
    elif isinstance(layer, Layer):
        return get_layer_data(layer, channel, **kwargs)
    raise TypeError(
        f"Expected LayerProtocol or PSDProtocol, got {type(layer).__name__}"
    )


def get_image_data(psdimage: "PSDProtocol", channel: Optional[str]) -> np.ndarray:
    if (channel == "mask") or (channel == "shape" and not has_transparency(psdimage)):
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
    layer: "LayerProtocol", channel: Optional[str], real_mask: bool = True
) -> Optional[np.ndarray]:
    def _find_channel(
        layer: "LayerProtocol",
        width: int,
        height: int,
        condition: Callable[[Any], bool],
    ) -> Optional[np.ndarray]:
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
    height, width = pattern.data.rectangle[2], pattern.data.rectangle[3]
    return np.stack(
        [
            _parse_array(c.get_data(), c.pixel_depth)  # type: ignore
            for c in pattern.data.channels
            if c.is_written
        ],
        axis=1,
    ).reshape((height, width, -1))


def _parse_array(
    data: Union[bytes, bytearray],
    depth: Literal[1, 8, 16, 32],
    lut: Optional[np.ndarray] = None,
) -> np.ndarray:
    if depth == 8:
        parsed = np.frombuffer(data, ">u1")
        if lut is not None:
            parsed = lut[parsed]
        return parsed.astype(np.float32) / 255.0
    elif depth == 16:
        return np.frombuffer(data, ">u2").astype(np.float32) / 65535.0
    elif depth == 32:
        return np.frombuffer(data, ">f4")
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
