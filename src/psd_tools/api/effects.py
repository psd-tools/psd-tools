"""
Effects module.

Everything here is a read-only view on the layer's effects descriptor; none
of it has a setter. An effect is changed by editing that ``descriptor`` in
place, which is the sanctioned way in, and an edit made that way has to be
followed by :py:meth:`~psd_tools.api.psd_image.PSDImage.mark_updated` --
nothing else tells the document that its stored preview no longer matches
its layers::

    from psd_tools.psd.descriptor import UnitFloat
    from psd_tools.terminology import Key, Unit

    layer.effects[0].descriptor[Key.Opacity] = UnitFloat(50.0, Unit.Percent)
    psd.mark_updated()

In place, because the view is rebuilt on every access: rebinding
``descriptor`` itself replaces an object the next access throws away.
"""

import logging
import warnings
from typing import Any, Iterator, Protocol

from psd_tools.api._descriptor import get_enum, get_scalar
from psd_tools.api.protocols import LayerProtocol
from psd_tools.constants import (
    BevelDirection,
    BevelStyle,
    BevelTechnique,
    GlowSource,
    GlowTechnique,
    GradientType,
    Resource,
    StrokeFillType,
    StrokePosition,
    Tag,
)
from psd_tools.psd.descriptor import Descriptor, List
from psd_tools.psd.image_resources import ImageResources
from psd_tools.terminology import Enum, Key, Klass
from psd_tools.registry import new_registry

logger = logging.getLogger(__name__)

_TYPES, register = new_registry()


_EFFECTS_TAGS = (
    Tag.OBJECT_BASED_EFFECTS_LAYER_INFO,
    Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V0,
    Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V1,
)


def _master_switch(data: Descriptor | None) -> bool:
    """Whether the master fx switch is on. False when there is no block."""
    return get_scalar(data, b"masterFXSwitch", bool, False)


