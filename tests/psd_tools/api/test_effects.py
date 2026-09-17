import logging
from typing import Iterator

import pytest

from psd_tools.api.layers import Layer
from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import Tag
from psd_tools.psd.descriptor import List
from psd_tools.terminology import Enum
from psd_tools.api import effects

from ..utils import full_name

logger = logging.getLogger(__name__)


@pytest.fixture
def fixture() -> Iterator[PSDImage]:
    yield PSDImage.open(full_name("layer_effects.psd"))


def test_effects(fixture: PSDImage) -> None:
    assert isinstance(fixture[0].effects, effects.Effects)
    assert isinstance(fixture[0].effects.scale, float)
    assert fixture[0].effects.enabled is True
    for layer in fixture:
        assert layer.__repr__()
    for effect in fixture[0].effects:
        assert effect.enabled is True


def test_bevel(fixture: PSDImage) -> None:
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


def test_emboss(fixture: PSDImage) -> None:
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


def test_outer_glow(fixture: PSDImage) -> None:
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


def test_inner_glow(fixture: PSDImage) -> None:
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


def test_inner_shadow(fixture: PSDImage) -> None:
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


def test_color_overlay(fixture: PSDImage) -> None:
    effect = fixture[6].effects[0]
    assert isinstance(effect, effects.ColorOverlay)
    assert effect.blend_mode == Enum.Normal
    assert effect.color
    assert effect.opacity == 100.0


def test_drop_shadow(fixture: PSDImage) -> None:
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


def test_gradient_overlay(fixture: PSDImage) -> None:
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


def test_pattern_overlay(fixture: PSDImage) -> None:
    effect = fixture[9].effects[0]
    assert isinstance(effect, effects.PatternOverlay)
    assert effect.aligned is True
    assert effect.blend_mode == Enum.Normal
    assert effect.opacity == 100.0
    assert effect.pattern
    assert effect.phase
    assert effect.scale == 100.0


def test_stroke(fixture: PSDImage) -> None:
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


def test_satin(fixture: PSDImage) -> None:
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


def _forge_unknown_class(layer: Layer, key: bytes, index: int = 0) -> None:
    """Give one of ``layer``'s effects a class psd-tools has no handler for.

    Nothing ships like this: every effect class in ``tests/psd_files`` is one
    ``_TYPES`` holds, and Photoshop writes no others, so reaching the branch
    at all means forging it. ``del layer._effects`` because
    :py:attr:`~psd_tools.api.layers.Layer.effects` memoises what it built.
    """
    item = layer.effects._data[key]  # type: ignore[index]
    item = item[index] if isinstance(item, List) else item
    item.classID = b"XXXX"
    del layer._effects


def test_an_unknown_effect_class_is_skipped_rather_than_rejected() -> None:
    """A class with no handler here costs its effect, not every caller (#828).

    Rejecting it made `layer.effects` raise, and `has_effects()` with it, and
    `Layer.__repr__` through that -- so a file carrying one could not be
    printed, displayed in a notebook, or composited at any log level. It is
    now skipped, like an effect the Photoshop UI does not show.

    The descriptor it came out of is still readable, which is why the master
    switch and the scale are asserted too: only the one effect is dropped.
    """
    psd = PSDImage.open(full_name("layer_effects.psd"))
    layer = psd[10]
    assert [effect.name for effect in layer.effects] == ["Stroke"]
    scale = layer.effects.scale

    _forge_unknown_class(layer, b"FrFX")

    assert list(layer.effects) == []
    assert layer.has_effects() is False
    assert " effects" not in repr(layer)
    assert layer.effects.enabled is True
    assert layer.effects.scale == scale


def test_an_unknown_effect_class_costs_only_its_own_effect() -> None:
    """One unknown class does not take the layer's other effects with it.

    ``double-stroke-effects.psd`` carries two enabled strokes in one
    ``frameFXMulti`` list (#798), so it tells skipping the item apart from
    abandoning the layer: only if the ``continue`` sits inside the per-item
    loop does the second stroke survive the first having no handler.
    """
    psd = PSDImage.open(full_name("effects/double-stroke-effects.psd"))
    layer = psd[1]
    assert [effect.name for effect in layer.effects] == ["Stroke", "Stroke"]

    _forge_unknown_class(layer, b"frameFXMulti", index=0)

    assert [effect.name for effect in layer.effects] == ["Stroke"]
    assert layer.has_effects() is True
    assert layer.has_effects(name="Stroke") is True
    assert " effects" in repr(layer)


def test_an_effects_block_that_did_not_parse_reads_as_no_effects() -> None:
    """The other way listing a layer's effects failed before it began (#828).

    ``TaggedBlock.read()`` keeps the raw bytes of a block it could not parse,
    so ``self._data`` could be ``bytes``, and reading those as a descriptor
    raised -- with the bytes forged here, ``IndexError``. Unlike an unknown
    effect class this needs no forged class name, only an effects descriptor
    that will not read, so it is the more reachable of the two.

    Which exception it was depended on the bytes, and that is the point:
    ``IndexError`` is not in the compositor's ``_UNREADABLE``, so for this
    content no guard #826 added could see it.
    """
    psd = PSDImage.open(full_name("effects/outside-stroke.psd"))
    layer = psd[0]
    assert layer.has_effects()

    for tag in (
        Tag.OBJECT_BASED_EFFECTS_LAYER_INFO,
        Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V0,
        Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V1,
    ):
        if tag in layer.tagged_blocks:
            layer.tagged_blocks[tag].data = b"garbagebytes"
    del layer._effects

    assert list(layer.effects) == []
    assert len(layer.effects) == 0
    assert layer.effects.enabled is False
    assert layer.has_effects() is False
    assert " effects" not in repr(layer)
