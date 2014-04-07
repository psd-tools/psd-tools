# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import pytest

from .utils import decode_psd
from psd_tools.constants import BlendMode


psd = decode_psd('layer_params.psd')
layer_records = psd.layer_and_mask_data.layers.layer_records

EFFECTS_COUNT = (
    (1, 7),
    (2, 7)
)

CHECK_LIST = (
    (1, 1, 'enabled',  True),
    (1, 2, 'enabled',  False),
    (1, 3, 'enabled',  False),
    (1, 4, 'enabled',  False),
    (1, 5, 'enabled',  True),
    (1, 6, 'enabled',  False),

    (2, 1, 'enabled',  True),
    (2, 2, 'enabled',  False),
    (2, 3, 'enabled',  True),
    (2, 4, 'enabled',  False),
    (2, 5, 'enabled',  False),
    (2, 6, 'enabled',  False),

    (1, 1, 'distance', 65536 * 5),
    (2, 1, 'distance', 65536 * 30),

    (1, 3, 'blend_mode', BlendMode.SCREEN),
    (2, 3, 'blend_mode', BlendMode.HARD_LIGHT),
    (1, 3, 'blur', 65536 * 5),
    (2, 3, 'blur', 65536 * 40),

    (1, 5, 'bevel_style', 4),
    (2, 5, 'bevel_style', 2)
)


@pytest.mark.parametrize(("layer_num", "count"), EFFECTS_COUNT)
def test_layer_effects_count(layer_num, count):
    effects_info = layer_records[layer_num].tagged_blocks[1].data
    assert effects_info.effects_count == count


@pytest.mark.parametrize(("layer_num", "effect_num", "param_name", "param_value"), CHECK_LIST)
def test_layer_effect_enabled(layer_num, effect_num, param_name, param_value):
    effects_list = layer_records[layer_num].tagged_blocks[1].data.effects_list
    effect_info = effects_list[effect_num].effect_info
    assert effect_info.__getattribute__(param_name) == param_value
