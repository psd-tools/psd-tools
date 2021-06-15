from __future__ import absolute_import, unicode_literals

import logging

import pytest

from psd_tools.api.psd_image import PSDImage
from ..utils import full_name

logger = logging.getLogger(__name__)


LAYER_EFFECTS = PSDImage.open(full_name('layer_effects.psd'))


@pytest.fixture
def fixture():
    yield LAYER_EFFECTS


def test_effects(fixture):
    assert isinstance(fixture[0].effects.scale, float)
    assert fixture[0].effects.enabled is True
    for effect in fixture[0].effects:
        assert effect.enabled is True


def test_bevel(fixture):
    effect = fixture[1].effects[0]
    assert not hasattr(effect, 'blend_mode')
    assert effect.altitude == 30.0
    assert effect.angle == 90.0
    assert effect.anti_aliased is False
    assert effect.bevel_style == 'inner'
    assert effect.bevel_type == 'smooth'
    assert effect.contour
    assert effect.depth == 100.0
    assert effect.direction == 'in'
    assert effect.enabled is True
    assert effect.highlight_color
    assert effect.highlight_mode == 'screen'
    assert effect.highlight_opacity == 50.0
    assert effect.shadow_color
    assert effect.shadow_mode == 'multiply'
    assert effect.shadow_opacity == 50.0
    assert effect.size == 41.0
    assert effect.soften == 0.0
    assert effect.use_global_light is True
    assert effect.use_shape is False
    assert effect.use_texture is False


def test_emboss(fixture):
    effect = fixture[2].effects[0]
    assert not hasattr(effect, 'blend_mode')
    assert effect.altitude == 30.0
    assert effect.angle == 90.0
    assert effect.anti_aliased is False
    assert effect.bevel_style == 'emboss'
    assert effect.bevel_type == 'smooth'
    assert effect.contour
    assert effect.depth == 100.0
    assert effect.direction == 'in'
    assert effect.enabled is True
    assert effect.highlight_color
    assert effect.highlight_mode == 'screen'
    assert effect.highlight_opacity == 50.0
    assert effect.shadow_color
    assert effect.shadow_mode == 'multiply'
    assert effect.shadow_opacity == 50.0
    assert effect.size == 41.0
    assert effect.soften == 0.0
    assert effect.use_global_light is True
    assert effect.use_shape is False
    assert effect.use_texture is False


def test_outer_glow(fixture):
    effect = fixture[3].effects[0]
    assert effect.anti_aliased is False
    assert effect.blend_mode == 'screen'
    assert effect.choke == 0.0
    assert effect.color
    assert effect.contour
    assert effect.glow_type == 'softer'
    assert effect.noise == 0.0
    assert effect.opacity == 35.0
    assert effect.quality_jitter == 0.0
    assert effect.quality_range == 50.0
    assert effect.size == 41.0
    assert effect.spread == 0.0
    assert effect.gradient is None


def test_inner_glow(fixture):
    effect = fixture[4].effects[0]
    assert effect.anti_aliased is False
    assert effect.blend_mode == 'screen'
    assert effect.choke == 0.0
    assert effect.color
    assert effect.contour
    assert effect.glow_source == 'edge'
    assert effect.glow_type == 'softer'
    assert effect.noise == 0.0
    assert effect.opacity == 46.0
    assert effect.quality_jitter == 0.0
    assert effect.quality_range == 50.0
    assert effect.size == 18.0
    assert effect.gradient is None


def test_inner_shadow(fixture):
    effect = fixture[5].effects[0]
    assert effect.angle == 90.0
    assert effect.anti_aliased is False
    assert effect.blend_mode == 'multiply'
    assert effect.choke == 0.0
    assert effect.color
    assert effect.contour
    assert effect.distance == 18.0
    assert effect.noise == 0.0
    assert effect.opacity == 35.0
    assert effect.size == 41.0
    assert effect.use_global_light is True


def test_color_overlay(fixture):
    effect = fixture[6].effects[0]
    assert effect.blend_mode == 'normal'
    assert effect.color
    assert effect.opacity == 100.0


def test_drop_shadow(fixture):
    effect = fixture[7].effects[0]
    assert effect.angle == 90.0
    assert effect.anti_aliased is False
    assert effect.blend_mode == 'multiply'
    assert effect.choke == 0.0
    assert effect.color
    assert effect.contour
    assert effect.layer_knocks_out is True
    assert effect.distance == 18.0
    assert effect.noise == 0.0
    assert effect.opacity == 35.0
    assert effect.size == 41.0
    assert effect.use_global_light is True


def test_gradient_overlay(fixture):
    effect = fixture[8].effects[0]
    assert effect.aligned is True
    assert effect.angle == 87.0
    assert effect.blend_mode == 'normal'
    assert effect.dithered is False
    assert effect.gradient
    assert effect.offset
    assert effect.opacity == 100.0
    assert effect.reversed is False
    assert effect.scale == 100.0
    assert effect.type == 'linear'


def test_pattern_overlay(fixture):
    effect = fixture[9].effects[0]
    assert effect.aligned is True
    assert effect.blend_mode == 'normal'
    assert effect.opacity == 100.0
    assert effect.pattern
    assert effect.phase
    assert effect.scale == 100.0


def test_stroke(fixture):
    effect = fixture[10].effects[0]
    assert effect.blend_mode == 'normal'
    assert effect.fill_type == 'solid-color'
    assert effect.opacity == 100.0
    assert effect.overprint is False
    assert effect.position == 'outer'
    assert effect.size == 6.0
    assert effect.color
    assert effect.gradient is None
    assert effect.pattern is None


def test_satin(fixture):
    effect = fixture[11].effects[0]
    assert effect.angle == -60.0
    assert effect.anti_aliased is True
    assert effect.blend_mode == 'multiply'
    assert effect.color
    assert effect.contour
    assert effect.distance == 20.0
    assert effect.inverted is True
    assert effect.opacity == 50.0
    assert effect.size == 35.0
