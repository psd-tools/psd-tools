# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from psd_tools.user_api.psd_image import PSDImage
from .utils import decode_psd, full_name


def test_no_groups():
    psd = PSDImage(decode_psd('2layers.psd'))
    assert len(psd.layers) == 2
    assert not any(layer.kind == "group" for layer in psd.layers)


def test_groups_simple():
    psd = PSDImage(decode_psd('group.psd'))
    assert len(psd.layers) == 2

    group = psd.layers[0]
    assert group.kind == "group"
    assert len(group.layers) == 1
    assert group.name == 'Group 1'
    assert group.closed is False

    group_element = group.layers[0]
    assert group_element.name == 'Shape 1'


def test_groups_without_opening():
    psd = PSDImage(decode_psd('broken-groups.psd'))
    group1, group2 = psd.layers
    assert group1.name == 'bebek'
    assert group2.name == 'anne'

    assert len(group1.layers) == 1
    assert len(group2.layers) == 1

    assert group1.layers[0].name == 'el sol'
    assert group2.layers[0].name == 'kas'


def test_group_visibility():
    psd = PSDImage(decode_psd('hidden-groups.psd'))

    group2, group1, bg = psd.layers
    assert group2.name == 'Group 2'
    assert group1.name == 'Group 1'
    assert bg.name == 'Background'

    assert bg.visible is True
    assert group2.visible is True
    assert group1.visible is False

    assert group2.layers[0].visible is True

    # The flag is 'visible=True', but this layer is hidden
    # because its group is not visible.
    assert group1.layers[0].visible is True


def test_layer_visibility():
    visible = dict(
        (layer.name, layer.visible)
        for layer in PSDImage(decode_psd('hidden-layer.psd')).layers
    )
    assert visible['Shape 1']
    assert not visible['Shape 2']
    assert visible['Background']


def test_groups_32bit():
    psd = PSDImage(decode_psd('32bit5x5.psd'))
    assert len(psd.layers) == 3
    assert psd.layers[0].name == 'Background copy 2'


def test_group_with_empty_layer():
    psd = PSDImage(decode_psd('empty-layer.psd'))
    group1, bg = psd.layers
    assert group1.name == 'group'
    assert bg.name == 'Background'


def test_clipping():
    psd = PSDImage(decode_psd('clipping-mask2.psd'))
    assert psd.layers[0].name == 'Group 1'
    layer = psd.layers[0].layers[0]
    assert layer.name == 'Rounded Rectangle 4'
    assert layer.has_clip_layers()
    assert layer.clip_layers[0].name == 'Color Balance 1'
    assert psd.layers[1].name == 'Rounded Rectangle 3'
    assert psd.layers[1].clip_layers[0].name == 'Brightness/Contrast 1'
    assert psd.layers[2].name == 'Polygon 1'
    assert psd.layers[2].clip_layers[0].name == 'Ellipse 1'
    assert psd.layers[2].clip_layers[1].name == 'Rounded Rectangle 2'
    assert psd.layers[2].clip_layers[2].name == 'Rounded Rectangle 1'
    assert psd.layers[2].clip_layers[3].name == 'Color Fill 1'
    assert psd.layers[3].name == 'Background'


def test_generator():
    psd = PSDImage.load(full_name('hidden-groups.psd'))
    assert len([True for layer in psd.layers]) == 3
    assert len([True for layer in psd.descendants()]) == 5


def test_generator_with_clip_layers():
    psd = PSDImage.load(full_name('clipping-mask.psd'))
    assert not psd.layers[0].has_clip_layers()
    assert len([True for layer in psd.layers]) == 2
    assert len([True for layer in psd.descendants()]) == 7
    assert len([True for layer in psd.descendants(include_clip=False)]) == 6
