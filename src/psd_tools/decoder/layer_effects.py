# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, print_function
import warnings
import io

from psd_tools.decoder import decoders
from psd_tools.decoder.actions import decode_descriptor, UnknownOSType
from psd_tools.decoder.color import decode_color
from psd_tools.exceptions import Error
from psd_tools.utils import read_fmt
from psd_tools.constants import EffectOSType, BlendMode
from psd_tools.debug import pretty_namedtuple

_effect_info_decoders, register = decoders.new_registry()


Effects = pretty_namedtuple('Effects', 'version effects_count effects_list')
_LayerEffect = pretty_namedtuple('LayerEffect', 'effect_type effect_info')
ObjectBasedEffects = pretty_namedtuple('ObjectBasedEffects', 'version descriptor_version descriptor')

CommonStateInfo = pretty_namedtuple('CommonStateInfo', 'version visible unused')
ShadowInfo = pretty_namedtuple('ShadowInfo', 'version enabled '
                                             'blend_mode color opacity '
                                             'angle use_global_angle '
                                             'distance intensity blur '
                                             'native_color')
OuterGlowInfo = pretty_namedtuple('OuterGlowInfo', 'version enabled '
                                                   'blend_mode opacity color '
                                                   'intensity blur '
                                                   'native_color')
InnerGlowInfo = pretty_namedtuple('InnerGlowInfo', 'version enabled '
                                                   'blend_mode opacity color '
                                                   'intensity blur '
                                                   'invert native_color')
BevelInfo = pretty_namedtuple('BevelInfo', 'version enabled '
                                           'bevel_style '
                                           'depth direction blur '
                                           'angle use_global_angle '
                                           'highlight_blend_mode highlight_color highlight_opacity '
                                           'shadow_blend_mode shadow_color shadow_opacity '
                                           'real_highlight_color real_shadow_color')
SolidFillInfo = pretty_namedtuple('SolidFillInfo', 'version enabled '
                                                   'blend_mode color opacity '
                                                   'native_color')


class LayerEffect(_LayerEffect):

    def __repr__(self):
        return "LayerEffect(%s %s, %s)" % (self.effect_type, EffectOSType.name_of(self.effect_type),
                                           self.effect_info)

    def _repr_pretty_(self, p, cycle):
        # IS NOT TESTED!!
        if cycle:
            p.text('LayerEffect(...)')
        else:
            with p.group(1, 'LayerEffect(', ')'):
                p.breakable()
                p.text("%s %s," % (self.effect_type, EffectOSType.name_of(self.effect_type)))
                p.breakable()
                p.pretty(self.effect_info)


def decode(effects):
    """
    Reads and decodes info about layer effects.
    """
    fp = io.BytesIO(effects)

    version, effects_count = read_fmt("HH", fp)

    effects_list = []
    for idx in range(effects_count):
        sig = fp.read(4)
        if sig != b'8BIM':
            raise Error("Error parsing layer effect: invalid signature (%r)" % sig)

        effect_type = fp.read(4)
        if not EffectOSType.is_known(effect_type):
            warnings.warn("Unknown effect type (%s)" % effect_type)

        effect_info_length = read_fmt("I", fp)[0]
        effect_info = fp.read(effect_info_length)

        decoder = _effect_info_decoders.get(effect_type, lambda data: data)
        effects_list.append(LayerEffect(effect_type, decoder(effect_info)))

    return Effects(version, effects_count, effects_list)

def decode_object_based(effects):
    """
    Reads and decodes info about object-based layer effects.
    """
    fp = io.BytesIO(effects)

    version, descriptor_version = read_fmt("II", fp)
    try:
        descriptor = decode_descriptor(None, fp)
    except UnknownOSType as e:
        warnings.warn("Ignoring object-based layer effects tagged block (%s)" % e)
        return effects

    return ObjectBasedEffects(version, descriptor_version, descriptor)

