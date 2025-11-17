"""
Descriptor data structure.

Descriptors are basic data structure used throughout PSD files. Descriptor is
one kind of serialization protocol for data objects, and
enum classes in :py:mod:`psd_tools.terminology` or bytes indicates what kind
of descriptor it is.

The class ID can be pre-defined enum if the tag is 4-byte length or plain
bytes if the length is arbitrary. They depend on the internal version of
Adobe Photoshop but the detail is unknown.

Pretty printing is the best approach to check the descriptor content::

    from IPython.pretty import pprint
    pprint(descriptor)
"""

import logging
from typing import Any, BinaryIO, Dict, Iterator, TypeVar

from attrs import define, field

from psd_tools.constants import OSType
from psd_tools.psd.base import (
    BaseElement,
    BooleanElement,
    DictElement,
    IntegerElement,
    ListElement,
    NumericElement,
    StringElement,
)
from psd_tools.terminology import Enum, Event, Form, Key, Klass, Type, Unit
from psd_tools.psd.bin_utils import (
    read_fmt,
    read_length_block,
    read_unicode_string,
    trimmed_repr,
    write_bytes,
    write_fmt,
    write_length_block,
    write_padding,
    write_unicode_string,
)
from psd_tools.registry import new_registry
from psd_tools.validators import in_

logger = logging.getLogger(__name__)

TYPES, register = new_registry(attribute="ostype")

T = TypeVar("T")

_TERMS = set(
    item.value
    for kls in (Klass, Enum, Event, Form, Key, Type, Unit)
    for item in kls
    if len(item.value) == 4
)


def read_length_and_key(fp: BinaryIO) -> bytes:
    """
    Helper to read descriptor key.
    """
    length = read_fmt("I", fp)[0]
    key = fp.read(length or 4)
    if length == 0 and key not in _TERMS:
        logger.debug("Unknown term: %r" % (key))
        _TERMS.add(key)
    return key


def write_length_and_key(fp: BinaryIO, value: bytes) -> int:
    """
    Helper to write descriptor key.
    """
    written = write_fmt(fp, "I", 0 if value in _TERMS else len(value))
    written += write_bytes(fp, value)
    return written


class _DescriptorMixin(DictElement):
    name: str = ""
    classID: bytes = b"\x00\x00\x00\x00"

    @classmethod
    def _read_body(cls, fp: BinaryIO) -> Dict[str, Any]:
        name = read_unicode_string(fp, padding=1)
        classID = read_length_and_key(fp)
        items = []
        count = read_fmt("I", fp)[0]
        for _ in range(count):
            key = read_length_and_key(fp)
            ostype = OSType(fp.read(4))
            kls = TYPES.get(ostype)
            value = kls.read(fp)  # type: ignore[union-attr]
            items.append((key, value))

        return dict(name=name, classID=classID, items=items)

    def _write_body(self, fp: BinaryIO) -> int:
        written = write_unicode_string(fp, self.name, padding=1)
        written += write_length_and_key(fp, self.classID)
        written += write_fmt(fp, "I", len(self))
        for key in self:
            written += write_length_and_key(fp, key)
            written += write_bytes(fp, self[key].ostype.value)
            written += self[key].write(fp)
        return written

    @classmethod
    def _key_converter(cls, key: Any) -> bytes:
        if hasattr(key, "encode"):
            return key.encode("ascii")
        return getattr(key, "value", key)

    def _repr_pretty_(self, p: Any, cycle: bool) -> None:
        if cycle:
            p.text("(...)")
            return

        prefix = "{cls}({name}){{".format(
            cls=self.__class__.__name__,
            name=getattr(self.classID, "name", self.classID),
        )
        with p.group(2, prefix, "}"):
            p.breakable("")
            for idx, key in enumerate(self):
                if idx:
                    p.text(",")
                    p.breakable()
                value = self[key]
                p.pretty(key.decode("ascii"))
                p.text(": ")
                if isinstance(value, bytes):
                    p.text(trimmed_repr(value))
                else:
                    p.pretty(value)
            p.breakable("")


@register(OSType.DESCRIPTOR)
@define(repr=False)
class Descriptor(_DescriptorMixin):
    """
    Dict-like descriptor structure.

    Key values can be 4-character `bytes` in
    :py:class:`~psd_tools.terminology.Key` or arbitrary length `bytes`.
    Supports direct access by :py:class:`~psd_tools.terminology.Key`.

    Example::

        from psd_tools.terminology import Key

        descriptor[Key.Enabled]

        for key in descriptor:
            print(descriptor[key])

    .. py:attribute:: name

        `str`

    .. py:attribute:: classID

        bytes in :py:class:`~psd_tools.terminology.Klass`
    """

    name: str = ""
    classID: bytes = Klass.Null.value

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        return cls(**cls._read_body(fp))  # type: ignore[attr-defined]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return self._write_body(fp)


