# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import pytest

from psd_tools.constants import BlendMode, TaggedBlock
from psd_tools.user_api.psd_image import PSDImage
from .utils import decode_psd, full_name


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


@pytest.mark.parametrize(
    ("layer_num", "effect_num", "param_name", "param_value"),
    EFFECTS_PARAMS
)
def test_layer_effect(layer_num, effect_num, param_name, param_value):
    effects_list = layer_records[layer_num].tagged_blocks[1].data.effects_list
    effect_info = effects_list[effect_num].effect_info
    assert effect_info.__getattribute__(param_name) == param_value


@pytest.mark.parametrize(
    ("layer_num", "effect_key", "param_name", "subparam_name", "param_value"),
    OBJECT_BASED_EFFECTS_PARAMS
)
def test_object_based_layer_effect(
    layer_num, effect_key, param_name, subparam_name, param_value
):
    effects_dict = dict(
        layer_records[layer_num].tagged_blocks[0].data.descriptor.items
    )
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
    assert tagged_blocks[TaggedBlock.BLEND_FILL_OPACITY] == 252
    setting = tagged_blocks[TaggedBlock.CHANNEL_BLENDING_RESTRICTIONS_SETTING]
    assert setting[0] is False
    assert setting[1] is False
    assert setting[2] is True


@pytest.fixture(scope='module')
def effects_psd():
    psd = PSDImage.load(full_name('layer_effects.psd'))
    yield psd


def test_effects_api(effects_psd):
    effect_kinds = [
        'DropShadow',
        'InnerShadow',
        'OuterGlow',
        'ColorOverlay',
        'GradientOverlay',
        'PatternOverlay',
        'Stroke',
        'InnerGlow',
        'BevelEmboss',
        'Satin',
    ]
    for layer in effects_psd.layers:
        assert layer.has_effects()
        assert len(layer.effects) == 1


def test_coloroverlay(effects_psd):
    layer = effects_psd.layers[5]
    assert layer.effects.has('coloroverlay')
    effect = list(layer.effects.find('coloroverlay'))[0]
    assert effect.name.lower() == 'coloroverlay'
    assert effect.blend_mode == 'normal'
    assert effect.color
    assert effect.opacity.value == 100.0


def test_patternoverlay(effects_psd):
    layer = effects_psd.layers[2]
    assert layer.effects.has('patternoverlay')
    effect = list(layer.effects.find('patternoverlay'))[0]
    assert effect.name.lower() == 'patternoverlay'
    assert effect.aligned is True
    assert effect.blend_mode == 'normal'
    assert effect.opacity.value == 100.0
    assert effect.pattern
    assert effect.phase
    assert effect.scale.value == 100.0


def test_gradientoverlay(effects_psd):
    layer = effects_psd.layers[3]
    assert layer.effects.has('gradientoverlay')
    effect = list(layer.effects.find('gradientoverlay'))[0]
    assert effect.name.lower() == 'gradientoverlay'
    assert effect.aligned is True
    assert effect.angle.value == 87.0
    assert effect.blend_mode == 'normal'
    assert effect.dithered is False
    assert effect.gradient
    assert effect.offset
    assert effect.opacity.value == 100.0
    assert effect.reversed is False
    assert effect.scale.value == 100.0
    assert effect.type == 'linear'


def test_satin(effects_psd):
    layer = effects_psd.layers[0]
    assert layer.effects.has('satin')
    effect = list(layer.effects.find('satin'))[0]
    assert effect.name.lower() == 'satin'
    assert effect.angle.value == -60.0
    assert effect.anti_aliased is True
    assert effect.blend_mode == 'multiply'
    assert effect.color
    assert effect.contour
    assert effect.distance.value == 20.0
    assert effect.inverted is True
    assert effect.opacity.value == 50.0
    assert effect.size.value == 35.0


def test_stroke(effects_psd):
    layer = effects_psd.layers[1]
    assert layer.effects.has('stroke')
    effect = list(layer.effects.find('stroke'))[0]
    assert effect.name.lower() == 'stroke'
    assert effect.blend_mode == 'normal'
    assert effect.fill.name.lower() == 'coloroverlay'
    assert effect.fill_type == 'solid-color'
    assert effect.opacity.value == 100.0
    assert effect.overprint is False
    assert effect.position == 'outer'
    assert effect.size.value == 6.0
    assert effect.color
    assert effect.gradient is None
    assert effect.pattern is None


def test_dropshadow(effects_psd):
    layer = effects_psd.layers[4]
    assert layer.effects.has('dropshadow')
    effect = list(layer.effects.find('dropshadow'))[0]
    assert effect.name.lower() == 'dropshadow'
    assert effect.angle.value == 90.0
    assert effect.anti_aliased is False
    assert effect.blend_mode == 'multiply'
    assert effect.choke.value == 0.0
    assert effect.color
    assert effect.contour
    assert effect.layer_knocks_out is True
    assert effect.distance.value == 18.0
    assert effect.noise.value == 0.0
    assert effect.opacity.value == 35.0
    assert effect.size.value == 41.0
    assert effect.use_global_light is True


