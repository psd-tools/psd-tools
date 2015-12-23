# -*- coding: utf-8 -*-
"""
A module for decoding "Actions" additional PSD data format.
"""
from __future__ import absolute_import, unicode_literals

from psd_tools.utils import read_unicode_string, read_fmt
from psd_tools.constants import OSType, ReferenceOSType, UnitFloatType
from psd_tools.debug import pretty_namedtuple
from psd_tools.utils import trimmed_repr
import warnings

Descriptor = pretty_namedtuple('Descriptor', 'name classID items')
Reference = pretty_namedtuple('Reference', 'items')
Property = pretty_namedtuple('Property', 'name classID keyID')
UnitFloat = pretty_namedtuple('UnitFloat', 'unit value')
Double = pretty_namedtuple('Double', 'value')
Class = pretty_namedtuple('Class', 'name classID')
String = pretty_namedtuple('String', 'value')
EnumReference = pretty_namedtuple('EnumReference', 'name classID typeID enum')
Boolean = pretty_namedtuple('Boolean', 'value')
Offset = pretty_namedtuple('Offset', 'name classID value')
Alias = pretty_namedtuple('Alias', 'value')
List = pretty_namedtuple('List', 'items')
Integer = pretty_namedtuple('Integer', 'value')
Enum = pretty_namedtuple('Enum', 'type value')
Identifier = pretty_namedtuple('Identifier', 'value')
Index = pretty_namedtuple('Index', 'value')
Name = pretty_namedtuple('Name', 'value')
ObjectArray = pretty_namedtuple('ObjectArray', 'classObj items')
ObjectArrayItem = pretty_namedtuple('ObjectArrayItem', 'keyID value')
_RawData = pretty_namedtuple('RawData', 'value')


class RawData(_RawData):
    def __repr__(self):
        return "RawData(value=%s)" % trimmed_repr(self.value)

    def _repr_pretty_(self, p, cycle):
        if cycle:
            p.text("RawData(...)")
        else:
            with p.group(1, "RawData(", ")"):
                p.breakable()
                p.text("value=")
                if isinstance(self.value, bytes):
                    p.text(trimmed_repr(self.value))
                else:
                    p.pretty(self.value)


def get_ostype_decode_func(ostype):
    return {
        OSType.REFERENCE:   decode_ref,
        OSType.DESCRIPTOR:  decode_descriptor,
        OSType.LIST:        decode_list,
        OSType.DOUBLE:      decode_double,
        OSType.UNIT_FLOAT:  decode_unit_float,
        OSType.UNIT_FLOATS: decode_unit_floats,
        OSType.STRING:      decode_string,
        OSType.ENUMERATED:  decode_enum,
        OSType.INTEGER:     decode_integer,
        OSType.BOOLEAN:     decode_bool,
        OSType.GLOBAL_OBJECT: decode_descriptor,
        OSType.CLASS1:      decode_class,
        OSType.CLASS2:      decode_class,
        OSType.ALIAS:       decode_alias,
        OSType.RAW_DATA:    decode_raw,
        OSType.OBJECT_ARRAY: decode_object_array,
    }.get(ostype, None)

def get_reference_ostype_decode_func(ostype):
    return {
        ReferenceOSType.PROPERTY:   decode_prop,
        ReferenceOSType.CLASS:      decode_class,
        ReferenceOSType.OFFSET:     decode_offset,
        ReferenceOSType.IDENTIFIER: decode_identifier,
        ReferenceOSType.INDEX:      decode_index,
        ReferenceOSType.NAME:       decode_name,
        ReferenceOSType.ENUMERATED_REFERENCE: decode_enum_ref,
    }.get(ostype, None)


def decode_descriptor(_, fp):
    name = read_unicode_string(fp)[:-1]
    classID_length = read_fmt("I", fp)[0]
    classID = fp.read(classID_length or 4)

    items = []
    item_count = read_fmt("I", fp)[0]
    for n in range(item_count):
        item_length = read_fmt("I", fp)[0]
        key = fp.read(item_length or 4)
        ostype = fp.read(4)

        decode_ostype = get_ostype_decode_func(ostype)
        if not decode_ostype:
            raise UnknownOSType('Unknown descriptor item of type %r' % ostype)

        value = decode_ostype(key, fp)
        if value is not None:
            items.append((key, value))

    return Descriptor(name, classID, items)

def decode_ref(key, fp):
    item_count = read_fmt("I", fp)[0]
    items = []
    for _ in range(item_count):
        ostype = fp.read(4)

        decode_ostype = get_reference_ostype_decode_func(ostype)
        if not decode_ostype:
            raise UnknownOSType('Unknown reference item of type %r' % ostype)

        value = decode_ostype(key, fp)
        if value is not None:
            items.append(value)

    return Reference(items)

