# -*- coding: utf-8 -*-
"""Layer effects API.

Class objects in this class corresponds to information in the layer effect
dialog in Photoshop.

Usage::

    for effect in psd.layers[0].effects:
        print(effect.name(), effect.dict())

"""
from __future__ import absolute_import
import inspect
import logging
from psd_tools.user_api.actions import translate
from psd_tools.constants import TaggedBlock

logger = logging.getLogger(__name__)


# List of blending mode keys and names.
BLEND_MODES = {
    b'Nrml': 'normal',
    b'Dslv': 'dissolve',
    b'Drkn': 'darken',
    b'Mltp': 'multiply',
    b'CBrn': 'color burn',
    b'linearBurn': 'linear burn',
    b'darkerColor': 'darken',
    b'Lghn': 'lighten',
    b'Scrn': 'screen',
    b'CDdg': 'color dodge',
    b'linearDodge': 'linear dodge',
    b'lighterColor': 'lighter color',
    b'Ovrl': 'overlay',
    b'SftL': 'soft light',
    b'HrdL': 'hard light',
    b'vividLight': 'vivid light',
    b'linearLight': 'linear light',
    b'pinLight': 'pin light',
    b'hardMix': 'hard mix',
    b'Dfrn': 'difference',
    b'Xclu': 'exclusion',
    b'blendSubtraction': 'subtract',
    b'blendDivide': 'divide',
    b'H   ': 'hue',
    b'Strt': 'saturation',
    b'Clr ': 'color',
    b'Lmns': 'luminosity',
}


def get_effects(self):
    """Return effects block from the layer."""
    blocks = self._tagged_blocks
    effects = blocks.get(
        TaggedBlock.OBJECT_BASED_EFFECTS_LAYER_INFO,
        blocks.get(
            TaggedBlock.OBJECT_BASED_EFFECTS_LAYER_INFO_V0,
            blocks.get(TaggedBlock.OBJECT_BASED_EFFECTS_LAYER_INFO_V0)))
    if not effects:
        return None
    descriptor = translate(effects.descriptor)
    return Effects(descriptor)


class _BaseEffect(object):
    """Base class for effect."""
    def __init__(self, info):
        self._info = info

    @property
    def enabled(self):
        """Whether if the effect is enabled.

        :rtype: bool
        """
        return self._info.get(b'enab', True)

    @property
    def present(self):
        """Whether if the effect is present in UI.

        :rtype: bool
        """
        return self._info.get(b'present')

    @property
    def show_in_dialog(self):
        """Whether if the effect is shown in dialog.

        :rtype: bool
        """
        return self._info.get(b'showInDialog')

    @property
    def blend_mode(self):
        """Effect blending mode.

        :returns: blending mode
        :rtype: str

        Blending mode is one of the following.

          - normal
          - dissolve
          - darken
          - multiply
          - color burn
          - linear burn
          - darken
          - lighten
          - screen
          - color dodge
          - linear dodge
          - lighter color
          - overlay
          - soft light
          - hard light
          - vivid light
          - linear light
          - pin light
          - hard mix
          - difference
          - exclusion
          - subtract
          - divide
          - hue
          - saturation
          - color
          - luminosity
        """
        return BLEND_MODES.get(self._info.get(b'Md  ', b'Nrml'), 'normal')

    @property
    def opacity(self):
        """Layer effect opacity in percentage.

        :rtype: float
        """
        return self._info.get(b'Opct', 100.0)

    def name(self):
        """Layer effect name.

        :rtype: str
        """
        return self.__class__.__name__

    def get(self, key, default=None):
        """Get attribute in the low-level structure.

        :param key: property key
        :type key: bytes
        :param default: default value to return
        """
        return self._info.get(key, default)

    def properties(self):
        """Return a list of property names.

        :returns: list of properties.
        :rtype: list
        """
        return [k for (k, v) in inspect.getmembers(
            self.__class__, lambda x: isinstance(x, property))]

    def dict(self):
        """Convert to dict."""
        return {k: getattr(self, k) for k in self.properties()}

    def __repr__(self):
        return "<%s>" % (self.name(),)


class _ColorMixin(object):
    @property
    def color(self):
        """Color.

        :returns: color tuple.
        :rtype: psd_tools.user_api.actions.Color
        """
        return self._info.get(b'Clr ')

class _ChokeNoiseMixin(_ColorMixin):
    @property
    def choke(self):
        """Choke level."""
        return self._info.get(b'Ckmt', 0.0)

    @property
    def size(self):
        """Size in pixels."""
        return self._info.get(b'blur', 41.0)

    @property
    def noise(self):
        """Noise level."""
        return self._info.get(b'Nose', 0.0)

    @property
    def anti_aliased(self):
        """Angi-aliased."""
        return self._info.get(b'AntA', False)

    @property
    def contour(self):
        """Contour configuration."""
        return self._info.get(b'TrnS')



