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
    SolidColorSetting, PatternFillSetting, GradientFillSetting)
from psd_tools.decoder.layer_effects import ObjectBasedEffects
from psd_tools.user_api.effects import GradientOverlay


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


@register(UnitFloat)
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


@register(SolidColorSetting)
@register(PatternFillSetting)
def _translate_fill_setting(data):
    return translate(data.data)


@register(GradientFillSetting)
def _translate_gradient_fill_setting(data):
    descriptor = translate(data.data)
    return GradientOverlay(descriptor)


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


@desc_register(b'null')
def _translate_null_descriptor(data):
    if len(data.items) == 1:
        return translate(data.items[0][1])
    return _translate_generic_descriptor(data)


@desc_register(b'Grsc')
def _translate_grsc_color(data):
    colors = OrderedDict(data.items)
    return Color('gray', ((100.0 - colors[0][1].value / 100.0), ))


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
