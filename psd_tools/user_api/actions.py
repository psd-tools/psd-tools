# -*- coding: utf-8 -*-
"""
A module for translating "Actions" format to User API objects.
"""
from __future__ import absolute_import

from collections import OrderedDict
from psd_tools.debug import pretty_namedtuple
from psd_tools.decoder.decoders import new_registry
from psd_tools.decoder.actions import (
    Descriptor, Reference, Property, UnitFloat, Double, Class, String,
    EnumReference, Boolean, Offset, Alias, List, Integer, Enum, Identifier,
    Index, Name, ObjectArray, ObjectArrayItem, RawData)
from psd_tools.decoder.tagged_blocks import (
    SolidColorSetting, PatternFillSetting, GradientFillSetting,
    VectorStrokeSetting, VectorMaskSetting, VectorStrokeContentSetting,
    ContentGeneratorExtraData, LevelsSettings, CurvesSettings, Exposure,
    Vibrance, HueSaturation, ColorBalance, BlackWhite, PhotoFilter,
    ChannelMixer, ColorLookup, Invert, Posterize, Threshold, SelectiveColor,
    GradientSettings, VectorOriginationData)
from psd_tools.decoder.layer_effects import ObjectBasedEffects
from psd_tools.user_api.effects import (
    GradientOverlay, PatternOverlay, ColorOverlay)
from psd_tools.user_api import adjustments, BBox

from psd_tools.user_api.shape import StrokeStyle, VectorMask, Origination


_translators, register = new_registry()
_desc_translators, desc_register = new_registry()

#: Point object, x and y attributes.
Point = pretty_namedtuple('Point', 'x y')

#: Shape object, contains list of points in curve.
Shape = pretty_namedtuple('Shape', 'name curve')

#: Pattern object.
Pattern = pretty_namedtuple('Pattern', 'name id')

_Gradient = pretty_namedtuple(
    'Gradient', 'desc_name name type smoothness colors transform')

#: StopColor in gradient.
StopColor = pretty_namedtuple('StopColor', 'color type location midpoint')

#: StopOpacity in gradient.
StopOpacity = pretty_namedtuple('StopOpacity', 'opacity location midpoint')


class Color(object):
    """Color picker point representing a single color.

    Example::

        color.name  # => rgb
        color.value # => (1.0, 1.0, 1.0)

    .. todo:: Add colorspace conversion support. Perhaps add ``rgb()`` method.
    """
    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __repr__(self):
        return "%s%s" % (self.name, self.value)


class Gradient(_Gradient):
    """Gradient object."""
    @property
    def short_name(self):
        """Short gradient name."""
        return self._name.split("=")[-1]


def translate(data):
    """Translate descriptor-based formats."""
    translator = _translators.get(type(data), lambda data: data)
    return translator(data)


@register(Descriptor)
def _translate_descriptor(data):
    translator = _desc_translators.get(data.classID,
                                       _translate_generic_descriptor)
    return translator(data)


@register(Reference)
@register(List)
def _translate_list(data):
    result = []
    for item in data.items:
        translator = _translators.get(type(item), lambda data: data)
        result.append(translator(item))
    return result


@register(Property)
def _translate_property(data):
    return data


# @register(UnitFloat)
@register(Double)
@register(String)
@register(Boolean)
@register(Alias)
@register(Integer)
@register(Enum)
@register(Identifier)
@register(Index)
@register(Name)
@register(RawData)
def _translate_value(data):
    return data.value


@register(ObjectBasedEffects)
def _translate_object_based_effects(data):
    return translate(data.descriptor)


@register(VectorStrokeSetting)
def _translate_vector_stroke_setting(data):
    return translate(data.data)


@register(VectorMaskSetting)
def _translate_vector_mask_setting(data):
    return VectorMask(data)


@register(VectorStrokeContentSetting)
def _translate_vector_stroke_content_setting(data):
    descriptor = translate(data.data)
    if b'Ptrn' in descriptor:
        return PatternOverlay(descriptor, None)
    elif b'Grdn' in descriptor:
        return GradientOverlay(descriptor, None)
    else:
        return ColorOverlay(descriptor, None)


@register(VectorOriginationData)
def _translate_vector_origination_data(data):
    return Origination(translate(data.data).get(b'keyDescriptorList')[0])


@register(SolidColorSetting)
def _translate_solid_color_setting(data):
    descriptor = translate(data.data)
    return ColorOverlay(descriptor, None)


@register(PatternFillSetting)
def _translate_pattern_fill_setting(data):
    descriptor = translate(data.data)
    return PatternOverlay(descriptor, None)


@register(GradientFillSetting)
def _translate_gradient_fill_setting(data):
    descriptor = translate(data.data)
    return GradientOverlay(descriptor, None)


@register(ContentGeneratorExtraData)
def _translate_content_generator_extra_data(data):
    descriptor = _translate_generic_descriptor(data.descriptor)
    return adjustments.BrightnessContrast(descriptor)


@register(LevelsSettings)
def _translate_levels_settings(data):
    return adjustments.Levels(data)


