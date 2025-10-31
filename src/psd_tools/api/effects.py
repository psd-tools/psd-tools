"""
Effects module.
"""

import logging
from typing import Any, Iterator, Optional, Protocol

from psd_tools.constants import Resource, Tag
from psd_tools.psd.descriptor import Descriptor, List
from psd_tools.psd.image_resources import ImageResources
from psd_tools.terminology import Key, Klass
from psd_tools.utils import new_registry

logger = logging.getLogger(__name__)

_TYPES, register = new_registry()


class Effects:
    """
    List-like effects.

    Only present effects are kept.
    """

    def __init__(self, layer: Any):  # TODO: Circular import
        self._data: Optional[Descriptor] = None
        for tag in (
            Tag.OBJECT_BASED_EFFECTS_LAYER_INFO,
            Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V0,
            Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V1,
        ):
            if tag in layer.tagged_blocks:
                self._data = layer.tagged_blocks.get_data(tag)
                break

        self._items: list["_Effect"] = []
        if self._data is None:
            return        
        for key in self._data:
            value = self._data[key]
            if not isinstance(value, List):
                value = [value]
            for item in value:
                # Keep only present effects.
                if not (isinstance(item, Descriptor) and item.get(b"present")):
                    continue
                kls = _TYPES.get(item.classID)
                assert kls is not None, "kls not found for %r" % item.classID
                self._items.append(kls(item, layer._psd.image_resources))

    @property
    def scale(self) -> float:
        """Scale value."""
        assert self._data is not None
        return float(self._data.get(Key.Scale, 100.0))

    @property
    def enabled(self) -> bool:
        """Whether if all the effects are enabled.

        :rtype: bool
        """
        if self._data is None:
            return False
        return bool(self._data.get(b"masterFXSwitch"))

    @property
    def items(self) -> list["_Effect"]:
        return self._items

    def find(self, name: str, enabled: bool = True) -> Iterator["_Effect"]:
        """Iterate effect items by name.
        
        :param name: Effect name, e.g. `DropShadow`, `InnerShadow`, `OuterGlow`,
            `InnerGlow`, `ColorOverlay`, `GradientOverlay`, `PatternOverlay`,
            `Stroke`, `BevelEmboss`, or `Satin`.
        :param enabled: If true, only return enabled effects.
        :rtype: Iterator[Effect]
        """
        if enabled and not self.enabled:
            return
        KLASS = {kls.__name__.lower(): kls for kls in _TYPES.values()}
        for item in self:
            if isinstance(item, KLASS.get(name.lower(), None)):
                if enabled and item.enabled:
                    yield item
                elif not enabled:
                    yield item

    def __len__(self) -> int:
        return self._items.__len__()

    def __iter__(self) -> Iterator["_Effect"]:
        return self._items.__iter__()

    def __getitem__(self, key) -> "_Effect":
        return self._items.__getitem__(key)

    def __repr__(self) -> str:
        return "%s(%s)" % (
            self.__class__.__name__,
            " ".join(x.__class__.__name__.lower() for x in self) if self._data else "",
        )


class _EffectProtocol(Protocol):
    """Effect protocol."""
    descriptor: Descriptor
    _image_resources: ImageResources


class _Effect(_EffectProtocol):
    """Base Effect class."""

    def __init__(self, descriptor: Descriptor, image_resources: ImageResources):
        self.descriptor = descriptor
        self._image_resources = image_resources

    @property
    def value(self) -> Descriptor:
        """Deprecated
        Effect descriptor value. Use `descriptor` property instead.
        """
        logger.debug("Deprecated, use 'descriptor' property instead.")
        return self.descriptor

    @property
    def enabled(self) -> bool:
        """Whether if the effect is enabled."""
        return bool(self.descriptor.get(Key.Enabled))

    @property
    def present(self) -> bool:
        """Whether if the effect is present in Photoshop UI."""
        return bool(self.descriptor.get(b"present"))

    @property
    def shown(self) -> bool:
        """Whether if the effect is shown in dialog."""
        return bool(self.descriptor.get(b"showInDialog"))

    @property
    def opacity(self) -> float:
        """Layer effect opacity in percentage."""
        return float(self.descriptor.get(Key.Opacity, 100.0))

    def has_patterns(self) -> bool:
        return isinstance(self, _PatternMixin) and self.pattern is not None
    
    @property
    def name(self) -> str:
        """Effect name."""
        return self.__class__.__name__

    def __repr__(self) -> str:
        return self.name

    def _repr_pretty_(self, p, cycle):
        if cycle:
            return self.__repr__()
        p.text(self.__repr__())


class _ColorMixin(_EffectProtocol):
    @property
    def color(self) -> Descriptor:
        """Color."""
        return self.descriptor.get(Key.Color)

    @property
    def blend_mode(self) -> bytes:
        """Effect blending mode."""
        return self.descriptor.get(Key.Mode).enum


