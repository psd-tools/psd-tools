# -*- coding: utf-8 -*-
from __future__ import absolute_import

from . import image_resources, tagged_blocks, color
import io
from psd_tools.constants import TaggedBlock

def parse(reader_parse_result):
    image_resource_blocks = reader_parse_result.image_resource_blocks
    image_resource_blocks = image_resources.decode(image_resource_blocks)

    layer_and_mask_data = reader_parse_result.layer_and_mask_data
    _layers = decode_layers(layer_and_mask_data.layers)
    _global_mask_info = decode_global_mask_info(layer_and_mask_data.global_mask_info)
    _tagged_blocks = tagged_blocks.decode(layer_and_mask_data.tagged_blocks)

    # 16 and 32 bit layers are stored in Lr16 and Lr32 tagged blocks
    if _layers.layer_count == 0:
        blocks_dict = dict(_tagged_blocks)
        if reader_parse_result.header.depth == 16:
            _layers = blocks_dict.get(TaggedBlock.LAYER_16, _layers)
        elif reader_parse_result.header.depth == 32:
            _layers = blocks_dict.get(TaggedBlock.LAYER_32, _layers)

    # XXX: this code is complicated because of the namedtuple abuse
    layer_and_mask_data = layer_and_mask_data._replace(
        layers = _layers,
        global_mask_info = _global_mask_info,
        tagged_blocks = _tagged_blocks
    )

    reader_parse_result = reader_parse_result._replace(
        image_resource_blocks = image_resource_blocks,
        layer_and_mask_data = layer_and_mask_data
    )

    return reader_parse_result

def decode_layers(layers):
    if layers.layer_count == 0:
        return layers

    _layer_records = [
        record._replace(
            tagged_blocks = tagged_blocks.decode(record.tagged_blocks)
        ) for record in layers.layer_records
    ]
    return layers._replace(layer_records = _layer_records)

def decode_global_mask_info(global_mask_info):
    if global_mask_info is None:
        return None

    fp = io.BytesIO(global_mask_info.overlay_color)
    global_mask_info = global_mask_info._replace(
        overlay_color = color.decode_color(fp)
    )

    return global_mask_info