@register(CurvesSettings)
def _translate_curves_settings(data):
    return adjustments.Curves(data)


@register(Exposure)
def _translate_levels_settings(data):
    return adjustments.Exposure(data)


@register(Vibrance)
def _translate_vibrance(data):
    descriptor = _translate_generic_descriptor(data.descriptor)
    return adjustments.Vibrance(descriptor)


@register(HueSaturation)
def _translate_hue_saturation(data):
    return adjustments.HueSaturation(data)


@register(ColorBalance)
def _translate_color_balance(data):
    return adjustments.ColorBalance(data)


@register(BlackWhite)
def _translate_black_and_white(data):
    descriptor = _translate_generic_descriptor(data.descriptor)
    return adjustments.BlackWhite(descriptor)


@register(PhotoFilter)
def _translate_photo_filter(data):
    return adjustments.PhotoFilter(data)


@register(ChannelMixer)
def _translate_channel_mixer(data):
    return adjustments.ChannelMixer(data)


@register(ColorLookup)
def _translate_color_lookup(data):
    descriptor = _translate_generic_descriptor(data.descriptor)
    return adjustments.ColorLookup(descriptor)


@register(Invert)
def _translate_invert(data):
    return adjustments.Invert(data)


@register(Posterize)
def _translate_posterize(data):
    return adjustments.Posterize(data)


@register(Threshold)
def _translate_threshold(data):
    return adjustments.Threshold(data)


@register(SelectiveColor)
def _translate_selective_color(data):
    return adjustments.SelectiveColor(data)


@register(GradientSettings)
def _translate_gradient_map(data):
    return adjustments.GradientMap(data)


def _translate_generic_descriptor(data):
    """
    Fallback descriptor translator.
    """
    result = OrderedDict()
    result[b'classID'] = data.classID
    for key, value in data.items:
        translator = _translators.get(type(value), lambda data: data)
        result[key] = translator(value)
    return result


@desc_register(b'Grsc')
def _translate_grsc_color(data):
    colors = OrderedDict(data.items)
    return Color('gray', ((1.0 - colors[b'Gry '][0] / 100.0),))


@desc_register(b'RGBC')
def _translate_rgbc_color(data):
    colors = OrderedDict(data.items)
    return Color('rgb', (colors[b'Rd  '].value, colors[b'Grn '].value,
                         colors[b'Bl  '].value))


@desc_register(b'CMYC')
def _translate_cmyc_color(data):
    colors = OrderedDict(data.items)
    return Color('cmyk', (colors[b'Cyn '].value, colors[b'Mgnt'].value,
                          colors[b'Ylw '].value, colors[b'Blck'].value))


@desc_register(b'Pnt ')
@desc_register(b'CrPt')
def _translate_point(data):
    items = dict(data.items)
    return Point(translate(items.get(b'Hrzn')), translate(items.get(b'Vrtc')))


@desc_register(b'Ptrn')
def _translate_point(data):
    items = dict(data.items)
    return Pattern(translate(items.get(b'Nm  ')),
                   translate(items.get(b'Idnt')))


@desc_register(b'Grdn')
def _translate_gradient(data):
    items = dict(data.items)
    return Gradient(data.name,
                    translate(items.get(b'Nm  ')),
                    translate(items.get(b'GrdF')),
                    translate(items.get(b'Intr')),
                    translate(items.get(b'Clrs')),
                    translate(items.get(b'Trns')))


@desc_register(b'Clrt')
def _translate_stopcolor(data):
    items = OrderedDict(data.items)
    return StopColor(*[translate(items[key]) for key in items])


@desc_register(b'TrnS')
def _translate_stopcolor(data):
    items = OrderedDict(data.items)
    return StopOpacity(*[translate(items[key]) for key in items])


@desc_register(b'ShpC')
def _translate_shape(data):
    items = dict(data.items)
    return Shape(translate(items.get(b'Nm  ')), translate(items.get(b'Crv ')))


@desc_register(b'metadata')
def _translate_metadata(data):
    return _translate_generic_descriptor(data)


@desc_register(b'strokeStyle')
def _translate_stroke_style(data):
    return StrokeStyle(_translate_generic_descriptor(data))


@desc_register(b'solidColorLayer')
def _translate_solid_color_layer(data):
    return ColorOverlay(_translate_generic_descriptor(data), None)


@desc_register(b'patternLayer')
def _translate_pattern_layer(data):
    return PatternOverlay(_translate_generic_descriptor(data), None)


@desc_register(b'gradientLayer')
def _translate_gradient_layer(data):
    return GradientOverlay(_translate_generic_descriptor(data), None)


@desc_register(b'radii')
def _translate_rrect_radii(data):
    items = dict(data.items)
    return (items.get(b'topLeft').value,
            items.get(b'topRight').value,
            items.get(b'bottomLeft').value,
            items.get(b'bottomRight').value)


@desc_register(b'unitRect')
def _translate_unit_rect(data):
    items = dict(data.items)
    return BBox(items.get(b'Left').value,
                items.get(b'Top ').value,
                items.get(b'Rght').value,
                items.get(b'Btom').value)
