# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import pytest

from .utils import decode_psd, full_name
from psd_tools.constants import BlendMode
from psd_tools.user_api.psd_image import PSDImage


psd = decode_psd('layer_params.psd')
layer_records = psd.layer_and_mask_data.layers.layer_records

EFFECTS_COUNT = (
    (1, 7),
    (2, 7)
)

EFFECTS_PARAMS = (
    (1, 1, 'enabled', True),
    (1, 2, 'enabled', False),
    (1, 3, 'enabled', False),
    (1, 4, 'enabled', False),
    (1, 5, 'enabled', True),
    (1, 6, 'enabled', False),

    (2, 1, 'enabled', True),
    (2, 2, 'enabled', False),
    (2, 3, 'enabled', True),
    (2, 4, 'enabled', False),
    (2, 5, 'enabled', False),
    (2, 6, 'enabled', False),

    (1, 1, 'distance', 65536 * 5),
    (2, 1, 'distance', 65536 * 30),

    (1, 3, 'blend_mode', BlendMode.SCREEN),
    (2, 3, 'blend_mode', BlendMode.HARD_LIGHT),
    (1, 3, 'blur', 65536 * 5),
    (2, 3, 'blur', 65536 * 40),

    (1, 5, 'bevel_style', 4),
    (2, 5, 'bevel_style', 2)
)

OBJECT_BASED_EFFECTS_PARAMS = (
    (1, b'DrSh', b'Md  ', None, b'Nrml'),
    (1, b'DrSh', b'Dstn', None, 5.0),
    (1, b'DrSh', b'Ckmt', None, 0.0),
    (1, b'DrSh', b'blur', None, 5.0),
    (1, b'DrSh', b'TrnS', b'Nm  ', '$$$/Contours/Defaults/Gaussian=Gaussian'),

    (1, b'ebbl', b'bvlS', None, b'PlEb'),
    (1, b'ebbl', b'hglM', None, b'Scrn'),
    (1, b'ebbl', b'useShape', None, False),
    (1, b'ebbl', b'useTexture', None, False),

    (1, b'FrFX', b'Sz  ', None, 4.0),
    (1, b'FrFX', b'PntT', None, b'GrFl'),
    (1, b'FrFX', b'Type', None, b'Rdl '),
    (1, b'FrFX', b'Algn', None, False),
    (1, b'FrFX', b'Scl ', None, 93.0),


    (2, b'DrSh', b'Md  ', None, b'Nrml'),
    (2, b'DrSh', b'Dstn', None, 30.0),
    (2, b'DrSh', b'Ckmt', None, 50.0),
    (2, b'DrSh', b'blur', None, 5.0),
    (2, b'DrSh', b'TrnS', b'Nm  ', 'Линейный'),

    (2, b'OrGl', b'Md  ', None, b'HrdL'),
    (2, b'OrGl', b'blur', None, 40.0),
    (2, b'OrGl', b'TrnS', b'Nm  ', 'Заказная'),
    (2, b'OrGl', b'AntA', None, True),
    (2, b'OrGl', b'Inpr', None, 43.0)
)


@pytest.mark.parametrize(("layer_num", "count"), EFFECTS_COUNT)
def test_layer_effects_count(layer_num, count):
    effects_info = layer_records[layer_num].tagged_blocks[1].data
    assert effects_info.effects_count == count


@pytest.mark.parametrize(("layer_num", "effect_num", "param_name", "param_value"), EFFECTS_PARAMS)
def test_layer_effect(layer_num, effect_num, param_name, param_value):
    effects_list = layer_records[layer_num].tagged_blocks[1].data.effects_list
    effect_info = effects_list[effect_num].effect_info
    assert effect_info.__getattribute__(param_name) == param_value


@pytest.mark.parametrize(("layer_num", "effect_key", "param_name", "subparam_name", "param_value"), OBJECT_BASED_EFFECTS_PARAMS)
def test_object_based_layer_effect(layer_num, effect_key, param_name, subparam_name, param_value):
    effects_dict = dict(layer_records[layer_num].tagged_blocks[0].data.descriptor.items)
    effect_info = dict(effects_dict[effect_key].items)

    if subparam_name is None:
        assert effect_info[param_name].value == param_value
    else:
        effect_info = dict(effect_info[param_name].items)
        assert effect_info[subparam_name].value == param_value


def test_iopa_brst_block():
    decoded_data = decode_psd('layer_effects.psd')
    layer_records = decoded_data.layer_and_mask_data.layers.layer_records
    tagged_blocks = dict(layer_records[4].tagged_blocks)
    assert tagged_blocks[b'iOpa'] == 252
    assert tagged_blocks[b'brst'][0] == False
    assert tagged_blocks[b'brst'][1] == False
    assert tagged_blocks[b'brst'][2] == True


def test_effects_api():
    psd = PSDImage.load(full_name('layer_effects.psd'))
    for layer in psd.layers:
        assert len(layer.effects) > 0
