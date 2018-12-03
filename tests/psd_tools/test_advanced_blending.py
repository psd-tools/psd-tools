# -*- coding: utf-8 -*-
from __future__ import absolute_import

import os

from psd_tools import PSDImage
from psd_tools.constants import TaggedBlock
from psd_tools.decoder.actions import Descriptor
from psd_tools.decoder.tagged_blocks import ArtboardData
from PIL import Image
from .utils import decode_psd, DATA_PATH


def test_advanced_blending():
    decoded = decode_psd('advanced-blending.psd')
    layer_records = decoded.layer_and_mask_data.layers.layer_records
    tagged_blocks = dict(layer_records[1].tagged_blocks)
    assert not tagged_blocks.get(TaggedBlock.BLEND_CLIPPING_ELEMENTS)
    assert tagged_blocks.get(TaggedBlock.BLEND_INTERIOR_ELEMENTS)
    tagged_blocks = dict(layer_records[3].tagged_blocks)
    assert isinstance(tagged_blocks.get(TaggedBlock.ARTBOARD_DATA1),
                      ArtboardData)


def test_blend_and_clipping():
    psd = PSDImage(decode_psd('blend-and-clipping.psd'))
    for layer in psd.layers:
        assert isinstance(layer.as_PIL(), Image.Image)