class Effects:
    """
    List-like effects.

    A live view on the layer's effects block: every access re-reads the
    descriptor, so an edit made underneath shows through, and :py:attr:`items`
    hands out a fresh list that cannot write back into the proxy.

    Only effects that are present and that this version can interpret are
    kept: one that is not present, and one whose effect class has no handler
    here, are both skipped. A layer whose effects block did not parse at all
    has no effects.

    The block itself is not this proxy's subject. Photoshop creates it with
    the first effect attached and leaves it behind once the last is removed,
    so it outlives everything it ever listed. A caller who wants that fact
    asks the low-level structure, which spells the block three ways::

        any(
            tag in layer.tagged_blocks
            for tag in (
                Tag.OBJECT_BASED_EFFECTS_LAYER_INFO,
                Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V0,
                Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V1,
            )
        )
    """

    def __init__(self, layer: LayerProtocol):
        self._layer = layer

    @property
    def _data(self) -> Descriptor | None:
        """The layer's effects descriptor, or None if there is none to read."""
        for tag in _EFFECTS_TAGS:
            if tag in self._layer.tagged_blocks:
                data = self._layer.tagged_blocks.get_data(tag)
                # ``TaggedBlock.read()`` keeps the raw bytes of a block it
                # could not read, and reports that once, at ERROR. Both that
                # and no block at all are the no-effects case, which every
                # property below answers for rather than raising (#828).
                return data if isinstance(data, Descriptor) else None
        return None

    def _list(self, data: Descriptor | None) -> list["_Effect"]:
        """The effects ``data`` lists, in file order.

        Takes the descriptor rather than reading it, so :py:meth:`find`, which
        needs the master switch as well, reads the tagged blocks once.
        """
        items: list["_Effect"] = []
        if data is None:
            return items
        for key in data:
            value = data[key]
            if not isinstance(value, List):
                value = [value]
            for item in value:
                # Keep only present effects.
                if not (
                    isinstance(item, Descriptor)
                    and get_scalar(item, b"present", bool, False)
                ):
                    continue
                kls = _TYPES.get(item.classID)
                if kls is None:
                    # Skip it, like the effect above that is not present.
                    # Rejecting it is defensible on its own, but ``Effects`` is
                    # read from read-only paths -- ``has_effects()``, and
                    # ``Layer.__repr__`` through it -- that can only pass a
                    # raise on. One effect lost, rather than the document
                    # (#828).
                    logger.debug("Effect class not found for %r", item.classID)
                    continue
                items.append(kls(item, self._layer._psd.image_resources))
        return items

    @property
    def scale(self) -> float:
        """The fx list's scale, in percent.

        100.0 where there is nothing to read, which is what a block that
        omits the key already answers. :py:attr:`enabled` answers on the
        same guard rather than raising, and this now matches it.
        """
        data = self._data
        if data is None:
            return 100.0
        return get_scalar(data, Key.Scale, float, 100.0)

    @property
    def enabled(self) -> bool:
        """Whether the master fx switch is on.

        Photoshop's one switch over the whole fx list, which greys every entry
        out at once. It says nothing about the individual effects' ``enabled``
        flags, and a list it has switched off still lists them.

        :rtype: bool
        """
        return _master_switch(self._data)

    @property
    def items(self) -> list["_Effect"]:
        """The listed effects, as a new list on every access."""
        return self._list(self._data)

    def find(self, name: str, enabled: bool = True) -> Iterator["_Effect"]:
        """Iterate effect items by name.

        :param name: Effect name, e.g. `DropShadow`, `InnerShadow`, `OuterGlow`,
            `InnerGlow`, `ColorOverlay`, `GradientOverlay`, `PatternOverlay`,
            `Stroke`, `BevelEmboss`, or `Satin`.
        :param enabled: If true, only return enabled effects.
        :rtype: Iterator[Effect]
        """
        data = self._data
        if enabled and not _master_switch(data):
            return
        KLASS = {kls.__name__.lower(): kls for kls in _TYPES.values()}
        target_kls = KLASS.get(name.lower())
        if target_kls is None:
            logger.debug("Effect class not found for name=%r", name)
            return
        for item in self._list(data):
            if isinstance(item, target_kls):
                if enabled and item.enabled:
                    yield item
                elif not enabled:
                    yield item

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self) -> Iterator["_Effect"]:
        return iter(self.items)

    def __getitem__(self, key: int) -> "_Effect":
        return self.items[key]

    def __repr__(self) -> str:
        return "%s(%s)" % (
            self.__class__.__name__,
            " ".join(x.__class__.__name__.lower() for x in self.items),
        )


class _EffectProtocol(Protocol):
    """Effect protocol."""

    descriptor: Descriptor
    _image_resources: ImageResources