@register(OSType.OBJECT_ARRAY)
@define(repr=False)
class ObjectArray(_DescriptorMixin):
    """
    Object array structure almost equivalent to
    :py:class:`~psd_tools.psd.descriptor.Descriptor`.

    .. py:attribute:: items_count

        `int` value

    .. py:attribute:: name

        `str` value

    .. py:attribute:: classID

        bytes in :py:class:`~psd_tools.terminology.Klass`
    """

    items_count: int = 0
    name: str = ""
    classID: bytes = Klass.Null.value

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        items_count = read_fmt("I", fp)[0]
        return cls(items_count=items_count, **cls._read_body(fp))  # type: ignore[attr-defined,call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "I", self.items_count)
        written += self._write_body(fp)
        return written


@register(OSType.LIST)
@define(repr=False)
class List(ListElement):
    """
    List structure.

    Example::

        for item in list_value:
            print(item)
    """

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        items = []
        count = read_fmt("I", fp)[0]
        for _ in range(count):
            key = OSType(fp.read(4))
            kls = TYPES.get(key)
            value = kls.read(fp)  # type: ignore[union-attr]
            items.append(value)
        return cls(items)  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "I", len(self))
        for item in self:
            written += write_bytes(fp, item.ostype.value)
            written += item.write(fp)
        return written


@register(OSType.PROPERTY)
@define(repr=False)
class Property(BaseElement):
    """
    Property structure.

    .. py:attribute:: name

        `str` value

    .. py:attribute:: classID

        bytes in :py:class:`~psd_tools.terminology.Klass`

    .. py:attribute:: keyID

        bytes in :py:class:`~psd_tools.terminology.Key`
    """

    name: str = ""
    classID: bytes = b"\x00\x00\x00\x00"
    keyID: bytes = b"\x00\x00\x00\x00"

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        name = read_unicode_string(fp)
        classID = read_length_and_key(fp)
        keyID = read_length_and_key(fp)
        return cls(name, classID, keyID)  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_unicode_string(fp, self.name)
        written += write_length_and_key(fp, self.classID)
        written += write_length_and_key(fp, self.keyID)
        return written


@register(OSType.UNIT_FLOAT)
@define(repr=False, eq=False, order=False)
class UnitFloat(NumericElement):
    """
    Unit float structure.

    .. py:attribute:: unit

        unit of the value in :py:class:`Unit` or :py:class:`Enum`

    .. py:attribute:: value

        `float` value
    """

    value: float = 0.0
    unit: Unit = Unit._None

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        unit, value = read_fmt("4sd", fp)
        try:
            unit = Unit(unit)
        except ValueError:
            logger.warning("Using Enum for Unit field")
            unit = Enum(unit)
        return cls(unit=unit, value=value)  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "4sd", self.unit.value, self.value)

    def _repr_pretty_(self, p: Any, cycle: bool) -> None:
        if cycle:
            p.text(self.__repr__())
            return
        p.pretty(self.value)
        p.text(" ")
        p.text(self.unit.name)


@register(OSType.UNIT_FLOATS)
@define(repr=False)
class UnitFloats(BaseElement):
    """
    Unit floats structure.

    .. py:attribute:: unit

        unit of the value in :py:class:`Unit` or :py:class:`Enum`

    .. py:attribute:: values

        List of `float` values
    """

    unit: Unit = Unit._None
    values: list = field(factory=list)

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        unit, count = read_fmt("4sI", fp)
        try:
            unit = Unit(unit)
        except ValueError:
            logger.warning("Using Enum for Unit field")
            unit = Enum(unit)
        values = list(read_fmt("%dd" % count, fp))
        return cls(unit=unit, values=values)  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(
            fp,
            "4sI%dd" % len(self.values),
            self.unit.value,
            len(self.values),
            *self.values,
        )

    def __iter__(self) -> Iterator[float]:
        for value in self.values:
            yield value

    def __getitem__(self, index: int) -> float:
        return self.values[index]

    def __len__(self) -> int:
        return len(self.values)


