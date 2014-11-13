# -*- coding: utf-8 -*-
from __future__ import absolute_import
from psd_tools.constants import TaggedBlock
from .utils import decode_psd

def test_placed_layer():
    decoded = decode_psd('placedLayer.psd')
    layers = decoded.layer_and_mask_data.layers.layer_records
    place_linked1 = dict(layers[1].tagged_blocks).get(TaggedBlock.SMART_OBJECT_PLACED_LAYER_DATA)
    place_linked2 = dict(layers[2].tagged_blocks).get(TaggedBlock.SMART_OBJECT_PLACED_LAYER_DATA)
    place_embedded = dict(layers[3].tagged_blocks).get(TaggedBlock.PLACED_LAYER_DATA)
    assert place_linked1 is not None
    assert place_linked2 is not None
    assert place_embedded is not None