def _read_blend_mode(fp):
    sig = fp.read(4)
    if sig != b'8BIM':
        raise Error("Error parsing layer effect: invalid signature (%r)" % sig)

    blend_mode = fp.read(4)
    if not BlendMode.is_known(blend_mode):
        warnings.warn("Unknown blend mode (%s)" % blend_mode)

    return blend_mode


@register(EffectOSType.COMMON_STATE)
def _decode_common_info(data):
    version, visible, unused = read_fmt("IBH", io.BytesIO(data))
    return CommonStateInfo(version, bool(visible), unused)


@register(EffectOSType.DROP_SHADOW)
@register(EffectOSType.INNER_SHADOW)
def _decode_shadow_info(data):
    fp = io.BytesIO(data)

    version, blur, intensity, angle, distance = read_fmt("IIIiI", fp)
    color = decode_color(fp)
    blend_mode = _read_blend_mode(fp)
    enabled, use_global_angle, opacity = read_fmt("3B", fp)

    native_color = None
    if version == 2:
        native_color = decode_color(fp)

    return ShadowInfo(
        version, bool(enabled),
        blend_mode, color, opacity,
        angle, bool(use_global_angle),
        distance, intensity, blur,
        native_color
    )


@register(EffectOSType.OUTER_GLOW)
def _decode_outer_glow_info(data):
    fp = io.BytesIO(data)

    version, blur, intensity = read_fmt("3I", fp)
    color = decode_color(fp)
    blend_mode = _read_blend_mode(fp)
    enabled, opacity = read_fmt("2B", fp)

    native_color = None
    if version == 2:
        native_color = decode_color(fp)

    return OuterGlowInfo(
        version, bool(enabled),
        blend_mode, opacity, color,
        intensity, blur,
        native_color
    )


@register(EffectOSType.INNER_GLOW)
def _decode_inner_glow_info(data):
    fp = io.BytesIO(data)

    version, blur, intensity = read_fmt("3I", fp)
    color = decode_color(fp)
    blend_mode = _read_blend_mode(fp)
    enabled, opacity = read_fmt("2B", fp)

    invert = None
    native_color = None
    if version == 2:
        invert = bool(read_fmt("B", fp)[0])
        native_color = decode_color(fp)

    return InnerGlowInfo(
        version, bool(enabled),
        blend_mode, opacity, color,
        intensity, blur,
        invert, native_color
    )


@register(EffectOSType.BEVEL)
def _decode_bevel_info(data):
    fp = io.BytesIO(data)

    version, angle, depth, blur = read_fmt("IiII", fp)

    highlight_blend_mode = _read_blend_mode(fp)
    shadow_blend_mode = _read_blend_mode(fp)

    highlight_color = decode_color(fp)
    shadow_color = decode_color(fp)

    bevel_style, highlight_opacity, shadow_opacity = read_fmt("3B", fp)
    enabled, use_global_angle, direction = read_fmt("3B", fp)

    real_highlight_color = None
    real_shadow_color = None
    if version == 2:
        real_highlight_color = decode_color(fp)
        real_shadow_color = decode_color(fp)

    return BevelInfo(
        version, bool(enabled),
        bevel_style,
        depth, direction, blur,
        angle, bool(use_global_angle),
        highlight_blend_mode, highlight_color, highlight_opacity,
        shadow_blend_mode, shadow_color, shadow_opacity,
        real_highlight_color, real_shadow_color
    )


@register(EffectOSType.SOLID_FILL)
def _decode_solid_fill_info(data):
    fp = io.BytesIO(data)

    version = read_fmt("I", fp)[0]
    blend_mode = _read_blend_mode(fp)
    color = decode_color(fp)
    opacity, enabled = read_fmt("2B", fp)

    native_color = decode_color(fp)

    return SolidFillInfo(
        version, bool(enabled),
        blend_mode, color, opacity,
        native_color
    )

