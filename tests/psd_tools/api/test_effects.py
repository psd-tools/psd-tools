import logging

import pytest

from psd_tools.api.psd_image import PSDImage
from psd_tools.terminology import Enum
from psd_tools.api import effects

from ..utils import full_name

logger = logging.getLogger(__name__)


@pytest.fixture
def fixture():
    yield PSDImage.open(full_name("layer_effects.psd"))


def test_effects(fixture) -> None:
    assert isinstance(fixture[0].effects, effects.Effects)
    assert isinstance(fixture[0].effects.scale, float)
    assert fixture[0].effects.enabled is True
    for layer in fixture:
        assert layer.__repr__()
    for effect in fixture[0].effects:
        assert effect.enabled is True


def test_bevel(fixture) -> None:
    effect = fixture[1].effects[0]
    assert isinstance(effect, effects.BevelEmboss)
    assert not hasattr(effect, "blend_mode")
    assert effect.altitude == 30.0
    assert effect.angle == 90.0
    assert effect.anti_aliased is False
    assert effect.bevel_style == Enum.InnerBevel
    assert effect.bevel_type == Enum.SoftMatte
    assert effect.contour
    assert effect.depth == 100.0
    assert effect.direction == Enum.StampIn
    assert effect.enabled is True
    assert effect.highlight_color
    assert effect.highlight_mode == Enum.Screen
    assert effect.highlight_opacity == 50.0
    assert effect.shadow_color
    assert effect.shadow_mode == Enum.Multiply
    assert effect.shadow_opacity == 50.0
    assert effect.size == 41.0
    assert effect.soften == 0.0
    assert effect.use_global_light is True
    assert effect.use_shape is False
    assert effect.use_texture is False


def test_emboss(fixture) -> None:
    effect = fixture[2].effects[0]
    assert isinstance(effect, effects.BevelEmboss)
    assert not hasattr(effect, "blend_mode")
    assert effect.altitude == 30.0
    assert effect.angle == 90.0
    assert effect.anti_aliased is False
    assert effect.bevel_style == Enum.Emboss
    assert effect.bevel_type == Enum.SoftMatte
    assert effect.contour
    assert effect.depth == 100.0
    assert effect.direction == Enum.StampIn
    assert effect.enabled is True
    assert effect.highlight_color
    assert effect.highlight_mode == Enum.Screen
    assert effect.highlight_opacity == 50.0
    assert effect.shadow_color
    assert effect.shadow_mode == Enum.Multiply
    assert effect.shadow_opacity == 50.0
    assert effect.size == 41.0
    assert effect.soften == 0.0
    assert effect.use_global_light is True
    assert effect.use_shape is False
    assert effect.use_texture is False


def test_outer_glow(fixture) -> None:
    effect = fixture[3].effects[0]
    assert isinstance(effect, effects.OuterGlow)
    assert effect.anti_aliased is False
    assert effect.blend_mode == Enum.Screen
    assert effect.choke == 0.0
    assert effect.color
    assert effect.contour
    assert effect.glow_type == Enum.SoftMatte
    assert effect.noise == 0.0
    assert effect.opacity == 35.0
    assert effect.quality_jitter == 0.0
    assert effect.quality_range == 50.0
    assert effect.size == 41.0
    assert effect.spread == 0.0
    assert effect.gradient is None


def test_inner_glow(fixture) -> None:
    effect = fixture[4].effects[0]
    assert isinstance(effect, effects.InnerGlow)
    assert effect.anti_aliased is False
    assert effect.blend_mode == Enum.Screen
    assert effect.choke == 0.0
    assert effect.color
    assert effect.contour
    assert effect.glow_source == Enum.EdgeGlow
    assert effect.glow_type == Enum.SoftMatte
    assert effect.noise == 0.0
    assert effect.opacity == 46.0
    assert effect.quality_jitter == 0.0
    assert effect.quality_range == 50.0
    assert effect.size == 18.0
    assert effect.gradient is None


def test_inner_shadow(fixture) -> None:
    effect = fixture[5].effects[0]
    assert isinstance(effect, effects.InnerShadow)
    assert effect.angle == 90.0
    assert effect.anti_aliased is False
    assert effect.blend_mode == Enum.Multiply
    assert effect.choke == 0.0
    assert effect.color
    assert effect.contour
    assert effect.distance == 18.0
    assert effect.noise == 0.0
    assert effect.opacity == 35.0
    assert effect.size == 41.0
    assert effect.use_global_light is True


def test_color_overlay(fixture) -> None:
    effect = fixture[6].effects[0]
    assert isinstance(effect, effects.ColorOverlay)
    assert effect.blend_mode == Enum.Normal
    assert effect.color
    assert effect.opacity == 100.0


def test_drop_shadow(fixture) -> None:
    effect = fixture[7].effects[0]
    assert isinstance(effect, effects.DropShadow)
    assert effect.angle == 90.0
    assert effect.anti_aliased is False
    assert effect.blend_mode == Enum.Multiply
    assert effect.choke == 0.0
    assert effect.color
    assert effect.contour
    assert effect.layer_knocks_out is True
    assert effect.distance == 18.0
    assert effect.noise == 0.0
    assert effect.opacity == 35.0
    assert effect.size == 41.0
    assert effect.use_global_light is True


def test_gradient_overlay(fixture) -> None:
    effect = fixture[8].effects[0]
    assert isinstance(effect, effects.GradientOverlay)
    assert effect.aligned is True
    assert effect.angle == 87.0
    assert effect.blend_mode == Enum.Normal
    assert effect.dithered is False
    assert effect.gradient
    assert effect.offset
    assert effect.opacity == 100.0
    assert effect.reversed is False
    assert effect.scale == 100.0
    assert effect.type == Enum.Linear


def test_pattern_overlay(fixture) -> None:
    effect = fixture[9].effects[0]
    assert isinstance(effect, effects.PatternOverlay)
    assert effect.aligned is True
    assert effect.blend_mode == Enum.Normal
    assert effect.opacity == 100.0
    assert effect.pattern
    assert effect.phase
    assert effect.scale == 100.0


def test_stroke(fixture) -> None:
    effect = fixture[10].effects[0]
    assert isinstance(effect, effects.Stroke)
    assert effect.blend_mode == Enum.Normal
    assert effect.fill_type == Enum.SolidColor
    assert effect.opacity == 100.0
    assert effect.overprint is False
    assert effect.position == Enum.OutsetFrame
    assert effect.size == 6.0
    assert effect.color
    assert effect.gradient is None
    assert effect.pattern is None


def test_satin(fixture) -> None:
    effect = fixture[11].effects[1]
    assert isinstance(effect, effects.Satin)
    assert effect.angle == -60.0
    assert effect.anti_aliased is True
    assert effect.blend_mode == Enum.Multiply
    assert effect.color
    assert effect.contour
    assert effect.distance == 20.0
    assert effect.inverted is True
    assert effect.opacity == 50.0
    assert effect.size == 35.0
