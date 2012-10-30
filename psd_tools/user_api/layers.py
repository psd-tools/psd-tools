# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, print_function
import warnings

from psd_tools.constants import (Compression, ChannelID, ColorMode,
                                 TaggedBlock, SectionDivider)


def group_layers(decoded_data):
    """
    Returns a nested dict with PSD layer group information.
    """
    layer_records = decoded_data.layer_and_mask_data.layers.layer_records

    root = dict(layers = [])
    group_stack = [root]

    for index, layer in reversed(list(enumerate(layer_records))):
        current_group = group_stack[-1]

        blocks = dict(layer.tagged_blocks)

        name = blocks.get(TaggedBlock.UNICODE_LAYER_NAME, layer.name)
        layer_id = blocks.get(TaggedBlock.LAYER_ID)
        divider = blocks.get(TaggedBlock.SECTION_DIVIDER_SETTING, None)
        visible = layer.flags.visible
        opacity = layer.opacity
        blend_mode = layer.blend_mode

        if divider is not None:
            # group information
            if divider.type in [SectionDivider.CLOSED_FOLDER, SectionDivider.OPEN_FOLDER]:
                # group begins
                group = dict(
                    id = layer_id,
                    index = index,
                    name = name,
                    layers = [],
                    closed = divider.type == SectionDivider.CLOSED_FOLDER,

                    blend_mode = blend_mode,
                    visible = visible,
                    opacity = opacity,
                )
                group_stack.append(group)
                current_group['layers'].append(group)

            elif divider.type == SectionDivider.BOUNDING_SECTION_DIVIDER:
                # group ends
                group_stack.pop()

            else:
                warnings.warn("invalid state")
        else:
            # layer with image

            current_group['layers'].append(dict(
                id = layer_id,
                index = index,
                name = name,

                top = layer.top,
                left = layer.left,
                bottom = layer.bottom,
                right = layer.right,

                blend_mode = blend_mode,
                visible = visible,
                opacity = opacity,
            ))

    return root['layers']

def _get_mode(band_keys):
    for mode in ['RGBA', 'RGB']:
        if set(band_keys) == set(list(mode)):
            return mode

def _channels_data_to_PIL(channels_data, channel_types, size, depth):
    from PIL import Image
    if hasattr(Image, 'frombytes'):
        frombytes = Image.frombytes
    else:
        frombytes = Image.fromstring

    if size == (0, 0):
        return

    bands = {}
    if depth == 8:
        pil_depth = 'L'
    elif depth == 32:
        pil_depth = 'I'
    else:
        warnings.warn("Unsupported depth (%s)" % depth)
        return

    for channel, channel_type in zip(channels_data, channel_types):

        pil_band = ChannelID.to_PIL(channel_type)
        if pil_band is None:
            warnings.warn("Unsupported channel type (%d)" % channel_type)
            continue
        if channel.compression == Compression.RAW:
            bands[pil_band] = frombytes(pil_depth, size, channel.data, "raw", pil_depth)
        elif channel.compression == Compression.PACK_BITS:
            bands[pil_band] = frombytes(pil_depth, size, channel.data, "packbits", pil_depth)
        elif Compression.is_known(channel.compression):
            warnings.warn("Compression method is not implemented (%s)" % channel.compression)
        else:
            warnings.warn("Unknown compression method (%s)" % channel.compression)

    mode = _get_mode(bands.keys())
    return Image.merge(mode, [bands[band] for band in mode])


def layer_to_PIL(decoded_data, layer_index):
    layers = decoded_data.layer_and_mask_data.layers
    layer = layers.layer_records[layer_index]

    channels_data = layers.channel_image_data[layer_index]
    size = layer.width(), layer.height()
    channel_types = [info.id for info in layer.channels]
    depth = decoded_data.header.depth

    return _channels_data_to_PIL(channels_data, channel_types, size, depth)

def composite_image_to_PIL(decoded_data):
    header = decoded_data.header
    size = header.width, header.height

    if header.color_mode == ColorMode.RGB:
        if header.number_of_channels == 3:
            channel_types = [0, 1, 2]
        elif header.number_of_channels == 4:
            channel_types = [0, 1, 2, -1]
        else:
            warnings.warn("This number of channels (%d) is unsupported for this color mode (%s)" % (
                         header.number_of_channels, header.color_mode))
            return

    else:
        warnings.warn("Unsupported color mode (%s)" % header.color_mode)
        return

    return _channels_data_to_PIL(
        decoded_data.image_data,
        channel_types,
        size,
        header.depth
    )
