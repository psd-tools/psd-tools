# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from psd_tools import PSDImage
from psd_tools.constants import TaggedBlock, SectionDivider, BlendMode
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

def test_groups():
    psd = decode_psd('group.psd')
    layers = psd.layer_and_mask_data.layers.layer_records
    assert len(layers) == 3+1 # 3 layers + 1 divider

    assert layers[1].tagged_blocks[3].key == TaggedBlock.SECTION_DIVIDER_SETTING
    assert layers[1].tagged_blocks[3].data.type == SectionDivider.BOUNDING_SECTION_DIVIDER

def test_api():
    image = PSDImage(decode_psd('1layer.psd'))
    assert len(image.layers) == 1

    layer = image.layers[0]
    assert layer.name == 'Фон'
    assert layer.bbox == (0, 0, 101, 55)
    assert layer.visible
    assert layer.opacity == 255
    assert layer.blend_mode == BlendMode.NORMAL

