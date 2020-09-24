import numpy as np
import logging

from psd_tools.constants import ChannelID, Tag, ColorMode, Resource

logger = logging.getLogger(__name__)

EXPECTED_CHANNELS = {
    ColorMode.BITMAP: 1,
    ColorMode.GRAYSCALE: 1,
    ColorMode.INDEXED: 3,
    ColorMode.RGB: 3,
    ColorMode.CMYK: 4,
    ColorMode.MULTICHANNEL: 64,
    ColorMode.DUOTONE: 2,
    ColorMode.LAB: 3,
}


def get_array(layer, channel, **kwargs):
    if layer.kind == 'psdimage':
        return get_image_data(layer, channel)
    else:
        return get_layer_data(layer, channel, **kwargs)
    return None


def get_image_data(psd, channel):
    if (channel == 'mask'
        ) or (channel == 'shape' and not has_transparency(psd)):
        return np.ones((psd.height, psd.width, 1), dtype=np.float32)

    lut = None
    if psd.color_mode == ColorMode.INDEXED:
        lut = np.frombuffer(psd._record.color_mode_data.value, np.uint8)
        lut = lut.reshape((3, -1)).transpose()
    data = psd._record.image_data.get_data(psd._record.header, False)
    data = _parse_array(data, psd.depth, lut=lut)
    if lut is not None:
        data = data.reshape((psd.height, psd.width, -1))
    else:
        data = data.reshape((-1, psd.height, psd.width)).transpose((1, 2, 0))
    data = _remove_background(data, psd)

    if channel == 'shape':
        return np.expand_dims(data[:, :, get_transparency_index(psd)], 2)
    elif channel == 'color':
        if psd.color_mode == ColorMode.MULTICHANNEL:
            return data
        # TODO: psd.color_mode == ColorMode.INDEXED --> Convert?
        return data[:, :, :EXPECTED_CHANNELS[psd.color_mode]]

    return data


def get_layer_data(layer, channel, real_mask=True):
    def _find_channel(layer, width, height, condition):
        depth, version = layer._psd.depth, layer._psd.version
        iterator = zip(layer._record.channel_info, layer._channels)
        channels = [
            _parse_array(data.get_data(width, height, depth, version), depth)
            for info, data in iterator
            if condition(info) and len(data.data) > 0
        ]
        if len(channels) and channels[0].size > 0:
            result = np.stack(channels, axis=1).reshape((height, width, -1))
            expected_channels = EXPECTED_CHANNELS.get(layer._psd.color_mode)
            if result.shape[2] > expected_channels:
                logger.debug('Extra channel found')
                return result[:, :, :expected_channels]
            return result
        return None

    if channel == 'color':
        return _find_channel(
            layer, layer.width, layer.height, lambda x: x.id >= 0
        )
    elif channel == 'shape':
        return _find_channel(
            layer, layer.width, layer.height,
            lambda x: x.id == ChannelID.TRANSPARENCY_MASK
        )
    elif channel == 'mask':
        if layer.mask._has_real() and real_mask:
            channel_id = ChannelID.REAL_USER_LAYER_MASK
        else:
            channel_id = ChannelID.USER_LAYER_MASK
        return _find_channel(
            layer, layer.mask.width, layer.mask.height,
            lambda x: x.id == channel_id
        )

    color = _find_channel(
        layer, layer.width, layer.height, lambda x: x.id >= 0
    )
    shape = _find_channel(
        layer, layer.width, layer.height,
        lambda x: x.id == ChannelID.TRANSPARENCY_MASK
    )
    if shape is None:
        return color
    return np.concatenate([color, shape], axis=2)


def get_pattern(pattern):
    """Get pattern array."""
    height, width = pattern.data.rectangle[2], pattern.data.rectangle[3]
    return np.stack([
        _parse_array(c.get_data(), c.pixel_depth)
        for c in pattern.data.channels if c.is_written
    ],
                    axis=1).reshape((height, width, -1))


def has_transparency(psd):
    keys = (
        Tag.SAVING_MERGED_TRANSPARENCY,
        Tag.SAVING_MERGED_TRANSPARENCY16,
        Tag.SAVING_MERGED_TRANSPARENCY32,
    )
    if psd.tagged_blocks and any(key in psd.tagged_blocks for key in keys):
        return True
    if psd.channels > EXPECTED_CHANNELS.get(psd.color_mode):
        alpha_ids = psd.image_resources.get_data(Resource.ALPHA_IDENTIFIERS)
        if alpha_ids and all(x > 0 for x in alpha_ids):
            return False
        return True
    return False


def get_transparency_index(psd):
    alpha_ids = psd.image_resources.get_data(Resource.ALPHA_IDENTIFIERS)
    if alpha_ids:
        try:
            offset = alpha_ids.index(0)
            return psd.channels - len(alpha_ids) + offset
        except ValueError:
            pass
    return -1  # Assume the last channel is the transparency


def _parse_array(data, depth, lut=None):
    if depth == 8:
        parsed = np.frombuffer(data, '>u1')
        if lut is not None:
            parsed = lut[parsed]
        return parsed.astype(np.float32) / 255.
    elif depth == 16:
        return np.frombuffer(data, '>u2').astype(np.float32) / 65535.
    elif depth == 32:
        return np.frombuffer(data, '>f4')
    elif depth == 1:
        return np.unpackbits(np.frombuffer(data, np.uint8)).astype(np.float32)
    else:
        raise ValueError('Unsupported depth: %g' % depth)


def _remove_background(data, psd):
    """ImageData preview is rendered on a white background."""
    if psd.color_mode == ColorMode.RGB and data.shape[2] > 3:
        color = data[:, :, :3]
        alpha = data[:, :, 3:4]
        a = np.repeat(alpha, color.shape[2], axis=2)
        color[a > 0] = (color + alpha - 1)[a > 0] / a[a > 0]
        data[:, :, :3] = color
    return data
