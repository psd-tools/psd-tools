# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import warnings
from psd_tools.constants import Compression, ChannelID, ColorMode


def _channels_data_to_PIL(channels_data, channel_types, size):
    from PIL import Image
    if size == (0, 0):
        return

    bands = {}

    for channel, channel_type in zip(channels_data, channel_types):

        pil_band = ChannelID.to_PIL(channel_type)
        if pil_band is None:
            warnings.warn("Unsupported channel type (%d)" % channel_type)
            continue
        if channel.compression == Compression.RAW:
            bands[pil_band] = Image.fromstring("L", size, channel.data, "raw", 'L')
        elif channel.compression == Compression.PACK_BITS:
            bands[pil_band] = Image.fromstring("L", size, channel.data, "packbits", 'L')
        elif Compression.is_known(channel.compression):
            warnings.warn("Compression method is not implemented (%s)" % channel.compression)
        else:
            warnings.warn("Unknown compression method (%s)" % channel.compression)

    for mode in ['RGBA', 'RGB']:
        if set(bands.keys()) == set(list(mode)):
            return Image.merge(mode, [bands[band] for band in mode])


def layer_to_PIL(parsed_data, layer_num):
    layers = parsed_data.layer_and_mask_data.layers
    layer = layers.layer_records[layer_num]

    channels_data = layers.channel_image_data[layer_num]
    size = layer.width(), layer.height()
    channel_types = [info.id for info in layer.channels]

    return _channels_data_to_PIL(channels_data, channel_types, size)

def image_to_PIL(parsed_data):
    header = parsed_data.header
    size = header.width, header.height

    if header.color_mode == ColorMode.RGB:
        assert header.number_of_channels == 3
        channel_types = [0, 1, 2]
    else:
        warnings.warn("Unsupported color mode (%s)" % header.color_mode)
        return

    return _channels_data_to_PIL(
        parsed_data.image_data,
        channel_types,
        size,
    )
