# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from psd_tools.user_api.layers import group_layers
from tests.utils import decode_psd

def test_no_groups():
    layers = group_layers(decode_psd('2layers.psd'))
    assert len(layers) == 2
    assert not any('layers' in layer for layer in layers)

def test_groups_simple():
    layers = group_layers(decode_psd('group.psd'))
    assert len(layers) == 2

    group = layers[0]
    assert len(group['layers']) == 1
    assert group['name'] == 'Group 1'
    assert group['closed'] == False

    group_element = group['layers'][0]
    assert group_element['name'] == 'Shape 1'

def test_groups_without_opening():
    layers = group_layers(decode_psd('broken-groups.psd'))
    group1, group2 = layers
    assert group1['name'] == 'bebek'
    assert group2['name'] == 'anne'

    assert len(group1['layers']) == 1
    assert len(group2['layers']) == 1

    assert group1['layers'][0]['name'] == 'el sol'
    assert group2['layers'][0]['name'] == 'kas'


def test_group_visibility():
    layers = group_layers(decode_psd('hidden-groups.psd'))

    group2, group1, bg = layers
    assert group2['name'] == 'Group 2'
    assert group1['name'] == 'Group 1'
    assert bg['name'] == 'Background'

    assert bg['visible'] == True
    assert group2['visible'] == True
    assert group1['visible'] == False

    assert group2['layers'][0]['visible'] == True

    # The flag is 'visible=True', but this layer is hidden
    # because its group is not visible.
    assert group1['layers'][0]['visible'] == True


def test_layer_visibility():
    visible = dict(
        (layer['name'], layer['visible'])
        for layer in group_layers(decode_psd('hidden-layer.psd'))
    )
    assert visible['Shape 1']
    assert not visible['Shape 2']
    assert visible['Background']

def test_groups_32bit():
    layers = group_layers(decode_psd('32bit5x5.psd'))
    assert len(layers) == 3
    assert layers[0]['name'] == 'Background copy 2'

def test_group_with_empty_layer():
    layers = group_layers(decode_psd('empty-layer.psd'))
    group1, bg = layers
    assert group1['name'] == 'group'
    assert bg['name'] == 'Background'

def test_clipping():
    layers = group_layers(decode_psd('clipping-mask2.psd'))
    assert layers[0]['name'] == 'Group 1'
    layer = layers[0]['layers'][0]
    assert layer['name'] == 'Rounded Rectangle 4'
    assert layer['clip_layers'][0]['name'] == 'Color Balance 1'
    assert layers[1]['name'] == 'Rounded Rectangle 3'
    assert layers[1]['clip_layers'][0]['name'] == 'Brightness/Contrast 1'
    assert layers[2]['name'] == 'Polygon 1'
    assert layers[2]['clip_layers'][0]['name'] == 'Ellipse 1'
    assert layers[2]['clip_layers'][1]['name'] == 'Rounded Rectangle 2'
    assert layers[2]['clip_layers'][2]['name'] == 'Rounded Rectangle 1'
    assert layers[2]['clip_layers'][3]['name'] == 'Color Fill 1'
    assert layers[3]['name'] == 'Background'
