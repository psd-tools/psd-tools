# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from psd_tools.constants import TaggedBlock
from .utils import decode_psd

def test_1layer_name():
    psd = decode_psd('1layer.psd')
    layers = psd.layer_and_mask_data.layers.layer_records
    assert len(layers) == 1

    layer = layers[0]
    assert len(layer.tagged_blocks) == 1

    block = layer.tagged_blocks[0]
    assert block.key == TaggedBlock.UNICODE_LAYER_NAME
    assert block.data == 'Фон'
