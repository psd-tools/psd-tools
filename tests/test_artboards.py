# -*- coding: utf-8 -*-
from __future__ import absolute_import
from .utils import decode_psd


def test_artboards():
    decoded = decode_psd('single_artboard.psd')
    layers = decoded.layer_and_mask_data.layers.layer_records

    artboard_layers = []
    for layer in layers:
        for block in layer.tagged_blocks:
            if block.key in (b'artb', b'artd', b'abdd'):
                artboard_layers.append(layer)

    assert len(artboard_layers) == 1

    artboard_layer = artboard_layers[0]
    tagged_blocks = dict(artboard_layer.tagged_blocks)
    artboard = tagged_blocks[b'artb']

    assert artboard.version == 16
    assert artboard.data.classID == b'artboard'

    items = dict(artboard.data.items)
    rect = dict(items[b'artboardRect'].items)

    assert rect[b'Btom'].value == 1061.0
    assert rect[b'Left'].value == 238.0
    assert rect[b'Rght'].value == 1154.0
    assert rect[b'Top '].value == 77.0

