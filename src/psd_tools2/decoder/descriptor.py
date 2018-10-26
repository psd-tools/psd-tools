"""
Descriptor data structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import io
import logging

from psd_tools2.decoder.base import BaseElement
from psd_tools2.constants import OSType, UnitFloatType
from psd_tools2.validators import in_
from psd_tools2.utils import (
    read_fmt, write_fmt, read_unicode_string, write_unicode_string,
    write_bytes, read_length_block, write_length_block,
)


TYPES = {}


def register(ostype):
    def wrapper(cls):
        TYPES[ostype] = cls
        setattr(cls, 'ostype', ostype)
        return cls
    return wrapper


def write_length_and_key(fp, value):
    """
    Helper to write descriptor classID and key.
    """
    length = 0 if len(value) == 4 else len(value)
    written = write_fmt(fp, 'I', length)
    written += write_bytes(fp, value)
    return written


@register(OSType.REFERENCE)
@attr.s
class Reference(BaseElement):
    """
    Reference structure.

    .. py:attribute:: items
    """
    items = attr.ib(factory=list)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        """
        items = []
        count = read_fmt('I', fp)[0]
        while len(items) < count:
            key = OSType(fp.read(4))
            decoder = TYPES.get(key)
            if not decoder:
                raise ValueError('Unknown reference key %r' % key)
            value = decoder.read(fp)
            items.append(value)
        return cls(items)

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        written = write_fmt(fp, 'I', len(self.items))
        for item in self.items:
            written += write_bytes(item.ostype)
            written += item.write(fp)
        return written


@register(OSType.DESCRIPTOR)
@attr.s
class Descriptor(BaseElement):
    """
    Descriptor structure.

    .. py:attribute:: name
    .. py:attribute:: classID
    .. py:attribute:: items
    """
    name = attr.ib(default='', type=str)
    classID = attr.ib(default=b'\x00\x00\x00\x00', type=bytes)
    items = attr.ib(factory=list)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        """
        name = read_unicode_string(fp)
        classID = fp.read(read_fmt('I', fp)[0] or 4)
        items = []
        count = read_fmt('I', fp)[0]
        for _ in range(count):
            key = fp.read(read_fmt("I", fp)[0] or 4)
            ostype = OSType(fp.read(4))
            decoder = TYPES.get(ostype)
            if not decoder:
                # # For some reason, name can appear in the middle of items...
                # if key == OSType.NAME:
                #     fp.seek(fp.tell() - 4)
                #     name = decode_name(key, fp)
                #     continue
                raise ValueError('Unknown descriptor type %r' % ostype)

            value = decoder.read(fp)
            if value is None:
                warnings.warn("%r (%r) is None" % (key, ostype))
            items.append((key, value))

        return cls(name, classID, items)

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        written = write_unicode_string(fp, self.name)
        written += write_length_and_key(fp, self.classID)
        written += write_fmt(fp, 'I', len(self.items))
        for item in self.items:
            written += write_length_and_key(fp, item[0])
            written += fp.write(item[1].ostype.value)
            written += item[1].write(fp)
        return written


@register(OSType.PROPERTY)
@attr.s
class Property(BaseElement):
    """
    Property structure.

    .. py:attribute:: name
    """
    name = attr.ib(default='', type=str)
    classID = attr.ib(default=b'\x00\x00\x00\x00', type=bytes)
    keyID = attr.ib(default=b'\x00\x00\x00\x00', type=bytes)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        """
        name = read_unicode_string(fp)
        classID = fp.read(read_fmt('I', fp)[0] or 4)
        keyID = fp.read(read_fmt('I', fp)[0] or 4)
        return cls(name, classID, keyID)

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        written = write_unicode_string(fp, self.name)
        written += write_length_and_key(fp, self.classID)
        written += write_length_and_key(fp, self.keyID)
        return written