class _ChokeNoiseMixin(_ColorMixin):
    @property
    def choke(self) -> float:
        """Choke level in pixels."""
        return float(self.descriptor.get(Key.ChokeMatte, 0.0))

    @property
    def size(self) -> float:
        """Size in pixels."""
        return float(self.descriptor.get(Key.Blur, 0.0))

    @property
    def noise(self) -> float:
        """Noise level in percent."""
        return float(self.descriptor.get(Key.Noise, 0.0))

    @property
    def anti_aliased(self) -> bool:
        """Angi-aliased."""
        return bool(self.descriptor.get(Key.AntiAlias))

    @property
    def contour(self) -> Descriptor:
        """Contour configuration."""
        return self.descriptor.get(Key.TransferSpec)


class _AngleMixin(_EffectProtocol):
    @property
    def use_global_light(self) -> bool:
        """Using global light."""
        return bool(self.descriptor.get(Key.UseGlobalAngle))

    @property
    def angle(self) -> float:
        """Angle value."""
        if self.use_global_light:
            return self._image_resources.get_data(Resource.GLOBAL_ANGLE, 30.0)
        return float(self.descriptor.get(Key.LocalLightingAngle, 0.0))


class _GradientMixin(_EffectProtocol):
    @property
    def gradient(self) -> Descriptor:
        """Gradient configuration."""
        return self.descriptor.get(Key.Gradient)

    @property
    def angle(self) -> float:
        """Angle value."""
        return float(self.descriptor.get(Key.Angle, 0.0))

    @property
    def type(self) -> bytes:
        """
        Gradient type, one of `linear`, `radial`, `angle`, `reflected`, or
        `diamond`.
        """
        return self.descriptor.get(Key.Type).enum

    @property
    def reversed(self) -> bool:
        """Reverse flag."""
        return bool(self.descriptor.get(Key.Reverse))

    @property
    def dithered(self) -> bool:
        """Dither flag."""
        return bool(self.descriptor.get(Key.Dither))

    @property
    def offset(self) -> Descriptor:
        """Offset value in Pnt descriptor."""
        return self.descriptor.get(Key.Offset)


class _PatternMixin(_EffectProtocol):
    @property
    def pattern(self) -> Descriptor:
        """Pattern config."""
        # TODO: Expose nested property.
        return self.descriptor.get(b"Ptrn")  # Enum.Pattern. Seems a bug.

    @property
    def linked(self) -> bool:
        """Linked."""
        return bool(self.descriptor.get(b"Lnkd"))  # Enum.Linked. Seems a bug.

    @property
    def angle(self) -> float:
        """Angle value."""
        return float(self.descriptor.get(Key.Angle, 0.0))

    @property
    def phase(self) -> Descriptor:
        """Phase value in Point."""
        return self.descriptor.get(b"phase")


class _ShadowEffect(_Effect, _ChokeNoiseMixin, _AngleMixin):
    """Base class for shadow effect."""

    @property
    def distance(self) -> float:
        """Distance in pixels."""
        return float(self.descriptor.get(Key.Distance, 0.0))


class _GlowEffect(_Effect, _ChokeNoiseMixin, _GradientMixin):
    """Base class for glow effect."""

    @property
    def glow_type(self) -> bytes:
        """Glow type."""
        return self.descriptor.get(Key.GlowTechnique).enum

    @property
    def quality_range(self) -> float:
        """Quality range in percent."""
        return float(self.descriptor.get(Key.InputRange, 0.0))

    @property
    def quality_jitter(self) -> float:
        """Quality jitter in percent."""
        return float(self.descriptor.get(Key.ShadingNoise, 0.0))


class _OverlayEffect(_Effect):
    pass


class _AlignScaleMixin(_EffectProtocol):
    @property
    def blend_mode(self) -> bytes:
        """Effect blending mode."""
        return self.descriptor.get(Key.Mode).enum

    @property
    def scale(self) -> float:
        """Scale value."""
        return float(self.descriptor.get(Key.Scale, 1.0))

    @property
    def aligned(self) -> bool:
        """Aligned."""
        return bool(self.descriptor.get(Key.Alignment))


@register(Klass.DropShadow.value)
class DropShadow(_ShadowEffect):
    @property
    def layer_knocks_out(self) -> bool:
        """Layers are knocking out."""
        return bool(self.descriptor.get(b"layerConceals"))


@register(Klass.InnerShadow.value)
class InnerShadow(_ShadowEffect):
    pass


@register(Klass.OuterGlow.value)
class OuterGlow(_GlowEffect):
    @property
    def spread(self) -> float:
        """Spread level in percent."""
        return float(self.descriptor.get(Key.ShadingNoise, 0.0))


@register(Klass.InnerGlow.value)
class InnerGlow(_GlowEffect):
    @property
    def glow_source(self) -> bytes:
        """Elements source."""
        return self.descriptor.get(Key.InnerGlowSource).enum