class _ShadowEffect(_BaseEffect, _ChokeNoiseMixin):
    """Base class for shadow effect."""
    @property
    def use_global_light(self):
        """Using global light."""
        return self._info.get(b'uglg', True)

    @property
    def angle(self):
        """Angle."""
        return self._info.get(b'lagl', 90.0)

    @property
    def distance(self):
        """Distance."""
        return self._info.get(b'Dstn', 18.0)


class DropShadow(_ShadowEffect):
    """DropShadow effect."""
    @property
    def layer_knocks_out(self):
        """Layers are knocking out."""
        return self._info.get(b'layerConceals', True)


class InnerShadow(_ShadowEffect):
    """InnerShadow effect."""
    pass


class _GlowEffect(_BaseEffect, _ChokeNoiseMixin):
    """Base class for glow effect."""
    @property
    def glow_type(self):
        """ Elements technique, softer or precise """
        return {b'SfBL': 'softer'}.get(self._info.get(b'GlwT', b'SfBL'),
                                       'precise')

    @property
    def quality_range(self):
        """Quality range."""
        return self._info.get(b'Inpr')

    @property
    def quality_jitter(self):
        """Quality jitter"""
        return self._info.get(b'ShdN')


class OuterGlow(_GlowEffect):
    """OuterGlow effect."""
    @property
    def spread(self):
        return self._info.get(b'ShdN')


class InnerGlow(_GlowEffect):
    """InnerGlow effect."""
    @property
    def glow_source(self):
        """ Elements source, center or edge """
        return {b'SrcE': 'edge'}.get(self._info.get(b'glwS', b'SrcE'),
                                     'center')


class _OverlayEffect(_BaseEffect):
    pass


class _AlignScaleMixin(object):
    @property
    def scale(self):
        """Scale value."""
        return self._info.get(b'Scl ')

    @property
    def aligned(self):
        """Aligned."""
        return self._info.get(b'Algn')


class ColorOverlay(_OverlayEffect, _ColorMixin):
    """ColorOverlay effect."""
    pass


class GradientOverlay(_OverlayEffect, _AlignScaleMixin):
    """GradientOverlay effect."""
    @property
    def gradient(self):
        """Gradient configuration.

        :rtype: psd_tools.user_api.actions.Gradient
        """
        # TODO: Expose nested property.
        return self._info.get(b'Grad')

    @property
    def angle(self):
        """Angle value."""
        return self._info.get(b'Angl', 30.0)

    @property
    def type(self):
        """Gradient type, linear or radial."""
        # TODO: Rephrase bytes. b'Lnr ': 'linear'.
        return self._info.get(b'Type', b'Lnr ')

    @property
    def reversed(self):
        """Reverse flag."""
        return self._info.get(b'Rvrs', False)

    @property
    def dithered(self):
        """Dither flag."""
        return self._info.get(b'Dthr', False)

    @property
    def offset(self):
        """Offset value."""
        return self._info.get(b'Ofst')


class PatternOverlay(_OverlayEffect, _AlignScaleMixin):
    """PatternOverlay effect."""
    @property
    def pattern(self):
        """Pattern config.

        :rtype: psd_tools.user_api.actions.Pattern
        """
        # TODO: Expose nested property.
        return self._info.get(b'Ptrn')

    @property
    def phase(self):
        """Phase value."""
        return self._info.get(b'phase')


class Stroke(_BaseEffect, _ColorMixin):
    """Stroke effect."""

    @property
    def position(self):
        """Position of the stroke."""
        # TODO: Rephrase bytes.
        return self._info.get(b'Styl', b'OutF')

    @property
    def fill_type(self):
        """Fill type, solid color, gradient, or pattern."""
        # TODO: Rephrase bytes. b'SClr': 'color'.
        return self._info.get(b'PntT', b'SClr')

    @property
    def size(self):
        """Size value."""
        return self._info.get(b'Sz ', 6.0)

    @property
    def overprint(self):
        """Overprint flag."""
        return self._info.get(b'overprint', False)