@register(OSType.DOUBLE)
class Double(NumericElement):
    """
    Double structure.

    .. py:attribute:: value

        `float` value
    """

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        return cls(*read_fmt("d", fp))

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "d", self.value)


@define(repr=False)
class Class(BaseElement):
    """
    Class structure.

    .. py:attribute:: name

        `str` value

    .. py:attribute:: classID

        bytes in :py:class:`~psd_tools.terminology.Klass`
    """

    name: str = ""
    classID: bytes = b"\x00\x00\x00\x00"

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        name = read_unicode_string(fp)
        classID = read_length_and_key(fp)
        return cls(name, classID)  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_unicode_string(fp, self.name)
        written += write_length_and_key(fp, self.classID)
        return written


@register(OSType.STRING)
class String(StringElement):
    """
    String structure.

    .. py:attribute:: value

        `str` value
    """

    pass


@register(OSType.ENUMERATED_REFERENCE)
@define(repr=False)
class EnumeratedReference(BaseElement):
    """
    Enumerated reference structure.

    .. py:attribute:: name

        `str` value

    .. py:attribute:: classID

        bytes in :py:class:`~psd_tools.terminology.Klass`

    .. py:attribute:: typeID

        bytes in :py:class:`~psd_tools.terminology.Type`

    .. py:attribute:: enum

        bytes in :py:class:`~psd_tools.terminology.Enum`
    """

    name: str = ""
    classID: bytes = b"\x00\x00\x00\x00"
    typeID: bytes = b"\x00\x00\x00\x00"
    enum: bytes = b"\x00\x00\x00\x00"

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        name = read_unicode_string(fp)
        classID = read_length_and_key(fp)
        typeID = read_length_and_key(fp)
        enum = read_length_and_key(fp)
        return cls(name, classID, typeID, enum)  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_unicode_string(fp, self.name)
        written += write_length_and_key(fp, self.classID)
        written += write_length_and_key(fp, self.typeID)
        written += write_length_and_key(fp, self.enum)
        return written


@register(OSType.OFFSET)
@define(repr=False)
class Offset(BaseElement):
    """
    Offset structure.

    .. py:attribute:: name

        `str` value

    .. py:attribute:: classID

        bytes in :py:class:`~psd_tools.terminology.Klass`

    .. py:attribute:: value

        `int` value
    """

    name: str = ""
    classID: bytes = b"\x00\x00\x00\x00"
    value: int = 0

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        name = read_unicode_string(fp)
        classID = read_length_and_key(fp)
        offset = read_fmt("I", fp)[0]
        return cls(name, classID, offset)  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_unicode_string(fp, self.name)
        written += write_length_and_key(fp, self.classID)
        written += write_fmt(fp, "I", self.value)
        return written


@register(OSType.BOOLEAN)
class Bool(BooleanElement):
    """
    Bool structure.

    .. py:attribute:: value

        `bool` value
    """

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        return cls(read_fmt("?", fp)[0])  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "?", self.value)


@register(OSType.LARGE_INTEGER)
class LargeInteger(IntegerElement):
    """
    LargeInteger structure.

    .. py:attribute:: value

        `int` value
    """

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        return cls(read_fmt("q", fp)[0])  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "q", self.value)


@register(OSType.INTEGER)
class Integer(IntegerElement):
    """
    Integer structure.

    .. py:attribute:: value

        `int` value
    """

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        return cls(read_fmt("i", fp)[0])  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "i", self.value)


@register(OSType.ENUMERATED)
@define(repr=False)
class Enumerated(BaseElement):
    """
    Enum structure.

    .. py:attribute:: typeID

        bytes in :py:class:`~psd_tools.terminology.Type`

    .. py:attribute:: enum

        bytes in :py:class:`~psd_tools.terminology.Enum`
    """

    typeID: bytes = b"\x00\x00\x00\x00"
    enum: bytes = b"\x00\x00\x00\x00"

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        typeID = read_length_and_key(fp)
        enum = read_length_and_key(fp)
        return cls(typeID, enum)  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_length_and_key(fp, self.typeID)
        written += write_length_and_key(fp, self.enum)
        return written

    def _repr_pretty_(self, p: Any, cycle: bool) -> None:
        if cycle:
            p.text(self.__repr__())
            return
        p.text("(")
        p.pretty(getattr(self.typeID, "name", self.typeID))
        p.text(", ")
        p.pretty(getattr(self.enum, "name", self.enum))
        p.text(")")

    def get_name(self) -> str:
        """Get enum name."""
        if len(self.enum) == 4:
            try:
                return Enum(self.enum).name
            except ValueError:
                pass
        return str(self.enum)


