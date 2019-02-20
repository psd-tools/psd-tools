"""
Effects module.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools.constants import TaggedBlockID, DescriptorClassID
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
            if key in (b'masterFXSwitch', DescriptorClassID.SCALE):
                continue
            value = self._data[key]
            if not isinstance(value, List):
                value = [value]
            for item in value:
                if not item.get(DescriptorClassID.ENABLED):
                    continue
                kls = _TYPES.get(item.classID)
                assert kls is not None
                self._items.append(kls(item, layer._psd.image_resources))

    @property
    def scale(self):
        """Scale value."""
        return self._data.get(DescriptorClassID.SCALE).value

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
        return bool(self.value.get(DescriptorClassID.ENABLED))

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
        return self.value.get(DescriptorClassID.OPACITY).value

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
        return self.value.get(DescriptorClassID.COLOR)

    @property
    def blend_mode(self):
        """Effect blending mode."""
        mode = self.value.get(DescriptorClassID.MODE)
        return mode.enum.name.lower().replace('blend_', '')


class _ChokeNoiseMixin(_ColorMixin):
    @property
    def choke(self):
        """Choke level."""
        return self.value.get(DescriptorClassID.CHOKE).value

    @property
    def size(self):
        """Size in pixels."""
        return self.value.get(DescriptorClassID.BLUR).value

    @property
    def noise(self):
        """Noise level."""
        return self.value.get(DescriptorClassID.NOISE).value

    @property
    def anti_aliased(self):
        """Angi-aliased."""
        return bool(self.value.get(DescriptorClassID.ANTI_ALIASED))

    @property
    def contour(self):
        """Contour configuration."""
        return self.value.get(DescriptorClassID.STOP_OPACITY)


class _AngleMixin(object):
    @property
    def use_global_light(self):
        """Using global light."""
        return bool(self.value.get(DescriptorClassID.USE_GLOBAL_LIGHT))

    @property
    def angle(self):
        """Angle value."""
        if self.use_global_light:
            return self._image_resources.get_data('global_angle', 30.0)
        return self.value.get(DescriptorClassID.LIGHT_ANGLE).value


class _GradientMixin(object):
    @property
    def gradient(self):
        """Gradient configuration."""
        return self.value.get(DescriptorClassID.GRADIENT_CONFIG)


class _PatternMixin(object):
    @property
    def pattern(self):
        """Pattern config."""
        # TODO: Expose nested property.
        return self.value.get(DescriptorClassID.PATTERN)


class _ShadowEffect(_Effect, _ChokeNoiseMixin, _AngleMixin):
    """Base class for shadow effect."""
    @property
    def distance(self):
        """Distance."""
        return self.value.get(DescriptorClassID.DISTANCE).value


class _GlowEffect(_Effect, _ChokeNoiseMixin, _GradientMixin):
    """Base class for glow effect."""
    @property
    def glow_type(self):
        """Glow type. 'softer' or 'precise'."""
        value = self.value.get(DescriptorClassID.GLOW_TYPE).enum.name.lower()
        value = value.replace('bevel_', '')
        return {'smooth': 'softer'}.get(value, 'precise')

    @property
    def quality_range(self):
        """Quality range."""
        return self.value.get(DescriptorClassID.QUARYTY_RANGE).value

    @property
    def quality_jitter(self):
        """Quality jitter"""
        return self.value.get(DescriptorClassID.QUALITY_JITTER).value


class _OverlayEffect(_Effect):
    pass


class _AlignScaleMixin(object):
    @property
    def blend_mode(self):
        """Effect blending mode."""
        mode = self.value.get(DescriptorClassID.MODE)
        return mode.enum.name.lower().replace('blend_', '')

    @property
    def scale(self):
        """Scale value."""
        return self.value.get(DescriptorClassID.SCALE).value

    @property
    def aligned(self):
        """Aligned."""
        return bool(self.value.get(DescriptorClassID.ALIGNED))


@register(DescriptorClassID.DROP_SHADOW)
class DropShadow(_ShadowEffect):
    @property
    def layer_knocks_out(self):
        """Layers are knocking out."""
        return bool(self.value.get(b'layerConceals'))


@register(DescriptorClassID.INNER_SHADOW)
class InnerShadow(_ShadowEffect):
    pass


@register(DescriptorClassID.OUTER_GLOW)
class OuterGlow(_GlowEffect):
    @property
    def spread(self):
        return self.value.get(DescriptorClassID.QUALITY_JITTER).value


@register(DescriptorClassID.INNER_GLOW)
class InnerGlow(_GlowEffect):
    @property
    def glow_source(self):
        """Elements source, 'edge' or 'center'."""
        value = self.value.get(DescriptorClassID.GLOW_SOURCE).enum.name
        value = value.lower().replace('glow_source_', '')
        return value


@register(DescriptorClassID.COLOR_OVERLAY)
class ColorOverlay(_OverlayEffect, _ColorMixin):
    pass


@register(DescriptorClassID.GRADIENT_OVERLAY)
class GradientOverlay(_OverlayEffect, _AlignScaleMixin, _GradientMixin):
    @property
    def angle(self):
        """Angle value."""
        return self.value.get(DescriptorClassID.ANGLE).value

    @property
    def type(self):
        """
        Gradient type, one of `linear`, `radial`, `angle`, `reflected`, or
        `diamond`.
        """
        value = self.value.get(DescriptorClassID.TYPE).enum.name.lower()
        return value.replace('gradient_', '')

    @property
    def reversed(self):
        """Reverse flag."""
        return bool(self.value.get(DescriptorClassID.REVERSED))

    @property
    def dithered(self):
        """Dither flag."""
        return bool(self.value.get(DescriptorClassID.DITHERED))

    @property
    def offset(self):
        """Offset value."""
        return self.value.get(DescriptorClassID.OFFSET)


@register(b'patternFill')
class PatternOverlay(_OverlayEffect, _AlignScaleMixin, _PatternMixin):
    @property
    def phase(self):
        """Phase value in Point."""
        return self.value.get(b'phase')


@register(DescriptorClassID.STROKE)
class Stroke(_Effect, _ColorMixin, _PatternMixin, _GradientMixin):

    @property
    def position(self):
        """Position of the stroke, `inner`, `outer`, or `center`."""
        value = self.value.get(b'Styl')
        return value.enum.name.lower().replace('stroke_', '')

    @property
    def fill_type(self):
        """Fill type, solid-color, gradient, or pattern."""
        return self.value.get(b'PntT').enum.name.lower().replace('_', '-')

    @property
    def size(self):
        """Size value."""
        return self.value.get(b'Sz  ').value

    @property
    def overprint(self):
        """Overprint flag."""
        return bool(self.value.get(b'overprint'))


@register(DescriptorClassID.BEVEL_EMBOSS)
class BevelEmboss(_Effect, _AngleMixin):

    @property
    def highlight_mode(self):
        """Highlight blending mode."""
        value = self.value.get(b'hglM').enum
        value = value.decode() if isinstance(value, bytes) else value.name
        return value.lower().replace('blend_', '').replace('_', '-')

    @property
    def highlight_color(self):
        """Highlight color value."""
        return self.value.get(b'hglC')

    @property
    def highlight_opacity(self):
        """Highlight opacity value."""
        return self.value.get(b'hglO').value

    @property
    def shadow_mode(self):
        """Shadow blending mode."""
        value = self.value.get(b'sdwM').enum
        value = value.decode() if isinstance(value, bytes) else value.name
        return value.lower().replace('blend_', '').replace('_', '-')

    @property
    def shadow_color(self):
        """Shadow color value."""
        return self.value.get(b'sdwC')

    @property
    def shadow_opacity(self):
        """Shadow opacity value."""
        return self.value.get(b'sdwO').value

    @property
    def bevel_type(self):
        """Bevel type, one of `smooth`, `chiesel-hard`, `chiesel-soft`."""
        value = self.value.get(b'bvlT').enum.name.lower()
        return value.replace('bevel_', '').replace('_', '-')

    @property
    def bevel_style(self):
        """
        Bevel style, one of `outer`, `inner`, `emboss`,
        `pillow-emboss`, or `stroke-emboss`.
        """
        value = self.value.get(b'bvlS').enum.name.lower()
        return value.replace('bevel_style_', '').replace('_', '-')

    @property
    def altitude(self):
        """Altitude value."""
        return self.value.get(b'Lald').value

    @property
    def depth(self):
        """Depth value."""
        return self.value.get(b'srgR').value

    @property
    def size(self):
        """Size value in pixel."""
        return self.value.get(b'blur').value

    @property
    def direction(self):
        """Direction, either `in` or `out`."""
        return self.value.get(b'bvlD').enum.name.lower()

    @property
    def contour(self):
        """Contour configuration."""
        return self.value.get(b'TrnS')

    @property
    def anti_aliased(self):
        """Anti-aliased."""
        return bool(self.value.get(b'antialiasGloss'))

    @property
    def soften(self):
        """Soften value."""
        return self.value.get(b'Sftn').value

    @property
    def use_shape(self):
        """Using shape."""
        return bool(self.value.get(b'useShape'))

    @property
    def use_texture(self):
        """Using texture."""
        return bool(self.value.get(b'useTexture'))


@register(DescriptorClassID.SATIN)
class Satin(_Effect, _ColorMixin):
    """ Satin effect """
    @property
    def anti_aliased(self):
        """Anti-aliased."""
        return bool(self.value.get(b'AntA'))

    @property
    def inverted(self):
        """Inverted."""
        return bool(self.value.get(b'Invr'))

    @property
    def angle(self):
        """Angle value."""
        return self.value.get(b'lagl').value

    @property
    def distance(self):
        """Distance value."""
        return self.value.get(b'Dstn').value

    @property
    def size(self):
        """Size value in pixel."""
        return self.value.get(b'blur').value

    @property
    def contour(self):
        """Contour configuration."""
        return self.value.get(b'MpgS')