class _Effect(_EffectProtocol):
    """Base Effect class.

    A read-only view on one entry of the layer's fx list. ``descriptor`` is
    that entry, and the only way to change one; see the module docstring for
    what an edit through it owes the document.
    """

    def __init__(self, descriptor: Descriptor, image_resources: ImageResources):
        self.descriptor = descriptor
        self._image_resources = image_resources

    @property
    def value(self) -> Descriptor:
        """Effect descriptor value.

        .. note:: Deprecated. Use the ``descriptor`` property instead.
        """
        warnings.warn(
            "'value' is deprecated, use the 'descriptor' property instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.descriptor

    @property
    def enabled(self) -> bool:
        """Whether if the effect is enabled."""
        return get_scalar(self.descriptor, Key.Enabled, bool, False)

    @property
    def present(self) -> bool:
        """Whether the effect has an entry in the layer's fx list.

        It is the flag :py:class:`Effects` filters on, so it is True for every
        effect a listing hands out and distinguishes nothing within one. It
        says so only as of that listing, though: clear it on an effect you are
        holding and this reports False, while the next listing drops it.
        """
        return get_scalar(self.descriptor, b"present", bool, False)

    @property
    def shown(self) -> bool:
        """Whether if the effect is shown in dialog."""
        return get_scalar(self.descriptor, b"showInDialog", bool, False)

    @property
    def opacity(self) -> float:
        """Layer effect opacity in percentage."""
        return get_scalar(self.descriptor, Key.Opacity, float, 100.0)

    def has_patterns(self) -> bool:
        return isinstance(self, _PatternMixin) and self.pattern is not None

    @property
    def name(self) -> str:
        """Effect name."""
        return self.__class__.__name__

    def __repr__(self) -> str:
        return self.name

    def _repr_pretty_(self, p: Any, cycle: bool) -> None:
        if cycle:
            return
        p.text(self.__repr__())


class _ColorMixin(_EffectProtocol):
    @property
    def color(self) -> Descriptor:
        """Color."""
        return self.descriptor.get(Key.Color)

    @property
    def blend_mode(self) -> bytes:
        """Effect blending mode."""
        mode = self.descriptor.get(Key.Mode)
        return getattr(mode, "enum", Enum.Normal) if mode is not None else Enum.Normal


class _ChokeNoiseMixin(_ColorMixin):
    @property
    def choke(self) -> float:
        """Choke level in pixels."""
        return get_scalar(self.descriptor, Key.ChokeMatte, float, 0.0)

    @property
    def size(self) -> float:
        """Size in pixels."""
        return get_scalar(self.descriptor, Key.Blur, float, 0.0)

    @property
    def noise(self) -> float:
        """Noise level in percent."""
        return get_scalar(self.descriptor, Key.Noise, float, 0.0)

    @property
    def anti_aliased(self) -> bool:
        """Angi-aliased."""
        return get_scalar(self.descriptor, Key.AntiAlias, bool, False)

    @property
    def contour(self) -> Descriptor:
        """Contour configuration."""
        return self.descriptor.get(Key.TransferSpec)


class _AngleMixin(_EffectProtocol):
    @property
    def use_global_light(self) -> bool:
        """Using global light."""
        return get_scalar(self.descriptor, Key.UseGlobalAngle, bool, False)

    @property
    def angle(self) -> float:
        """Angle value."""
        if self.use_global_light:
            return self._image_resources.get_data(Resource.GLOBAL_ANGLE, 30.0)
        return get_scalar(self.descriptor, Key.LocalLightingAngle, float, 0.0)


class _GradientMixin(_EffectProtocol):
    @property
    def gradient(self) -> Descriptor:
        """Gradient configuration."""
        return self.descriptor.get(Key.Gradient)

    @property
    def angle(self) -> float:
        """Angle value."""
        return get_scalar(self.descriptor, Key.Angle, float, 0.0)

    @property
    def type(self) -> GradientType | None:
        """
        Gradient type, or None where the descriptor does not say.

        That is most of them: :py:class:`Stroke` and the two glows inherit
        this property from the gradient mixin, while only a gradient writes
        the key.
        """
        return get_enum(self.descriptor, Key.Type, GradientType)

    @property
    def reversed(self) -> bool:
        """Reverse flag."""
        return get_scalar(self.descriptor, Key.Reverse, bool, False)

    @property
    def dithered(self) -> bool:
        """Dither flag."""
        return get_scalar(self.descriptor, Key.Dither, bool, False)

    @property
    def offset(self) -> Descriptor:
        """Offset value in Pnt descriptor."""
        return self.descriptor.get(Key.Offset)


class _PatternMixin(_EffectProtocol):
    # ``b"Ptrn"`` and ``b"Lnkd"`` below are the codes Photoshop writes for
    # these keys, and they are also Enum.Pattern and Enum.Linked. Adobe
    # reuses a code across roles, and the Enum/Key/Klass split is a
    # psd-tools convention, so a key spelled like an Enum is not a bug.

    @property
    def pattern(self) -> Descriptor:
        """Pattern config."""
        # TODO: Expose nested property.
        return self.descriptor.get(b"Ptrn")

    @property
    def linked(self) -> bool:
        """Linked."""
        return get_scalar(self.descriptor, b"Lnkd", bool, False)

    @property
    def angle(self) -> float:
        """Angle value."""
        return get_scalar(self.descriptor, Key.Angle, float, 0.0)

    @property
    def phase(self) -> Descriptor:
        """Phase value in Point."""
        return self.descriptor.get(b"phase")


class _ShadowEffect(_Effect, _ChokeNoiseMixin, _AngleMixin):
    """Base class for shadow effect."""

    @property
    def distance(self) -> float:
        """Distance in pixels."""
        return get_scalar(self.descriptor, Key.Distance, float, 0.0)


class _GlowEffect(_Effect, _ChokeNoiseMixin, _GradientMixin):
    """Base class for glow effect."""

    @property
    def glow_type(self) -> GlowTechnique | None:
        """Glow technique, or None where the descriptor does not say."""
        return get_enum(self.descriptor, Key.GlowTechnique, GlowTechnique)

    @property
    def quality_range(self) -> float:
        """Quality range in percent."""
        return get_scalar(self.descriptor, Key.InputRange, float, 0.0)

    @property
    def quality_jitter(self) -> float:
        """Quality jitter in percent."""
        return get_scalar(self.descriptor, Key.ShadingNoise, float, 0.0)


class _OverlayEffect(_Effect):
    pass


class _AlignScaleMixin(_EffectProtocol):
    @property
    def blend_mode(self) -> bytes:
        """Effect blending mode."""
        mode = self.descriptor.get(Key.Mode)
        return getattr(mode, "enum", Enum.Normal) if mode is not None else Enum.Normal

    @property
    def scale(self) -> float:
        """Scale value."""
        return get_scalar(self.descriptor, Key.Scale, float, 1.0)

    @property
    def aligned(self) -> bool:
        """Aligned."""
        return get_scalar(self.descriptor, Key.Alignment, bool, False)


@register(Klass.DropShadow.value)
class DropShadow(_ShadowEffect):
    @property
    def layer_knocks_out(self) -> bool:
        """Layers are knocking out."""
        return get_scalar(self.descriptor, b"layerConceals", bool, False)


@register(Klass.InnerShadow.value)
class InnerShadow(_ShadowEffect):
    pass


@register(Klass.OuterGlow.value)
class OuterGlow(_GlowEffect):
    @property
    def spread(self) -> float:
        """Spread level in percent."""
        return get_scalar(self.descriptor, Key.ShadingNoise, float, 0.0)


@register(Klass.InnerGlow.value)
class InnerGlow(_GlowEffect):
    @property
    def glow_source(self) -> GlowSource | None:
        """Elements source, or None where the descriptor does not say."""
        return get_enum(self.descriptor, Key.InnerGlowSource, GlowSource)


@register(Klass.SolidFill.value)
class ColorOverlay(_OverlayEffect, _ColorMixin):
    pass


@register(b"GrFl")  # Enum.GradientFill's code, reused as a class ID.
class GradientOverlay(_OverlayEffect, _AlignScaleMixin, _GradientMixin):
    pass


@register(b"patternFill")
class PatternOverlay(_OverlayEffect, _AlignScaleMixin, _PatternMixin):
    pass


@register(Klass.FrameFX.value)
class Stroke(_Effect, _ColorMixin, _PatternMixin, _GradientMixin):
    @property
    def position(self) -> StrokePosition | None:
        """Position of the stroke, or None where the descriptor does not say."""
        return get_enum(self.descriptor, Key.Style, StrokePosition)

    @property
    def fill_type(self) -> StrokeFillType | None:
        """Fill type, or None where the descriptor does not say."""
        return get_enum(self.descriptor, Key.PaintType, StrokeFillType)

    @property
    def size(self) -> float:
        """Size value."""
        return get_scalar(self.descriptor, Key.SizeKey, float, 0.0)

    @property
    def overprint(self) -> bool:
        """Overprint flag."""
        return get_scalar(self.descriptor, b"overprint", bool, False)


@register(Klass.BevelEmboss.value)
class BevelEmboss(_Effect, _AngleMixin):
    @property
    def highlight_mode(self) -> bytes:
        """Highlight blending mode."""
        mode = self.descriptor.get(Key.HighlightMode)
        return getattr(mode, "enum", Enum.Normal) if mode is not None else Enum.Normal

    @property
    def highlight_color(self) -> Descriptor:
        """Highlight color value."""
        return self.descriptor.get(Key.HighlightColor)

    @property
    def highlight_opacity(self) -> float:
        """Highlight opacity value in percentage."""
        return get_scalar(self.descriptor, Key.HighlightOpacity, float, 50.0)

    @property
    def shadow_mode(self) -> bytes:
        """Shadow blending mode."""
        mode = self.descriptor.get(Key.ShadowMode)
        return getattr(mode, "enum", Enum.Normal) if mode is not None else Enum.Normal

    @property
    def shadow_color(self) -> Descriptor:
        """Shadow color value."""
        return self.descriptor.get(Key.ShadowColor)

    @property
    def shadow_opacity(self) -> float:
        """Shadow opacity value in percentage."""
        return get_scalar(self.descriptor, Key.ShadowOpacity, float, 50.0)

    @property
    def bevel_type(self) -> BevelTechnique | None:
        """Bevel technique, or None where the descriptor does not say."""
        return get_enum(self.descriptor, Key.BevelTechnique, BevelTechnique)

    @property
    def bevel_style(self) -> BevelStyle | None:
        """Bevel style, or None where the descriptor does not say."""
        return get_enum(self.descriptor, Key.BevelStyle, BevelStyle)

    @property
    def altitude(self) -> float:
        """Altitude value in angle."""
        return get_scalar(self.descriptor, Key.LocalLightingAltitude, float, 30.0)

    @property
    def depth(self) -> float:
        """Depth value in percentage."""
        return get_scalar(self.descriptor, Key.StrengthRatio, float, 0.0)

    @property
    def size(self) -> float:
        """Size value in pixel."""
        return get_scalar(self.descriptor, Key.Blur, float, 0.0)

    @property
    def direction(self) -> BevelDirection | None:
        """Direction, or None where the descriptor does not say."""
        return get_enum(self.descriptor, Key.BevelDirection, BevelDirection)

    @property
    def contour(self) -> Descriptor:
        """Contour configuration."""
        return self.descriptor.get(Key.TransferSpec)

    @property
    def anti_aliased(self) -> bool:
        """Anti-aliased."""
        return get_scalar(self.descriptor, b"antialiasGloss", bool, False)

    @property
    def soften(self) -> float:
        """Soften value in pixels."""
        return get_scalar(self.descriptor, Key.Softness, float, 0.0)

    @property
    def use_shape(self) -> bool:
        """Using shape."""
        return get_scalar(self.descriptor, b"useShape", bool, False)

    @property
    def use_texture(self) -> bool:
        """Using texture."""
        return get_scalar(self.descriptor, b"useTexture", bool, False)


@register(Klass.ChromeFX.value)
class Satin(_Effect, _ColorMixin):
    """Satin effect."""

    @property
    def anti_aliased(self) -> bool:
        """Anti-aliased."""
        return get_scalar(self.descriptor, Key.AntiAlias, bool, False)

    @property
    def inverted(self) -> bool:
        """Inverted."""
        return get_scalar(self.descriptor, Key.Invert, bool, False)

    @property
    def angle(self) -> float:
        """Angle value in degrees."""
        return get_scalar(self.descriptor, Key.LocalLightingAngle, float, 0.0)

    @property
    def distance(self) -> float:
        """Distance value in pixels."""
        return get_scalar(self.descriptor, Key.Distance, float, 120.0)

    @property
    def size(self) -> float:
        """Size value in pixel."""
        return get_scalar(self.descriptor, Key.Blur, float, 120.0)

    @property
    def contour(self) -> Descriptor:
        """Contour configuration."""
        return self.descriptor.get(Key.MappingShape)
