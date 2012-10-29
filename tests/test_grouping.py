# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from psd_tools.user_api.layers import group_layers
from .utils import decode_psd

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
