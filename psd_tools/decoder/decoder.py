# -*- coding: utf-8 -*-
from __future__ import absolute_import

from . import image_resources, tagged_blocks

def parse(reader_parse_result):

    layers = reader_parse_result.layer_and_mask_data.layers

    new_layers = layers._replace(layer_records = [
        rec._replace(
            tagged_blocks = tagged_blocks.decode(rec.tagged_blocks)
        )
        for rec in layers.layer_records
    ])

    new_layer_and_mask_data = reader_parse_result.layer_and_mask_data._replace(layers=new_layers)

    reader_parse_result = reader_parse_result._replace(
        image_resource_blocks = image_resources.decode(reader_parse_result.image_resource_blocks),
        layer_and_mask_data = new_layer_and_mask_data,
    )

    return reader_parse_result
