# -*- coding: utf-8 -*-
from __future__ import absolute_import

from psd_tools import PSDImage, BBox
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


def test_userapi_no_placed_layers():
    img = PSDImage(decode_psd("1layer.psd"))
    layer = img.layers[0]
    assert layer.placed_layer_size is None
    assert layer.transform_bbox is None


def test_userapi_placed_layers():
    img = PSDImage(decode_psd("placedLayer.psd"))
    bg = img.layers[3]
    assert bg.placed_layer_size is None
    assert bg.transform_bbox is None

    layer0 = img.layers[0]
    assert layer0.placed_layer_size == (64, 64)
    assert layer0.transform_bbox == BBox(x1=96.0, y1=96.0, x2=160.0, y2=160.0)

    layer1 = img.layers[1]
    assert layer1.placed_layer_size == (101, 55)
    assert layer1.placed_layer_size.width == 101
    assert layer1.transform_bbox == BBox(x1=27.0, y1=73.0, x2=229.0, y2=183.0)

    layer2 = img.layers[2]
    assert layer2.placed_layer_size == (64, 64)
    assert layer2.transform_bbox == BBox(x1=96.0, y1=96.0, x2=160.0, y2=160.0)
