# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import warnings
from psd_tools.constants import Compression, ChannelID

def channels_to_PIL(layer, channels_data):
    from PIL import Image
    size = layer.width(), layer.height()

    bands = {}

    for channel, info in zip(channels_data, layer.channels):

        pil_band = ChannelID.to_PIL(info.id)
        if pil_band is None:
            warnings.warn("Unsupported channel type (%d)" % info.id)
            continue

        if channel.compression == Compression.RAW:
            bands[pil_band] = Image.fromstring("L", size, channel.data, 'L')
        elif channel.compression == Compression.PACK_BITS:
            bands[pil_band] = Image.fromstring("L", size, channel.data, "packbits", 'L')
        elif Compression.is_known(channel.compression):
            warnings.warn("Compression method is not implemented (%s)" % channel.compression)
        else:
            warnings.warn("Unknown compression method (%s)" % channel.compression)

    def as_bands(mode):
        if set(bands.keys()) == set(list(mode)):
            return [bands[band] for band in ['R', 'G', 'B', 'A']]


    for mode in ['RGBA', 'RGB']:
        image_bands = as_bands(mode)
        if image_bands:
            return Image.merge(mode, image_bands)
