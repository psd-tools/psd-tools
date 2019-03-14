"""
Effects module.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools.constants import TaggedBlockID
from psd_tools.terminology import Klass, Enum, Key
from psd_tools.utils import new_registry
from psd_tools.psd.base import ValueElement
from psd_tools.psd.descriptor import List

logger = logging.getLogger(__name__)


_TYPES, register = new_registry()


class Effects(object):
    """
    List-like effects.
    """
    def __init__(self, layer):
        self._data = None
        for tag in (
            TaggedBlockID.OBJECT_BASED_EFFECTS_LAYER_INFO,
            TaggedBlockID.OBJECT_BASED_EFFECTS_LAYER_INFO_V0,
            TaggedBlockID.OBJECT_BASED_EFFECTS_LAYER_INFO_V1,
        ):
            if tag in layer.tagged_blocks:
                self._data = layer.tagged_blocks.get_data(tag)
                break

        self._items = []
        for key in (self._data or []):
            if key in (b'masterFXSwitch', Key.Scale.value):
                continue
            value = self._data[key]
            if not isinstance(value, List):
                value = [value]
            for item in value:
                if not item.get(Key.Enabled):
                    continue
                kls = _TYPES.get(item.classID)
                assert kls is not None, 'kls not found for %r' % item.classID
                self._items.append(kls(item, layer._psd.image_resources))

    @property
    def scale(self):
        """Scale value."""
        return self._data.get(Key.Scale).value

    @property
    def enabled(self):
        """Whether if all the effects are enabled.

        :rtype: bool
        """
        return bool(self._data.get(b'masterFXSwitch'))

    @property
    def items(self):
        return self._items

    def __len__(self):
        return self._items.__len__()

    def __iter__(self):
        return self._items.__iter__()

    def __getitem__(self, key):
        return self._items.__getitem__(key)

    # def __setitem__(self, key, value):
    #     return self._items.__setitem__(key, value)

    # def __delitem__(self, key):
    #     return self._items.__delitem__(key)

    def __repr__(self):
        return '%s(%s%s)' % (
            self.__class__.__name__,
            '' if self.enabled else 'disabled ',
            ' '.join(x.__class__.__name__.lower() for x in self)
        )


class _Effect(object):
    """Base Effect class."""
    def __init__(self, value, image_resources):
        self.value = value
        self._image_resources = image_resources

    @property
    def enabled(self):
        """Whether if the effect is enabled."""
        return bool(self.value.get(Key.Enabled))

    @property
    def present(self):
        """Whether if the effect is present in Photoshop UI."""
        return bool(self.value.get(b'present'))

    @property
    def shown(self):
        """Whether if the effect is shown in dialog."""
        return bool(self.value.get(b'showInDialog'))

    @property
    def opacity(self):
        """Layer effect opacity in percentage."""
        return self.value.get(Key.Opacity).value

    def __repr__(self):
        return self.__class__.__name__

    def _repr_pretty_(self, p, cycle):
        if cycle:
            return self.__repr__()
        p.text(self.__repr__())


class _ColorMixin(object):
    @property
    def color(self):
        """Color."""
        return self.value.get(Key.Color)

    @property
    def blend_mode(self):
        """Effect blending mode."""
        return self.value.get(Key.Mode).get_name()


class _ChokeNoiseMixin(_ColorMixin):
    @property
    def choke(self):
        """Choke level."""
        return self.value.get(Key.ChokeMatte).value

    @property
    def size(self):
        """Size in pixels."""
        return self.value.get(Key.Blur).value

    @property
    def noise(self):
        """Noise level."""
        return self.value.get(Key.Noise).value

    @property
    def anti_aliased(self):
        """Angi-aliased."""
        return bool(self.value.get(Key.AntiAlias))

    @property
    def contour(self):
        """Contour configuration."""
        return self.value.get(Key.TransferSpec)


class _AngleMixin(object):
    @property
    def use_global_light(self):
        """Using global light."""
        return bool(self.value.get(Key.UseGlobalAngle))

    @property
    def angle(self):
        """Angle value."""
        if self.use_global_light:
            return self._image_resources.get_data('global_angle', 30.0)
        return self.value.get(Key.LocalLightingAngle).value


class _GradientMixin(object):
    @property
    def gradient(self):
        """Gradient configuration."""
        return self.value.get(Key.Gradient)


class _PatternMixin(object):
    @property
    def pattern(self):
        """Pattern config."""
        # TODO: Expose nested property.
        return self.value.get(b'Ptrn')  # Enum.Pattern. Seems a bug.


class _ShadowEffect(_Effect, _ChokeNoiseMixin, _AngleMixin):
    """Base class for shadow effect."""
    @property
    def distance(self):
        """Distance."""
        return self.value.get(Key.Distance).value


class _GlowEffect(_Effect, _ChokeNoiseMixin, _GradientMixin):
    """Base class for glow effect."""
    @property
    def glow_type(self):
        """Glow type."""
        return self.value.get(Key.GlowTechnique).get_name()

    @property
    def quality_range(self):
        """Quality range."""
        return self.value.get(Key.InputRange).value

    @property
    def quality_jitter(self):
        """Quality jitter"""
        return self.value.get(Key.ShadingNoise).value


class _OverlayEffect(_Effect):
    pass


class _AlignScaleMixin(object):
    @property
    def blend_mode(self):
        """Effect blending mode."""
        return self.value.get(Key.Mode).get_name()

    @property
    def scale(self):
        """Scale value."""
        return self.value.get(Key.Scale).value

    @property
    def aligned(self):
        """Aligned."""
        return bool(self.value.get(Key.Alignment))


@register(Klass.DropShadow.value)
class DropShadow(_ShadowEffect):
    @property
    def layer_knocks_out(self):
        """Layers are knocking out."""
        return bool(self.value.get(b'layerConceals'))


@register(Klass.InnerShadow.value)
class InnerShadow(_ShadowEffect):
    pass


@register(Klass.OuterGlow.value)
class OuterGlow(_GlowEffect):
    @property
    def spread(self):
        return self.value.get(Key.ShadingNoise).value


@register(Klass.InnerGlow.value)
class InnerGlow(_GlowEffect):
    @property
    def glow_source(self):
        """Elements source."""
        return self.value.get(Key.InnerGlowSource).get_name()


@register(Klass.SolidFill.value)
class ColorOverlay(_OverlayEffect, _ColorMixin):
    pass


@register(b'GrFl')  # Equalt to Enum.GradientFill. This seems a bug.
class GradientOverlay(_OverlayEffect, _AlignScaleMixin, _GradientMixin):
    @property
    def angle(self):
        """Angle value."""
        return self.value.get(Key.Angle).value

    @property
    def type(self):
        """
        Gradient type, one of `linear`, `radial`, `angle`, `reflected`, or
        `diamond`.
        """
        return self.value.get(Key.Type).get_name()

    @property
    def reversed(self):
        """Reverse flag."""
        return bool(self.value.get(Key.Reverse))

    @property
    def dithered(self):
        """Dither flag."""
        return bool(self.value.get(Key.Dither))

    @property
    def offset(self):
        """Offset value."""
        return self.value.get(Key.Offset)


@register(b'patternFill')
class PatternOverlay(_OverlayEffect, _AlignScaleMixin, _PatternMixin):
    @property
    def phase(self):
        """Phase value in Point."""
        return self.value.get(b'phase')


@register(Klass.FrameFX.value)
class Stroke(_Effect, _ColorMixin, _PatternMixin, _GradientMixin):

    @property
    def position(self):
        """
        Position of the stroke, InsetFrame, OutsetFrame, or CenteredFrame.
        """
        return self.value.get(Key.Style).get_name()

    @property
    def fill_type(self):
        """Fill type, SolidColor, Gradient, or Pattern."""
        return self.value.get(Key.PaintType).get_name()

    @property
    def size(self):
        """Size value."""
        return self.value.get(Key.SizeKey).value

    @property
    def overprint(self):
        """Overprint flag."""
        return bool(self.value.get(b'overprint'))


@register(Klass.BevelEmboss.value)
class BevelEmboss(_Effect, _AngleMixin):

    @property
    def highlight_mode(self):
        """Highlight blending mode."""
        return self.value.get(Key.HighlightMode).get_name()

    @property
    def highlight_color(self):
        """Highlight color value."""
        return self.value.get(Key.HighlightColor)

    @property
    def highlight_opacity(self):
        """Highlight opacity value."""
        return self.value.get(Key.HighlightOpacity).value

    @property
    def shadow_mode(self):
        """Shadow blending mode."""
        return self.value.get(Key.ShadowMode).get_name()

    @property
    def shadow_color(self):
        """Shadow color value."""
        return self.value.get(Key.ShadowColor)

    @property
    def shadow_opacity(self):
        """Shadow opacity value."""
        return self.value.get(Key.ShadowOpacity).value

    @property
    def bevel_type(self):
        """Bevel type, one of `SoftMatte`, `HardLight`, `SoftLight`."""
        return self.value.get(Key.BevelTechnique).get_name()

    @property
    def bevel_style(self):
        """
        Bevel style, one of `OuterBevel`, `InnerBevel`, `Emboss`,
        `PillowEmboss`, or `StrokeEmboss`.
        """
        return self.value.get(Key.BevelStyle).get_name()

    @property
    def altitude(self):
        """Altitude value."""
        return self.value.get(Key.LocalLightingAltitude).value

    @property
    def depth(self):
        """Depth value."""
        return self.value.get(Key.StrengthRatio).value

    @property
    def size(self):
        """Size value in pixel."""
        return self.value.get(Key.Blur).value

    @property
    def direction(self):
        """Direction, either `StampIn` or `StampOut`."""
        return self.value.get(Key.BevelDirection).get_name()

    @property
    def contour(self):
        """Contour configuration."""
        return self.value.get(Key.TransferSpec)

    @property
    def anti_aliased(self):
        """Anti-aliased."""
        return bool(self.value.get(b'antialiasGloss'))

    @property
    def soften(self):
        """Soften value."""
        return self.value.get(Key.Softness).value

    @property
    def use_shape(self):
        """Using shape."""
        return bool(self.value.get(b'useShape'))

    @property
    def use_texture(self):
        """Using texture."""
        return bool(self.value.get(b'useTexture'))


@register(Klass.ChromeFX.value)
class Satin(_Effect, _ColorMixin):
    """ Satin effect """
    @property
    def anti_aliased(self):
        """Anti-aliased."""
        return bool(self.value.get(Key.AntiAlias))

    @property
    def inverted(self):
        """Inverted."""
        return bool(self.value.get(Key.Invert))

    @property
    def angle(self):
        """Angle value."""
        return self.value.get(Key.LocalLightingAngle).value

    @property
    def distance(self):
        """Distance value."""
        return self.value.get(Key.Distance).value

    @property
    def size(self):
        """Size value in pixel."""
        return self.value.get(Key.Blur).value

    @property
    def contour(self):
        """Contour configuration."""
        return self.value.get(Key.MappingShape)
