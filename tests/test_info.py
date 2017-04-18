# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import re
import pytest

from psd_tools import PSDImage
from psd_tools.constants import TaggedBlock, SectionDivider, BlendMode
from .utils import load_psd, decode_psd
from psd_tools.decoder.tagged_blocks import VectorMaskSetting


FILES_WITH_NO_LAYERS = (
    ('0layers.psd',         False),
    ('0layers_tblocks.psd', True),
    ('16bit5x5.psd',        True),
    ('32bit.psd',           True),
    ('32bit5x5.psd',        True),
    ('300dpi.psd',          True),
    ('gradient fill.psd',   True),
    ('history.psd',         True),
    ('pen-text.psd',        True),
    ('transparentbg.psd',   True),
    ('vector mask.psd',     True)
)


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


def test_fakeroot_layer_repr():
    img = PSDImage(decode_psd('1layer.psd'))
    fakeroot = img.layers[0].parent
    assert re.match(r"<psd_tools.Group: u?'_RootGroup', layer_count=1>", repr(fakeroot)), repr(fakeroot)


@pytest.mark.parametrize(('filename', 'has_layer_and_mask_data'), FILES_WITH_NO_LAYERS)
def test_no_layers_has_tagged_blocks(filename, has_layer_and_mask_data):
    psd = load_psd(filename)

    assert psd.layer_and_mask_data is not None

    layers = psd.layer_and_mask_data.layers
    assert layers.layer_count == 0
    assert len(layers.layer_records) == 0
    assert len(layers.channel_image_data) == 0

    tagged_blocks = psd.layer_and_mask_data.tagged_blocks
    assert (len(tagged_blocks) != 0) == has_layer_and_mask_data


def text_vector_mask():
    psd = decode_psd('vector mask.psd')
    layers = psd.layer_and_mask_data.layers.layer_records
    assert layers[1].tagged_blocks[1].key == b'vmsk'
    assert isinstance(layers[1].tagged_blocks[1].data, VectorMaskSetting)