def test_innershadow(effects_psd):
    layer = effects_psd.layers[6]
    assert layer.effects.has('innershadow')
    effect = list(layer.effects.find('innershadow'))[0]
    assert effect.name.lower() == 'innershadow'
    assert effect.angle.value == 90.0
    assert effect.anti_aliased is False
    assert effect.blend_mode == 'multiply'
    assert effect.choke.value == 0.0
    assert effect.color
    assert effect.contour
    assert effect.distance.value == 18.0
    assert effect.noise.value == 0.0
    assert effect.opacity.value == 35.0
    assert effect.size.value == 41.0
    assert effect.use_global_light is True


def test_innerglow(effects_psd):
    layer = effects_psd.layers[7]
    assert layer.effects.has('innerglow')
    effect = list(layer.effects.find('innerglow'))[0]
    assert effect.name.lower() == 'innerglow'
    assert effect.anti_aliased is False
    assert effect.blend_mode == 'screen'
    assert effect.choke.value == 0.0
    assert effect.color
    assert effect.contour
    assert effect.glow_source == 'edge'
    assert effect.glow_type == 'softer'
    assert effect.noise.value == 0.0
    assert effect.opacity.value == 46.0
    assert effect.quality_jitter.value == 0.0
    assert effect.quality_range.value == 50.0
    assert effect.size.value == 18.0
    assert effect.gradient is None


def test_outerglow(effects_psd):
    layer = effects_psd.layers[8]
    assert layer.effects.has('outerglow')
    effect = list(layer.effects.find('outerglow'))[0]
    assert effect.name.lower() == 'outerglow'
    assert effect.anti_aliased is False
    assert effect.blend_mode == 'screen'
    assert effect.choke.value == 0.0
    assert effect.color
    assert effect.contour
    assert effect.glow_type == 'softer'
    assert effect.noise.value == 0.0
    assert effect.opacity.value == 35.0
    assert effect.quality_jitter.value == 0.0
    assert effect.quality_range.value == 50.0
    assert effect.size.value == 41.0
    assert effect.spread.value == 0.0
    assert effect.gradient is None


def test_emboss(effects_psd):
    layer = effects_psd.layers[9]
    assert layer.effects.has('bevelemboss')
    effect = list(layer.effects.find('bevelemboss'))[0]
    assert effect.name.lower() == 'bevelemboss'
    assert effect.altitude.value == 30.0
    assert effect.angle.value == 90.0
    assert effect.anti_aliased is False
    assert effect.bevel_style == 'emboss'
    assert effect.bevel_type == 'smooth'
    assert effect.blend_mode == 'normal'
    assert effect.contour
    assert effect.depth.value == 100.0
    assert effect.direction == 'up'
    assert effect.enabled is True
    assert effect.highlight_color
    assert effect.highlight_mode == 'screen'
    assert effect.highlight_opacity.value == 50.0
    assert effect.shadow_color
    assert effect.shadow_mode == 'multiply'
    assert effect.shadow_opacity.value == 50.0
    assert effect.size.value == 41.0
    assert effect.soften.value == 0.0
    assert effect.use_global_light is True
    assert effect.use_shape is False
    assert effect.use_texture is False


def test_bevel(effects_psd):
    layer = effects_psd.layers[10]
    assert layer.effects.has('bevelemboss')
    effect = list(layer.effects.find('bevelemboss'))[0]
    assert effect.name.lower() == 'bevelemboss'
    assert effect.altitude.value == 30.0
    assert effect.angle.value == 90.0
    assert effect.anti_aliased is False
    assert effect.bevel_style == 'inner-bevel'
    assert effect.bevel_type == 'smooth'
    assert effect.blend_mode == 'normal'
    assert effect.contour
    assert effect.depth.value == 100.0
    assert effect.direction == 'up'
    assert effect.enabled is True
    assert effect.highlight_color
    assert effect.highlight_mode == 'screen'
    assert effect.highlight_opacity.value == 50.0
    assert effect.shadow_color
    assert effect.shadow_mode == 'multiply'
    assert effect.shadow_opacity.value == 50.0
    assert effect.size.value == 41.0
    assert effect.soften.value == 0.0
    assert effect.use_global_light is True
    assert effect.use_shape is False
    assert effect.use_texture is False


def test_gradient_descriptor():
    psd = PSDImage.load(full_name('effect-stroke-gradient.psd'))
    assert psd.layers[0].effects[0].gradient.type == b'ClNs'
    assert psd.layers[1].effects[0].gradient.type == b'CstS'
