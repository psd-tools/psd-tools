# -*- coding: utf-8 -*-
from __future__ import absolute_import

import os

from psd_tools.user_api.psd_image import PSDImage, BBox
from psd_tools.constants import TaggedBlock
from .utils import decode_psd, DATA_PATH


def test_placed_layer():
    decoded = decode_psd('placedLayer.psd')
    layers = decoded.layer_and_mask_data.layers.layer_records
    place_linked1 = dict(layers[1].tagged_blocks).get(
        TaggedBlock.SMART_OBJECT_PLACED_LAYER_DATA)
    place_linked2 = dict(layers[2].tagged_blocks).get(
        TaggedBlock.SMART_OBJECT_PLACED_LAYER_DATA)
    place_embedded = dict(layers[3].tagged_blocks).get(
        TaggedBlock.PLACED_LAYER_DATA)
    assert place_linked1 is not None
    assert place_linked2 is not None
    assert place_embedded is not None


def test_userapi_no_placed_layers():
    img = PSDImage(decode_psd("1layer.psd"))
    layer = img.layers[0]
    assert not hasattr(layer, 'object_bbox')
    assert not hasattr(layer, 'placed_bbox')


def test_userapi_placed_layers():
    img = PSDImage(decode_psd("placedLayer.psd"))
    bg = img.layers[3]
    assert bg.kind == 'pixel'
    assert not hasattr(bg, 'object_bbox')
    assert not hasattr(bg, 'placed_bbox')

    layer0 = img.layers[0]
    assert layer0.kind == 'smartobject'
    assert layer0.object_bbox == BBox(0, 0, 64, 64)
    assert layer0.placed_bbox == BBox(x1=96.0, y1=96.0, x2=160.0, y2=160.0)

    layer1 = img.layers[1]
    assert layer1.kind == 'smartobject'
    assert layer1.object_bbox == BBox(0, 0, 101, 55)
    assert layer1.object_bbox.width == 101
    assert layer1.placed_bbox == BBox(x1=27.0, y1=73.0, x2=229.0, y2=183.0)

    layer2 = img.layers[2]
    assert layer2.kind == 'smartobject'
    assert layer2.object_bbox == BBox(0, 0, 64, 64)
    assert layer2.placed_bbox == BBox(x1=96.0, y1=96.0, x2=160.0, y2=160.0)


def test_embedded():
    # This file contains both an embedded and linked png
    psd = PSDImage.load(os.path.join(DATA_PATH, 'placedLayer.psd'))
    link = psd.smart_objects['5a96c404-ab9c-1177-97ef-96ca454b82b7']
    assert link.filename == 'linked-layer.png'
    with open(os.path.join(DATA_PATH, 'linked-layer.png'), 'rb') as f:
        assert link.data == f.read()
