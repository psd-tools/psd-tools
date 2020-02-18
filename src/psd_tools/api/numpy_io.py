import numpy as np
import logging

from psd_tools.constants import Resource, ChannelID, Tag

logger = logging.getLogger(__name__)


def get_array(layer, channel):
    if layer.kind == 'psdimage':
        return get_image_data(layer, channel)
    else:
        return get_layer_data(layer, channel)
    return None


def get_image_data(psd, channel):
    if (channel == 'mask') or (channel == 'shape' and not _has_alpha(psd)):
        return np.ones((psd.height, psd.width, 1))

    data = psd._record.image_data.get_data(psd._record.header, False)
    data = _parse_array(data, psd.depth)
    data = data.reshape((-1, psd.height, psd.width)).transpose((1, 2, 0))
    if channel == 'shape':
        return data[:, :, -1]
    elif channel == 'color':
        return data[:, :, :psd.channels]
    return data


def get_layer_data(layer, channel):

    def _find_channel(layer, width, height, condition):
        depth, version = layer._psd.depth, layer._psd.version
        iterator = zip(layer._record.channel_info, layer._channels)
        channels = [
            _parse_array(
                data.get_data(width, height, depth, version), depth)
            for info, data in iterator if condition(info) and len(data.data) > 0
        ]
        if len(channels) and channels[0].size > 0:
            return np.stack(channels, axis=1).reshape((height, width, -1))
        return None

    if channel == 'color':
        return _find_channel(layer, layer.width, layer.height,
                             lambda x: x.id >= 0)
    elif channel == 'shape':
        return _find_channel(layer, layer.width, layer.height,
                             lambda x: x.id == ChannelID.TRANSPARENCY_MASK)
    elif channel == 'mask':
        if layer.mask._has_real():
            channel_id = ChannelID.REAL_USER_LAYER_MASK
        else:
            channel_id = ChannelID.USER_LAYER_MASK
        return _find_channel(layer, layer.mask.width, layer.mask.height,
                             lambda x: x.id == channel_id)

    color = _find_channel(layer, layer.width, layer.height, lambda x: x.id >= 0)
    shape = _find_channel(layer, layer.width, layer.height,
                          lambda x: x.id == ChannelID.TRANSPARENCY_MASK)
    if shape is None:
        return color
    return np.concatenate([color, shape], axis=2)


def get_pattern(pattern, version=1):
    """Get pattern array."""
    height, width = pattern.data.rectangle[2], pattern.data.rectangle[3]
    return np.stack([
        _parse_array(c.get_data(version), c.pixel_depth)
        for c in pattern.data.channels if c.is_written
    ], axis=1).reshape((height, width, -1))


def _has_alpha(psd):
    if psd.tagged_blocks:
        keys = (
            Tag.SAVING_MERGED_TRANSPARENCY,
            Tag.SAVING_MERGED_TRANSPARENCY16,
            Tag.SAVING_MERGED_TRANSPARENCY32,
        )
        return any(key in psd.tagged_blocks for key in keys)
    return False


def _parse_array(data, depth):
    if depth == 8:
        return np.frombuffer(data, np.uint8) / float(255)
    elif depth == 16:
        return np.frombuffer(data, np.uint16) / float(65535)
    elif depth == 32:
        return np.frombuffer(data, np.float32).astype(np.float)
    elif depth == 1:
        return np.unpackbits(np.frombuffer(data, np.uint8)).astype(np.float)
    else:
        raise ValueError('Unsupported depth: %g' % depth)
