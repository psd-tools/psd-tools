import logging
from pathlib import Path
from typing import Iterator

import pytest

from psd_tools.api.layers import Layer
from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import Tag
from psd_tools.psd.descriptor import Bool, Descriptor, List, UnitFloat
from psd_tools.terminology import Enum, Key, Unit
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
    assert effect.type is None  # a glow inherits the gradient mixin
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
    assert effect.type is None  # a glow inherits the gradient mixin
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
    # One class covers all three fill shapes, so a solid-colour stroke is
    # asked about a gradient it does not have. It used to answer b"Lnr ".
    assert effect.type is None


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
    at all means forging it.

    No ``del layer._effects`` afterwards: :py:attr:`Layer.effects` is a live
    view, so the callers below see the forged class on their next access.
    That this helper reads ``layer.effects._data`` first is what makes them
    evidence for it -- under the snapshot they would be reading a list built
    before the forgery.
    """
    item = layer.effects._data[key]  # type: ignore[index]
    item = item[index] if isinstance(item, List) else item
    item.classID = b"XXXX"


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

    assert list(layer.effects) == []
    assert len(layer.effects) == 0
    assert layer.effects.enabled is False
    assert layer.has_effects() is False
    assert " effects" not in repr(layer)


def _effects_block(layer: Layer) -> Descriptor | None:
    """The layer's effects descriptor straight out of the low-level structure.

    The route :py:meth:`Layer.has_effects` documents in place of an API for
    block presence, so the tests below can say "the block is still there"
    without going through the proxy that is under test.
    """
    for tag in (
        Tag.OBJECT_BASED_EFFECTS_LAYER_INFO,
        Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V0,
        Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V1,
    ):
        if tag in layer.tagged_blocks:
            data = layer.tagged_blocks.get_data(tag)
            return data if isinstance(data, Descriptor) else None
    return None


def test_a_block_listing_nothing_is_not_effects() -> None:
    """``has_effects(enabled=False)`` follows the fx list, not the block (#830).

    ``Фигура 1`` is the first of the 38 layers in ``tests/psd_files`` that
    carry an effects block listing nothing -- Photoshop writes the block when
    the first effect is attached and leaves it once the last is removed.

    It discriminates because both its entries are ``enab=True`` with no
    ``present`` flag: an implementation that read the enabled flag, or the
    block, would answer True here. Only ``present`` -- what the Photoshop UI
    lists, and what ``Effects`` already filters on -- answers False.
    """
    psd = PSDImage.open(full_name("layer_comps.psd"))
    layer = psd[1]

    block = _effects_block(layer)
    assert block is not None
    assert bool(block.get(b"masterFXSwitch")) is True
    entries = [block[key] for key in block if isinstance(block[key], Descriptor)]
    assert [entry.classID for entry in entries] == [b"DrSh", b"ebbl"]
    assert [bool(entry.get(Key.Enabled)) for entry in entries] == [True, True]
    assert [bool(entry.get(b"present")) for entry in entries] == [False, False]

    assert len(layer.effects) == 0
    assert layer.has_effects() is False
    assert layer.has_effects(enabled=False) is False
    # The pair that used to disagree on this very layer: True from the arm
    # that asked about the block, False from the arm that read the list.
    assert layer.has_effects(enabled=False, name="DropShadow") is False
    assert layer.has_effects(enabled=False, name="BevelEmboss") is False


def test_effects_follows_a_block_attached_after_it_was_read() -> None:
    """The additive half of the live view: a block set later is seen.

    Under the snapshot this was unreachable without ``del layer._effects``,
    and the only reason the corresponding compositor fixture worked was that
    it set its block before anything read ``layer.effects``.

    ``view`` is taken, and read, while the layer still has no block, and is
    asserted on alongside every fresh ``layer.effects``. Without it the test
    would pass on the de-memoisation alone -- a proxy that still froze its
    own descriptor would go unnoticed, since each access hands back a new one.
    """
    psd = PSDImage.open(full_name("layer_comps.psd"))
    layer = psd[3]
    assert _effects_block(layer) is None
    view = layer.effects
    assert len(view) == 0
    assert view.enabled is False

    overlay = Descriptor(classID=b"SoFi")
    overlay[Key.Enabled] = Bool(True)
    overlay[b"present"] = Bool(True)
    block = Descriptor(classID=b"null")
    block[b"masterFXSwitch"] = Bool(True)
    block[b"solidFill"] = overlay
    layer.tagged_blocks.set_data(Tag.OBJECT_BASED_EFFECTS_LAYER_INFO, block)

    assert [effect.name for effect in layer.effects] == ["ColorOverlay"]
    assert [effect.name for effect in view] == ["ColorOverlay"]
    assert layer.effects.enabled is True
    assert view.enabled is True
    assert layer.has_effects() is True
    assert layer.has_effects(name="ColorOverlay") is True
    assert list(view.find("ColorOverlay"))

    # And the structural flags too, which the snapshot froze along with the
    # list. ``set_data`` stores a ``DescriptorBlock2`` of its own, so these go
    # at what the layer now holds rather than at what was handed to it.
    stored = _effects_block(layer)
    assert stored is not None
    stored[b"masterFXSwitch"] = Bool(False)
    assert layer.effects.enabled is False
    assert view.enabled is False
    assert layer.has_effects() is False
    # Switching the master off greys the fx list out; it does not empty it.
    assert layer.has_effects(enabled=False) is True
    assert len(view) == 1
    stored[b"solidFill"][b"present"] = Bool(False)  # type: ignore[index]
    assert layer.has_effects(enabled=False) is False
    assert len(view) == 0


def test_items_hands_out_a_list_that_cannot_write_back() -> None:
    """``items`` was the internal list itself, so a caller could empty it.

    Held as one proxy throughout: re-reading ``layer.effects`` would pass on
    the de-memoisation alone, and the point here is the list.
    """
    effects = PSDImage.open(full_name("layer_effects.psd"))[10].effects
    assert [effect.name for effect in effects.items] == ["Stroke"]

    effects.items.clear()

    assert len(effects) == 1
    assert [effect.name for effect in effects.items] == ["Stroke"]


def test_an_absent_reporting_enum_is_not_fabricated() -> None:
    """The reporting-only enums answer None instead of inventing a default.

    Only ``type`` reaches the absent case on a real file -- 43 of the 53
    corpus effects that expose it never write the key. The other three are
    written by every file there is, so taking the key away is the only way
    to ask them the question at all.
    """
    psd = PSDImage.open(full_name("layer_effects.psd"))

    stroke = psd[10].effects[0]
    assert isinstance(stroke, effects.Stroke)
    assert stroke.position == Enum.OutsetFrame
    assert stroke.fill_type == Enum.SolidColor
    del stroke.descriptor[Key.Style]
    del stroke.descriptor[Key.PaintType]
    assert stroke.position is None
    assert stroke.fill_type is None

    glow = psd[3].effects[0]
    assert isinstance(glow, effects.OuterGlow)
    assert glow.glow_type == Enum.SoftMatte
    del glow.descriptor[Key.GlowTechnique]
    assert glow.glow_type is None


def test_value_is_deprecated_out_loud() -> None:
    """The deprecation was a ``logger.debug`` no user ever saw.

    The compositor was its last in-tree reader until #831; nothing in the
    library trips this now.
    """
    effect = PSDImage.open(full_name("layer_effects.psd"))[10].effects[0]

    with pytest.warns(DeprecationWarning, match="descriptor"):
        assert effect.value is effect.descriptor


def test_the_documented_edit_recipe_survives_a_save(tmp_path: Path) -> None:
    """The module docstring's editing recipe, run exactly as it is written.

    It is the one workflow this module sanctions, and the failure it guards
    against is invisible short of a save: a unit given as raw bytes reads
    back correctly and only raises in ``write()``.
    """
    psd = PSDImage.open(full_name("layer_effects.psd"))
    psd[6].effects[0].descriptor[Key.Opacity] = UnitFloat(50.0, Unit.Percent)
    psd.mark_updated()

    out = tmp_path / "edited.psd"
    psd.save(out)

    assert PSDImage.open(out)[6].effects[0].opacity == 50.0
