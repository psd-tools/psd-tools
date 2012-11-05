# -*- coding: utf-8 -*-
from __future__ import absolute_import

from . import image_resources, tagged_blocks
from psd_tools.constants import TaggedBlock

def parse(reader_parse_result):

    layer_and_mask_data = reader_parse_result.layer_and_mask_data
    layers = layer_and_mask_data.layers

    new_layers = decode_layers(layers)
    new_tagged_blocks = tagged_blocks.decode(layer_and_mask_data.tagged_blocks)

    # 16 and 32 bit layers are stored in Lr16 and Lr32 tagged blocks
    if new_layers.layer_count == 0:
        blocks_dict = dict(new_tagged_blocks)
        if reader_parse_result.header.depth == 16:
            new_layers = blocks_dict.get(TaggedBlock.LAYER_16, new_layers)
        elif reader_parse_result.header.depth == 32:
            new_layers = blocks_dict.get(TaggedBlock.LAYER_32, new_layers)

    # XXX: this code is complicated because of the namedtuple abuse
    new_layer_and_mask_data = layer_and_mask_data._replace(
        layers = new_layers,
        tagged_blocks = new_tagged_blocks
    )

    reader_parse_result = reader_parse_result._replace(
        image_resource_blocks = image_resources.decode(reader_parse_result.image_resource_blocks),
        layer_and_mask_data = new_layer_and_mask_data,
    )

    return reader_parse_result

def decode_layers(layers):
    new_layer_records = [
        rec._replace(
            tagged_blocks = tagged_blocks.decode(rec.tagged_blocks)
        ) for rec in layers.layer_records
    ]
    return layers._replace(layer_records = new_layer_records)
