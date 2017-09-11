# -*- coding: utf-8 -*-
"""
A module for translating "Actions" format to native Python structure.
"""
from __future__ import absolute_import

from collections import OrderedDict
from psd_tools.decoder.decoders import new_registry
from psd_tools.decoder.actions import (Descriptor, Reference, Property,
    UnitFloat, Double, Class, String, EnumReference, Boolean, Offset, Alias,
    List, Integer, Enum, Identifier, Index, Name, ObjectArray,
    ObjectArrayItem, RawData)


_translators, register = new_registry()


def translate(descriptor):
    """
    Translate descriptor-based format.
    """
    return _translate_descriptor(descriptor)


@register(Descriptor)
def _translate_descriptor(data):
    result = OrderedDict()
    for key, value in data.items:
        translator = _translators.get(type(value), lambda data: data)
        result[key] = translator(value)
    return result


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


@register(Double)
@register(String)
@register(Boolean)
@register(Alias)
@register(Integer)
@register(Identifier)
@register(Index)
@register(Name)
@register(RawData)
def _translate_value(data):
    return data.value