def decode_prop(key, fp):
    name = read_unicode_string(fp)[:-1]
    classID_length = read_fmt("I", fp)[0]
    classID = fp.read(classID_length or 4)
    keyID_length = read_fmt("I", fp)[0]
    keyID = fp.read(keyID_length or 4)
    return Property(name, classID, keyID)

def decode_unit_float(key, fp):
    unit_key = fp.read(4)
    if not UnitFloatType.is_known(unit_key):
        warnings.warn('Unknown UnitFloatType: %r' % unit_key)

    value = read_fmt("d", fp)[0]
    return UnitFloat(UnitFloatType.name_of(unit_key), value)

def decode_unit_floats(key, fp):
    unit_key = fp.read(4)
    if not UnitFloatType.is_known(unit_key):
        warnings.warn('Unknown UnitFloatType: %r' % unit_key)

    floats_count = read_fmt("I", fp)[0]
    floats = []

    for n in range(floats_count):
        value = read_fmt("d", fp)[0]
        floats.append(UnitFloat(UnitFloatType.name_of(unit_key), value))

    return floats

def decode_double(key, fp):
    return Double(read_fmt("d", fp)[0])

def decode_class(key, fp):
    name = read_unicode_string(fp)[:-1]
    classID_length = read_fmt("I", fp)[0]
    classID = fp.read(classID_length or 4)
    return Class(name, classID)

def decode_string(key, fp):
    value = read_unicode_string(fp)[:-1]
    return String(value)

def decode_enum_ref(key, fp):
    name = read_unicode_string(fp)[:-1]
    classID_length = read_fmt("I", fp)[0]
    classID = fp.read(classID_length or 4)
    typeID_length = read_fmt("I", fp)[0]
    typeID = fp.read(typeID_length or 4)
    enum_length = read_fmt("I", fp)[0]
    enum = fp.read(enum_length or 4)
    return EnumReference(name, classID, typeID, enum)

def decode_offset(key, fp):
    name = read_unicode_string(fp)[:-1]
    classID_length = read_fmt("I", fp)[0]
    classID = fp.read(classID_length or 4)
    offset = read_fmt("I", fp)[0]
    return Offset(name, classID, offset)

def decode_bool(key, fp):
    return Boolean(read_fmt("?", fp)[0])

def decode_alias(key, fp):
    length = read_fmt("I", fp)[0]
    value = fp.read(length)
    return Alias(value)

def decode_list(key, fp):
    items_count = read_fmt("I", fp)[0]
    items = []
    for _ in range(items_count):
        ostype = fp.read(4)

        decode_ostype = get_ostype_decode_func(ostype)
        if not decode_ostype:
            raise UnknownOSType('Unknown list item of type %r' % ostype)

        value = decode_ostype(key, fp)
        if value is not None:
            items.append(value)

    return List(items)

def decode_integer(key, fp):
    return Integer(read_fmt("I", fp)[0])

def decode_enum(key, fp):
    type_length = read_fmt("I", fp)[0]
    type_ = fp.read(type_length or 4)
    value_length = read_fmt("I", fp)[0]
    value = fp.read(value_length or 4)
    return Enum(type_, value)

def decode_identifier(key, fp):
    return Identifier(read_fmt("I", fp)[0])

def decode_index(key, fp):
    return Index(read_fmt("I", fp)[0])

def decode_name(key, fp):
    value = read_unicode_string(fp)[:-1]
    return Name(value)


def decode_raw(key, fp):
    # This is the only thing we know about:
    # The first unsigned int determines the size of the raw data.
    size = read_fmt("I", fp)[0]
    data = fp.read(size)
    return RawData(data)

def decode_object_array(key, fp):
    items_per_object_count = read_fmt("I", fp)[0]
    classObj = decode_class(None, fp)
    items_count = read_fmt("I", fp)[0]
    items = []

    for n in range(items_count):
        object_array_item = decode_object_array_item(None, fp)

        if object_array_item is not None:
            items.append(object_array_item)

    return ObjectArray(classObj, items)

def decode_object_array_item(key, fp):
    keyID_length = read_fmt("I", fp)[0]
    keyID = fp.read(keyID_length or 4)

    ostype = fp.read(4)

    decode_ostype = get_ostype_decode_func(ostype)
    if not decode_ostype:
        raise UnknownOSType('Unknown list item of type %r' % ostype)

    value = decode_ostype(key, fp)

    return ObjectArrayItem(keyID, value)

class UnknownOSType(ValueError):
    pass
