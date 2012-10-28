# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, print_function
import warnings

from psd_tools.constants import (Compression, ChannelID, ColorMode,
                                 TaggedBlock, SectionDivider)

def make_layers(raw_data):
    layer_records = raw_data.layer_and_mask_data.layers.layer_records

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

        if divider is not None:
            # group information
            if divider.type in [SectionDivider.CLOSED_FOLDER, SectionDivider.OPEN_FOLDER]:
                # group begins
                group = dict(
                    id = layer_id,
                    name = name,
                    layers = [],
                    closed = divider.type == SectionDivider.CLOSED_FOLDER,
                    blend_mode = layer.blend_mode,
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
            image = layer_to_PIL(raw_data, index)
            current_group['layers'].append(dict(
                id = layer_id,
                name = name,
                image = image,

                top = layer.top,
                left = layer.left,
                bottom = layer.bottom,
                right = layer.right,

                blend_mode = layer.blend_mode,
                visible = visible,
                opacity = opacity,
            ))

    return root['layers']


def _get_mode(band_keys):
    for mode in ['RGBA', 'RGB']:
        if set(band_keys) == set(list(mode)):
            return mode

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

    mode = _get_mode(bands.keys())
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
