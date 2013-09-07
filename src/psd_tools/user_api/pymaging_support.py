# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import array

try:
    import packbits
    from pymaging.image import LoadedImage
    from pymaging.colors import RGB, RGBA
    from pymaging.pixelarray import get_pixel_array
except ImportError:
    LoadedImage = None
    packbits = None

from psd_tools.constants import ColorMode, Compression, ChannelID


def extract_composite_image(decoded_data):
    """
    Converts a composite (merged) image from the ``decoded_data``
    to a pymaging.Image.
    """
    header = decoded_data.header
    size = header.width, header.height
    depth, mode = _validate_header(header)

    return _channels_data_to_image(decoded_data.image_data, mode, size, depth)

def extract_layer_image(decoded_data, layer_index):
    """
    Converts a layer from the ``decoded_data`` to a ``pymaging.Image``.
    """
    layers = decoded_data.layer_and_mask_data.layers
    layer = layers.layer_records[layer_index]

    channels_data = layers.channel_image_data[layer_index]
    channel_types = [info.id for info in layer.channels]
    size = layer.width(), layer.height()

    depth, _ = _validate_header(decoded_data.header)

    # FIXME: support for layers with mask (there would be 5 channels in this case)
    if channel_types[0] == ChannelID.TRANSPARENCY_MASK:
        # move alpha channel to the end
        channels_data = [channels_data[i] for i in [1, 2, 3, 0]]

    mode = _get_mode(len(channels_data))
    return _channels_data_to_image(channels_data, mode, size, depth)


def _channels_data_to_image(channels_data, mode, size, depth):

    if size == (0, 0):
        return

    w, h = size
    num_channels = mode.length
    assert depth == 8
    assert len(channels_data) == num_channels

    total_size = w*h*num_channels
    image_bytes = array.array(str("B"), [0]*total_size)

    for index, channel in enumerate(channels_data):

        data = channel.data # zip and zip-with-prediction data is already decoded
        if channel.compression == Compression.PACK_BITS:
            data = packbits.decode(data)

        image_bytes[index::num_channels] = array.array(str("B"), data)

    pixels = get_pixel_array(image_bytes, w, h, mode.length)

    return LoadedImage(mode, w, h, pixels)


def _get_mode(number_of_channels):
    mode = None
    if number_of_channels == 3:
        mode = RGB
    elif number_of_channels == 4:
        mode = RGBA
    return mode


def _validate_header(header):
    """
    Validates header and returns (depth, mode) tuple.
    """
    if LoadedImage is None or packbits is None:
        raise Exception("This module requires `pymaging` and `packbits` packages.")

    if header.color_mode != ColorMode.RGB:
        raise NotImplementedError(
            "This color mode (%s) is not supported yet" % ColorMode.name_of(header.color_mode)
        )

    mode = _get_mode(header.number_of_channels)
    if mode is None:
        raise NotImplementedError("This number of channels (%d) is unsupported for this color mode (%s)" % (
                         header.number_of_channels, header.color_mode))

    if header.depth != 8:
        raise NotImplementedError("Only 8bit images are currently supported with pymaging.")

    return 8, mode