@register(Klass.SolidFill.value)
class ColorOverlay(_OverlayEffect, _ColorMixin):
    pass


@register(b"GrFl")  # Equal to Enum.GradientFill. This seems a bug.
class GradientOverlay(_OverlayEffect, _AlignScaleMixin, _GradientMixin):
    pass


@register(b"patternFill")
class PatternOverlay(_OverlayEffect, _AlignScaleMixin, _PatternMixin):
    pass


@register(Klass.FrameFX.value)
class Stroke(_Effect, _ColorMixin, _PatternMixin, _GradientMixin):
    @property
    def position(self) -> bytes:
        """
        Position of the stroke, InsetFrame, OutsetFrame, or CenteredFrame.
        """
        return self.descriptor.get(Key.Style).enum

    @property
    def fill_type(self) -> bytes:
        """Fill type, SolidColor, Gradient, or Pattern."""
        return self.descriptor.get(Key.PaintType).enum

    @property
    def size(self) -> float:
        """Size value."""
        return float(self.descriptor.get(Key.SizeKey, 0.0))

    @property
    def overprint(self) -> bool:
        """Overprint flag."""
        return bool(self.descriptor.get(b"overprint"))


@register(Klass.BevelEmboss.value)
class BevelEmboss(_Effect, _AngleMixin):
    @property
    def highlight_mode(self) -> bytes:
        """Highlight blending mode."""
        return self.descriptor.get(Key.HighlightMode).enum

    @property
    def highlight_color(self) -> Descriptor:
        """Highlight color value."""
        return self.descriptor.get(Key.HighlightColor)

    @property
    def highlight_opacity(self) -> float:
        """Highlight opacity value in percentage."""
        return float(self.descriptor.get(Key.HighlightOpacity, 50.0))

    @property
    def shadow_mode(self) -> bytes:
        """Shadow blending mode."""
        return self.descriptor.get(Key.ShadowMode).enum

    @property
    def shadow_color(self) -> Descriptor:
        """Shadow color value."""
        return self.descriptor.get(Key.ShadowColor)

    @property
    def shadow_opacity(self) -> float:
        """Shadow opacity value in percentage."""
        return float(self.descriptor.get(Key.ShadowOpacity, 50.0))

    @property
    def bevel_type(self) -> bytes:
        """Bevel type, one of `SoftMatte`, `HardLight`, `SoftLight`."""
        return self.descriptor.get(Key.BevelTechnique).enum

    @property
    def bevel_style(self) -> bytes:
        """
        Bevel style, one of `OuterBevel`, `InnerBevel`, `Emboss`,
        `PillowEmboss`, or `StrokeEmboss`.
        """
        return self.descriptor.get(Key.BevelStyle).enum

    @property
    def altitude(self) -> float:
        """Altitude value in angle."""
        return float(self.descriptor.get(Key.LocalLightingAltitude, 30.0))

    @property
    def depth(self) -> float:
        """Depth value in percentage."""
        return float(self.descriptor.get(Key.StrengthRatio, 0.0))

    @property
    def size(self) -> float:
        """Size value in pixel."""
        return float(self.descriptor.get(Key.Blur, 0.0))

    @property
    def direction(self) -> bytes:
        """Direction, either `StampIn` or `StampOut`."""
        return self.descriptor.get(Key.BevelDirection).enum

    @property
    def contour(self) -> Descriptor:
        """Contour configuration."""
        return self.descriptor.get(Key.TransferSpec)

    @property
    def anti_aliased(self) -> bool:
        """Anti-aliased."""
        return bool(self.descriptor.get(b"antialiasGloss"))

    @property
    def soften(self) -> float:
        """Soften value in pixels."""
        return float(self.descriptor.get(Key.Softness, 0.0))

    @property
    def use_shape(self) -> bool:
        """Using shape."""
        return bool(self.descriptor.get(b"useShape"))

    @property
    def use_texture(self) -> bool:
        """Using texture."""
        return bool(self.descriptor.get(b"useTexture"))


@register(Klass.ChromeFX.value)
class Satin(_Effect, _ColorMixin):
    """Satin effect"""

    @property
    def anti_aliased(self) -> bool:
        """Anti-aliased."""
        return bool(self.descriptor.get(Key.AntiAlias))

    @property
    def inverted(self) -> bool:
        """Inverted."""
        return bool(self.descriptor.get(Key.Invert))

    @property
    def angle(self) -> float:
        """Angle value in degrees."""
        return float(self.descriptor.get(Key.LocalLightingAngle, 0.0))

    @property
    def distance(self) -> float:
        """Distance value in pixels."""
        return float(self.descriptor.get(Key.Distance, 120.0))

    @property
    def size(self) -> float:
        """Size value in pixel."""
        return float(self.descriptor.get(Key.Blur, 120.0))

    @property
    def contour(self) -> Descriptor:
        """Contour configuration."""
        return self.descriptor.get(Key.MappingShape)