class BevelEmboss(_BaseEffect):
    """Bevel and Emboss effect."""
    @property
    def highlight_mode(self):
        """Highlight blending mode."""
        return BLEND_MODES.get(self._info.get(b'hglM', b'Nrml'), 'normal')

    @property
    def highlight_color(self):
        """Highlight color value."""
        return self._info.get(b'hglC')

    @property
    def highlight_opacity(self):
        """Highlight opacity value."""
        return self._info.get(b'hglO')

    @property
    def shadow_mode(self):
        """Shadow blending mode."""
        return BLEND_MODES.get(self._info.get(b'sdwM', b'Nrml'), 'normal')

    @property
    def shadow_color(self):
        """Shadow color value."""
        return self._info.get(b'sdwC')

    @property
    def shadow_opacity(self):
        """Shadow opacity value."""
        return self._info.get(b'sdwO')

    @property
    def bevel_type(self):
        """Bevel type."""
        # TODO: Rephrase bytes.
        return self._info.get(b'bvlT', b'SfBL')

    @property
    def bevel_style(self):
        """Bevel style, emboss or bevel."""
        # TODO: Rephrase bytes.
        return self._info.get(b'bvlS', b'Embs')

    @property
    def use_global_light(self):
        """Using global light."""
        return self._info.get(b'uglg', True)

    @property
    def angle(self):
        """Angle value."""
        return self._info.get(b'lagl', 90.0)

    @property
    def altitude(self):
        """Altitude value."""
        return self._info.get(b'Lald', 30.0)

    @property
    def depth(self):
        """Depth value."""
        return self._info.get(b'srgR', 100.0)

    @property
    def size(self):
        """Size value in pixel."""
        return self._info.get(b'blur', 41.0)

    @property
    def direction(self):
        """Direction."""
        # TODO: Rephrase bytes.
        return self._info.get(b'bvlD', b'In  ')

    @property
    def contour(self):
        """Contour configuration."""
        return self._info.get(b'TrnS')

    @property
    def anti_aliased(self):
        """Anti-aliased."""
        return self._info.get(b'antialiasGloss', False)

    @property
    def soften(self):
        """Soften value."""
        return self._info.get(b'Sftn', 0.0)

    @property
    def use_shape(self):
        """Using shape."""
        return self._info.get(b'useShape', False)

    @property
    def use_texture(self):
        """Using texture."""
        return self._info.get(b'useTexture', False)


class Satin(_BaseEffect, _ColorMixin):
    """ Satin effect """
    @property
    def anti_aliased(self):
        """Anti-aliased."""
        return self._info.get(b'AntA', True)

    @property
    def inverted(self):
        """Inverted."""
        return self._info.get(b'Invr', True)

    @property
    def angle(self):
        """Angle value."""
        return self._info.get(b'lagl', 90.0)

    @property
    def distance(self):
        """Distance value."""
        return self._info.get(b'Dstn', 250.0)

    @property
    def size(self):
        """Size value in pixel."""
        return self._info.get(b'blur', 250.0)

    @property
    def contour(self):
        """Contour configuration."""
        return self._info.get(b'MpgS')


class Effects(object):
    """Layer effects wrapper. Behaves like a list.

    Example::

        for effect in psd.layers[0].effects:
            print(effect.name())
    """
    _KEYS = {
        b'dropShadowMulti': DropShadow,
        b'DrSh': DropShadow,
        b'innerShadowMulti': InnerShadow,
        b'IrSh': InnerShadow,
        b'OrGl': OuterGlow,
        b'solidFillMulti': ColorOverlay,
        b'SoFi': ColorOverlay,
        b'gradientFillMulti': GradientOverlay,
        b'GrFl': GradientOverlay,
        b'patternFill': PatternOverlay,
        b'frameFXMulti': Stroke,
        b'FrFX': Stroke,
        b'IrGl': InnerGlow,
        b'ebbl': BevelEmboss,
        b'ChFX': Satin,
        }

    def __init__(self, descriptor):
        self._info = descriptor
        self.items = self._build_items()

    @property
    def scale(self):
        """Scale value."""
        return self._info.get(b'Scl ')

    @property
    def enabled(self):
        """Whether if all the effects are enabled.

        :rtype: bool
        """
        return self._info.get(b'masterFXSwitch', True)

    def _build_items(self):
        items = []
        for key in self._info:
            cls = self._KEYS.get(key, None)
            if not cls:
                continue
            if key.endswith(b'Multi'):
                for value in self._info[key]:
                    items.append(cls(value))
            else:
                items.append(cls(self._info[key]))
        return items

    def present_items(self):
        """List of effects present in Photoshop UI."""
        return [item for item in self.items if item.present]

    def enabled_items(self):
        """List of enabled effects."""
        if self.enabled:
            return [item for item in self.items
                    if getattr(item, 'enabled', False)]
        return []

    def __getitem__(self, index):
        return self.enabled_items()[index]

    def __len__(self):
        return len(self.enabled_items())

    def __repr__(self):
        return "%s" % (self.enabled_items(),)