@register(OSType.UNIT_FLOAT)
@attr.s
class UnitFloat(BaseElement):
    """
    Unit float structure.

    .. py:attribute:: unit
    .. py:attribute:: value
    """
    unit = attr.ib(default=UnitFloatType.NONE, converter=UnitFloatType,
                   validator=in_(UnitFloatType))
    value = attr.ib(default=0.0, type=float)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        """
        return cls(*read_fmt('4sd', fp))

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        return write_fmt(fp, '4sd', self.unit.value, self.value)


@register(OSType.UNIT_FLOATS)
@attr.s
class UnitFloats(BaseElement):
    """
    Unit floats structure.

    .. py:attribute:: unit
    .. py:attribute:: values
    """
    unit = attr.ib(default=UnitFloatType.NONE, converter=UnitFloatType,
                   validator=in_(UnitFloatType))
    values = attr.ib(factory=list)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        """
        unit, count = read_fmt('4sI', fp)
        values = list(read_fmt('%dd' % count, fp))
        return cls(unit, values)

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        return write_fmt(fp, '4sI%dd' % len(self.values), self.unit.value,
                         len(self.values), *self.values)


@register(OSType.DOUBLE)
@attr.s
class Double(BaseElement):
    """
    Double structure.

    .. py:attribute:: value
    """
    value = attr.ib(default=0.0, type=float)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        """
        return cls(*read_fmt('d'))

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        return write_fmt(fp, 'd', self.value)


@attr.s
class Class(BaseElement):
    """
    Class structure.

    .. py:attribute:: name
    .. py:attribute:: classID
    """
    name = attr.ib(default='', type=str)
    classID = attr.ib(default=b'\x00\x00\x00\x00', type=bytes)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        """
        name = read_unicode_string(fp)
        classID = fp.read(read_fmt('I', fp)[0] or 4)
        return cls(name, classID)

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        written = write_unicode_string(fp, self.name)
        written += write_length_and_key(fp, self.classID)
        return written


@register(OSType.CLASS1)
class Class1(Class):
    pass


@register(OSType.CLASS2)
class Class2(Class):
    pass


@register(OSType.CLASS3)
class Class3(Class):
    pass


@register(OSType.DOUBLE)
@attr.s
class String(BaseElement):
    """
    String structure.

    .. py:attribute:: value
    """
    value = attr.ib(default='', type=str)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        """
        return cls(read_unicode_string(fp))

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        return write_unicode_string(fp, self.value)


@register(OSType.ENUMERATED_REFERENCE)
@attr.s
class EnumeratedReference(BaseElement):
    """
    Enumerated reference structure.

    .. py:attribute:: value
    """
    name = attr.ib(default='', type=str)
    classID = attr.ib(default=b'\x00\x00\x00\x00', type=bytes)
    typeID = attr.ib(default=b'\x00\x00\x00\x00', type=bytes)
    enum = attr.ib(default=b'\x00\x00\x00\x00', type=bytes)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        """
        name = read_unicode_string(fp)
        classID = fp.read(read_fmt('I', fp)[0] or 4)
        typeID = fp.read(read_fmt('I', fp)[0] or 4)
        enum = fp.read(read_fmt('I', fp)[0] or 4)
        return cls(name, classID, typeID, enum)

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        written = write_unicode_string(fp, self.name)
        written += write_length_and_key(fp, self.classID)
        written += write_length_and_key(fp, self.typeID)
        written += write_length_and_key(fp, self.enum)
        return written


@register(OSType.OFFSET)
@attr.s
class Offset(BaseElement):
    """
    Offset structure.

    .. py:attribute:: value
    """
    name = attr.ib(default='', type=str)
    classID = attr.ib(default=b'\x00\x00\x00\x00', type=bytes)
    value = attr.ib(default=0)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        """
        name = read_unicode_string(fp)
        classID = fp.read(read_fmt('I', fp)[0] or 4)
        offset = read_fmt('I', fp)[0]
        return cls(name, classID, offset)

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        written = write_unicode_string(fp, self.name)
        written += write_length_and_key(fp, self.classID)
        written += write_fmt(fp, 'I', self.value)
        return written


@register(OSType.BOOLEAN)
@attr.s
class Bool(BaseElement):
    """
    Bool structure.

    .. py:attribute:: value
    """
    value = attr.ib(default=False, type=bool)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        """
        return cls(read_fmt('?', fp)[0])

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        return write_fmt(fp, '?', self.value)