@register(OSType.RAW_DATA)
@define(repr=False)
class RawData(BaseElement):
    """
    RawData structure.

    .. py:attribute:: value

        `bytes` value
    """

    value: bytes = b"\x00\x00\x00\x00"

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        return cls(read_length_block(fp))  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        def writer(f: BinaryIO) -> int:
            if hasattr(self.value, "write"):
                return self.value.write(f)
            return write_bytes(f, self.value)

        return write_length_block(fp, writer)


@register(OSType.CLASS1)
class Class1(Class):
    """
    Class structure equivalent to
    :py:class:`~psd_tools.psd.descriptor.Class`.
    """

    pass


@register(OSType.CLASS2)
class Class2(Class):
    """
    Class structure equivalent to
    :py:class:`~psd_tools.psd.descriptor.Class`.
    """

    pass


@register(OSType.CLASS3)
class Class3(Class):
    """
    Class structure equivalent to
    :py:class:`~psd_tools.psd.descriptor.Class`.
    """

    pass


@register(OSType.REFERENCE)
class Reference(List):
    """
    Reference structure equivalent to
    :py:class:`~psd_tools.psd.descriptor.List`.
    """

    pass


@register(OSType.ALIAS)
class Alias(RawData):
    """
    Alias structure equivalent to
    :py:class:`~psd_tools.psd.descriptor.RawData`.
    """

    pass


@register(OSType.GLOBAL_OBJECT)
class GlobalObject(Descriptor):
    """
    Global object structure equivalent to
    :py:class:`~psd_tools.psd.descriptor.Descriptor`.
    """

    pass


@register(OSType.PATH)
class Path(RawData):
    """
    Undocumented path structure equivalent to
    :py:class:`~psd_tools.psd.descriptor.RawData`.
    """

    pass


@register(OSType.IDENTIFIER)
class Identifier(Integer):
    """
    Identifier equivalent to
    :py:class:`~psd_tools.psd.descriptor.Integer`.
    """

    pass


@register(OSType.INDEX)
class Index(Integer):
    """
    Index equivalent to :py:class:`~psd_tools.psd.descriptor.Integer`.
    """

    pass


@register(OSType.NAME)
@define(repr=False)
class Name(BaseElement):
    """
    Name structure (Undocumented).

    .. py:attribute:: name

        str

    .. py:attribute:: classID

        bytes in :py:class:`~psd_tools.terminology.Klass`

    .. py:attribute:: value

        str
    """

    name: str = ""
    classID: bytes = b"\x00\x00\x00\x00"
    value: str = ""

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        name = read_unicode_string(fp)
        classID = read_length_and_key(fp)
        value = read_unicode_string(fp)
        return cls(name, classID, value)  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_unicode_string(fp, self.name)
        written += write_length_and_key(fp, self.classID)
        written += write_unicode_string(fp, self.value)
        return written


@define(repr=False)
class DescriptorBlock(Descriptor):
    """
    Dict-like Descriptor-based structure that has `version` field. See
    :py:class:`~psd_tools.psd.descriptor.Descriptor`.

    .. py:attribute:: version
    """

    version: int = field(default=16, validator=in_((16,)))

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        version = read_fmt("I", fp)[0]
        return cls(version=version, **cls._read_body(fp))  # type: ignore[attr-defined,call-arg]

    def write(self, fp: BinaryIO, padding: int = 4, **kwargs: Any) -> int:
        written = write_fmt(fp, "I", self.version)
        written += self._write_body(fp)
        written += write_padding(fp, written, padding)
        return written


@define(repr=False)
class DescriptorBlock2(Descriptor):
    """
    Dict-like Descriptor-based structure that has `version` and
    `data_version` fields. See
    :py:class:`~psd_tools.psd.descriptor.Descriptor`.

    .. py:attribute:: version
    .. py:attribute:: data_version
    """

    version: int = 1
    data_version: int = field(default=16, validator=in_((16,)))

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        version, data_version = read_fmt("2I", fp)
        return cls(version=version, data_version=data_version, **cls._read_body(fp))  # type: ignore[attr-defined,call-arg]

    def write(self, fp: BinaryIO, padding: int = 4, **kwargs: Any) -> int:
        written = write_fmt(fp, "2I", self.version, self.data_version)
        written += self._write_body(fp)
        written += write_padding(fp, written, padding)
        return written
