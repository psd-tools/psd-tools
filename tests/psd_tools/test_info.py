# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import re
import pytest

from psd_tools import PSDImage
from psd_tools.constants import TaggedBlock, SectionDivider
from psd_tools.decoder.tagged_blocks import VectorMaskSetting
from psd_tools.user_api.effects import PatternOverlay
from .utils import load_psd, decode_psd, with_psb


FILES_WITH_NO_LAYERS = (
    ('0layers.psd',         False),
    ('0layers_tblocks.psd', True),
    ('16bit5x5.psd',        True),
    ('32bit.psd',           True),
    ('32bit5x5.psd',        True),
    ('300dpi.psd',          True),
    ('gradient-fill.psd',   True),
    ('history.psd',         True),
    ('pen-text.psd',        True),
    ('transparentbg.psd',   True),
    ('vector-mask.psd',     True),
    ('0layers.psb',         True),
    ('0layers_tblocks.psb', True),
    ('16bit5x5.psb',        True),
    ('32bit.psb',           True),
    ('32bit5x5.psb',        True),
    ('300dpi.psb',          True),
    ('gradient-fill.psb',   True),
    ('history.psb',         True),
    ('pen-text.psb',        True),
    ('transparentbg.psb',   True),
    ('vector-mask.psb',     True)
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
    assert len(layers) == 3 + 1  # 3 layers + 1 divider

    assert (
        layers[1].tagged_blocks[3].key == TaggedBlock.SECTION_DIVIDER_SETTING
    )
    assert (
        layers[1].tagged_blocks[3].data.type ==
        SectionDivider.BOUNDING_SECTION_DIVIDER
    )


@pytest.mark.parametrize(
    ('filename', 'has_layer_and_mask_data'),
    FILES_WITH_NO_LAYERS
)
def test_no_layers_has_tagged_blocks(filename, has_layer_and_mask_data):
    psd = load_psd(filename)

    assert psd.layer_and_mask_data is not None

    layers = psd.layer_and_mask_data.layers
    assert layers.layer_count == 0
    assert len(layers.layer_records) == 0
    assert len(layers.channel_image_data) == 0

    tagged_blocks = psd.layer_and_mask_data.tagged_blocks
    assert (len(tagged_blocks) != 0) == has_layer_and_mask_data


def test_patterns():
    psd = decode_psd('patterns.psd')
    tagged_blocks = dict(psd.layer_and_mask_data.tagged_blocks)
    assert b'Patt' in tagged_blocks
    assert len(tagged_blocks[b'Patt']) == 6


def test_layer_properties():
    psd = PSDImage(decode_psd('clipping-mask2.psd'))
    assert psd.width
    assert psd.height
    assert psd.channels
    assert psd.viewbox
    for layer in psd.descendants():
        assert layer.bbox


def test_api():
    image = PSDImage(decode_psd('1layer.psd'))
    assert len(image.layers) == 1

    layer = image.layers[0]
    assert layer.name == 'Фон'
    assert layer.bbox == (0, 0, 101, 55)
    assert layer.left == 0
    assert layer.right == 101
    assert layer.top == 0
    assert layer.bottom == 55
    assert layer.visible
    assert layer.opacity == 255
    assert layer.blend_mode == 'normal'


def test_vector_mask():
    psd = decode_psd('vector-mask.psd')
    layers = psd.layer_and_mask_data.layers.layer_records
    assert layers[1].tagged_blocks[1].key == TaggedBlock.VECTOR_MASK_SETTING1
    assert isinstance(layers[1].tagged_blocks[1].data, VectorMaskSetting)


def test_shape_paths():
    psd = PSDImage(decode_psd('gray1.psd'))
    assert psd.layers[1].has_vector_mask()
    vector_mask = psd.layers[1].vector_mask
    assert not vector_mask.invert
    assert not vector_mask.disabled
    assert not vector_mask.not_link
    assert len(vector_mask.paths) == 2
    path = vector_mask.paths[0]
    assert len(path.knots) == path.num_knots
    assert path.closed
    path = vector_mask.paths[1]
    assert len(path.knots) == path.num_knots
    assert path.closed


@pytest.fixture(scope='module')
def stroke_psd():
    psd = PSDImage(decode_psd('stroke.psd'))
    yield psd


def test_vector_stroke_content_setting(stroke_psd):
    assert stroke_psd.layers[1].kind == 'shape'
    assert isinstance(stroke_psd.layers[1].stroke_content, PatternOverlay)


def test_vector_origination(stroke_psd):
    assert stroke_psd.layers[0].has_origination
    origination = stroke_psd.layers[0].origination
    assert origination.origin_type == 4
    assert origination.resolution == 150.0
    assert origination.shape_bbox == (187.0, 146.0, 220.0, 206.0)
    assert origination.line_end.x == 220.0
    assert origination.line_end.y == 146.0
    assert origination.line_start.x == 187.0
    assert origination.line_start.y == 206.0
    assert origination.line_weight == 1.0
    assert origination.arrow_start is False
    assert origination.arrow_end is False
    assert origination.arrow_width == 0.0
    assert origination.arrow_length == 0.0
    assert origination.arrow_conc == 0
    assert origination.index == 0


def test_print():
    psd = PSDImage(decode_psd('empty-layer.psd'))
    psd.print_tree()