@register(OSType.LIST)
@attr.s
class List(BaseElement):
    """
    List structure.

    .. py:attribute:: items
    """
    items = attr.ib(factory=list)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        """
        items = []
        count = read_fmt('I', fp)[0]
        while len(items) < count:
            key = OSType(fp.read(4))
            decoder = TYPES.get(key)
            if not decoder:
                raise ValueError('Unknown key %r' % key)
            value = decoder.read(fp)
            items.append(value)
        return cls(items)

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        written = write_fmt(fp, 'I', len(self.items))
        for item in self.items:
            written += write_bytes(item.ostype)
            written += item.write(fp)
        return written


@register(OSType.LARGE_INTEGER)
@attr.s
class LargeInteger(BaseElement):
    """
    LargeInteger structure.

    .. py:attribute:: value
    """
    value = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        """
        return cls(read_fmt('q', fp)[0])

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        return write_fmt(fp, 'q', self.value)


@register(OSType.INTEGER)
@attr.s
class Integer(BaseElement):
    """
    Integer structure.

    .. py:attribute:: value
    """
    value = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        """
        return cls(read_fmt('i', fp)[0])

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        return write_fmt(fp, 'i', self.value)


@register(OSType.ENUMERATED)
@attr.s
class Enum(BaseElement):
    """
    Enum structure.

    .. py:attribute:: value
    """
    typeID = attr.ib(default=b'\x00\x00\x00\x00', type=bytes)
    enum = attr.ib(default=b'\x00\x00\x00\x00', type=bytes)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        """
        typeID = fp.read(read_fmt('I', fp)[0] or 4)
        enum = fp.read(read_fmt('I', fp)[0] or 4)
        return cls(typeID, enum)

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        written = write_length_and_key(fp, self.typeID)
        written += write_length_and_key(fp, self.enum)
        return written


@register(OSType.RAW_DATA)
@attr.s
class RawData(BaseElement):
    """
    RawData structure.

    .. py:attribute:: value
    """
    value = attr.ib(default=b'\x00\x00\x00\x00', type=bytes)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        """
        return cls(read_length_block(fp))

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        return write_length_block(fp, lambda f: write_bytes(f, self.value))


@register(OSType.ALIAS)
class Alias(RawData):
    """
    Alias structure.

    .. py:attribute:: value
    """
    pass


@register(OSType.GLOBAL_OBJECT)
class GlobalObject(Descriptor):
    """
    Global object structure equivalent to
    :py:class:`~psd_tools2.decoder.descriptor.Descriptor`.
    """
    pass


@register(OSType.OBJECT_ARRAY)
class ObjectArray(Descriptor):
    """
    Object array structure equivalent to
    :py:class:`~psd_tools2.decoder.descriptor.Descriptor`.
    """
    pass


@register(OSType.PATH)
class Path(RawData):
    """
    Undocumented path structure.
    """
    pass


@register(OSType.IDENTIFIER)
class Identifier(Integer):
    """
    Identifier equivalent to
    :py:class:`~psd_tools2.decoder.descriptor.Integer`.
    """
    pass


@register(OSType.INDEX)
class Index(Integer):
    """
    Index equivalent to :py:class:`~psd_tools2.decoder.descriptor.Integer`.
    """
    pass


@register(OSType.NAME)
class Name(String):
    """
    Name equivalent to :py:class:`~psd_tools2.decoder.descriptor.String`.
    """
    pass
