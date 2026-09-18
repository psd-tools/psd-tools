"""
Base data structures intended for inheritance.

All the data objects in this subpackage inherit from the base classes here.
That means, all the data structures in the :py:mod:`psd_tools.psd` subpackage
implements the methods of :py:class:`~psd_tools.psd.BaseElement` for
serialization and decoding.

Objects that inherit from the :py:class:`~psd_tools.psd.BaseElement` typically
gets attrs_ decoration to have data fields.

.. _attrs: https://www.attrs.org/en/stable/index.html
"""

import io
import logging
import numbers
from collections import OrderedDict
from enum import Enum
from typing import IO, Any, Callable, Generator, TypeVar

from attrs import define, field, fields, has, validate

from psd_tools.psd.bin_utils import (
    read_fmt,
    read_unicode_string,
    trimmed_repr,
    write_bytes,
    write_fmt,
    write_unicode_string,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="BaseElement")


class BaseElement:
    """
    Base element of various PSD file structs.

    All the data objects in the :py:mod:`psd_tools.psd` subpackage inherit
    from this class.

    .. py:classmethod:: read(cls, fp)

        Read the element from a file-like object.

    .. py:method:: write(self, fp)

        Write the element to a file-like object.

    .. py:classmethod:: frombytes(self, data, *args, **kwargs)

        Read the element from bytes.

    .. py:method:: tobytes(self, *args, **kwargs)

        Write the element to bytes.

    .. py:method:: validate(self)

        Validate the attribute.
    """

    @classmethod
    def read(cls: type[T], fp: IO[bytes], **kwargs: Any) -> T:
        raise NotImplementedError()

    def write(self, fp: IO[bytes], **kwargs: Any) -> int:
        raise NotImplementedError()

    @classmethod
    def frombytes(cls: type[T], data: bytes, *args: Any, **kwargs: Any) -> T:
        with io.BytesIO(data) as f:
            return cls.read(f, *args, **kwargs)

    def tobytes(self, *args: Any, **kwargs: Any) -> bytes:
        with io.BytesIO() as f:
            self.write(f, *args, **kwargs)
            return f.getvalue()

    def validate(self) -> None:
        return validate(self)  # type: ignore[arg-type]

    def _repr_pretty_(self, p: Any, cycle: bool) -> None:
        if cycle:
            p.text("{name}(...)".format(name=self.__class__.__name__))
            return

        with p.group(2, "{name}(".format(name=self.__class__.__name__), ")"):
            p.breakable("")
            field_list = [f for f in fields(self.__class__) if f.repr]  # type: ignore[arg-type]
            for idx, field_item in enumerate(field_list):
                if idx:
                    p.text(",")
                    p.breakable()
                p.text("{field}=".format(field=field_item.name))
                value = getattr(self, field_item.name)
                if isinstance(value, bytes):
                    p.text(trimmed_repr(value))
                elif isinstance(value, Enum):
                    p.text(value.name)
                else:
                    p.pretty(value)
            p.breakable("")

    def _find(
        self, condition: Callable[[Any], bool] | None = None
    ) -> Generator[Any, None, None]:
        """
        Traversal API intended for debugging.
        """
        for _ in BaseElement._traverse(self, condition):
            yield _

    @staticmethod
    def _traverse(
        element: Any, condition: Callable[[Any], bool] | None = None
    ) -> Generator[Any, None, None]:
        """
        Traversal API intended for debugging.
        """
        if condition is None or condition(element):
            yield element
        if isinstance(element, DictElement):
            for child in element.values():
                for _ in BaseElement._traverse(child, condition):
                    yield _
        elif isinstance(element, ListElement):
            for child in element:
                for _ in BaseElement._traverse(child, condition):
                    yield _
        elif has(element.__class__):
            for field_item in fields(element.__class__):
                child = getattr(element, field_item.name)
                for _ in BaseElement._traverse(child, condition):
                    yield _


@define
class EmptyElement(BaseElement):
    """
    Empty element that does not have a value.
    """

    @classmethod
    def read(cls: type[T], fp: IO[bytes], *args: Any, **kwargs: Any) -> T:
        return cls()

    def write(self, fp: IO[bytes], *args: Any, **kwargs: Any) -> int:
        return 0


@define(repr=False, eq=False, order=False)
class ValueElement(BaseElement):
    """
    Single value wrapper that has a `value` attribute.

    Pretty printing shows the internal value by default. Inherit with
    `@define(repr=False)` decorator to keep this behavior.

    .. py:attribute:: value

        Internal value.
    """

    value: object = None

    def __lt__(self, other: Any) -> bool:
        return self.value < other

    def __le__(self, other: Any) -> bool:
        return self.value <= other

    def __eq__(self, other: Any) -> bool:
        return self.value == other

    def __ne__(self, other: Any) -> bool:
        return self.value != other

    def __gt__(self, other: Any) -> bool:
        return self.value > other

    def __ge__(self, other: Any) -> bool:
        return self.value >= other

    def __add__(self, other: Any) -> Any:
        return self.value + other

    def __sub__(self, other: Any) -> Any:
        return self.value - other

    def __mul__(self, other: Any) -> Any:
        return self.value * other

    def __mod__(self, other: Any) -> Any:
        return self.value % other

    def __rmul__(self, other: Any) -> Any:
        return other * self.value  # type: ignore[no-any-return]

    def __rmod__(self, other: Any) -> Any:
        return other % self.value  # type: ignore[no-any-return]

    def __hash__(self) -> int:
        return hash(self.value)

    def __bool__(self) -> bool:
        return bool(self.value)

    def __repr__(self) -> str:
        return self.value.__repr__()

    def _repr_pretty_(self, p: Any, cycle: bool) -> None:
        if cycle:
            p.text(self.__repr__())
            return
        if isinstance(self.value, bytes):
            p.text(trimmed_repr(self.value))
        else:
            p.pretty(self.value)


@define(repr=False, eq=False, order=False)
class NumericElement(ValueElement):
    """
    Single value element that has a numeric `value` attribute.

    Registered as a :py:class:`numbers.Real`, so that
    ``isinstance(element, numbers.Real)`` holds and code that dispatches on
    numeric type recognises the element. Every member of the protocol
    delegates to `value`.
    """

    value: float = field(default=0.0, converter=float)

    # Every binary operator delegates in expression form rather than by calling
    # the slot on `value`. ``self.value.__truediv__(other)`` returns
    # ``NotImplemented`` whenever `other` is not a float -- another element
    # included -- and the reflected method dead-ends the same way, so the
    # operator raises between two operands that are both `numbers.Real`.
    def __floordiv__(self, other: Any) -> Any:
        return self.value // other

    def __truediv__(self, other: Any) -> Any:
        return self.value / other

    def __divmod__(self, other: Any) -> Any:
        return divmod(self.value, other)

    def __pow__(self, other: Any, modulo: Any = None) -> Any:
        if modulo is None:
            return self.value**other
        return pow(self.value, other, modulo)

    def __radd__(self, other: Any) -> Any:
        return other + self.value

    def __rsub__(self, other: Any) -> Any:
        return other - self.value

    def __rfloordiv__(self, other: Any) -> Any:
        return other // self.value

    def __rtruediv__(self, other: Any) -> Any:
        return other / self.value

    def __rdivmod__(self, other: Any) -> Any:
        return divmod(other, self.value)

    def __rpow__(self, other: Any) -> Any:
        return other**self.value

    def __neg__(self) -> Any:
        return self.value.__neg__()

    def __pos__(self) -> Any:
        return self.value.__pos__()

    def __abs__(self) -> Any:
        return self.value.__abs__()

    def __round__(self, ndigits: int | None = None) -> Any:
        if ndigits is None:
            return self.value.__round__()
        return self.value.__round__(ndigits)

    def __trunc__(self) -> int:
        return self.value.__trunc__()

    def __floor__(self) -> int:
        return self.value.__floor__()

    def __ceil__(self) -> int:
        return self.value.__ceil__()

    def __int__(self) -> int:
        return int(self.value)

    def __float__(self) -> float:
        return float(self.value)

    def __complex__(self) -> complex:
        return complex(self.value)

    def __format__(self, format_spec: str) -> str:
        return format(self.value, format_spec)

    @property
    def real(self) -> float:
        return self.value.real

    @property
    def imag(self) -> float:
        return self.value.imag

    def conjugate(self) -> float:
        return self.value.conjugate()

    # Not part of the `numbers` protocol, but what `statistics` reaches for:
    # `statistics._exact_ratio` tries `as_integer_ratio()` first and only falls
    # back to `numerator`/`denominator` for a `numbers.Rational`. Registering a
    # float-valued element as `Rational` would be a lie, so the ratio is what
    # puts it on the same footing as the float it wraps.
    def as_integer_ratio(self) -> tuple[int, int]:
        return self.value.as_integer_ratio()

    def is_integer(self) -> bool:
        return self.value.is_integer()

    @classmethod
    def read(cls: type[T], fp: IO[bytes], **kwargs: Any) -> T:
        return cls(read_fmt("d", fp)[0])  # type: ignore[call-arg]

    def write(self, fp: IO[bytes], **kwargs: Any) -> int:
        return write_fmt(fp, "d", self.value)


# Registration rather than inheritance: putting ``ABCMeta`` underneath the slots
# classes attrs recreates is more risk than the ABC mixins are worth, and those
# mixin members are written out explicitly above instead.
numbers.Real.register(NumericElement)


@define(repr=False, eq=False, order=False)
class IntegerElement(NumericElement):
    """
    Single integer value element that has a `value` attribute.

    Registered as a :py:class:`numbers.Integral`. Use with
    `@define(repr=False)` decorator.
    """

    value: int = field(default=0, converter=int)

    def __lshift__(self, other: Any) -> int:
        return self.value << other

    def __rshift__(self, other: Any) -> int:
        return self.value >> other

    def __and__(self, other: Any) -> int:
        return self.value & other

    def __xor__(self, other: Any) -> int:
        return self.value ^ other

    def __or__(self, other: Any) -> int:
        return self.value | other

    def __rlshift__(self, other: Any) -> int:
        return other << self.value

    def __rrshift__(self, other: Any) -> int:
        return other >> self.value

    def __rand__(self, other: Any) -> int:
        return other & self.value

    def __rxor__(self, other: Any) -> int:
        return other ^ self.value

    def __ror__(self, other: Any) -> int:
        return other | self.value

    def __invert__(self) -> int:
        return ~self.value

    def __index__(self) -> int:
        return self.value.__index__()

    @property
    def numerator(self) -> int:
        return self.value.numerator

    @property
    def denominator(self) -> int:
        return self.value.denominator

    # `int.is_integer` only exists from Python 3.12, so the inherited
    # delegation would raise `AttributeError` on 3.10 and 3.11. An integer is
    # integral on every version.
    def is_integer(self) -> bool:
        return True

    @classmethod
    def read(cls: type[T], fp: IO[bytes], **kwargs: Any) -> T:
        return cls(read_fmt("I", fp)[0])  # type: ignore[call-arg]

    def write(self, fp: IO[bytes], **kwargs: Any) -> int:
        return write_fmt(fp, "I", self.value)


numbers.Integral.register(IntegerElement)


@define(repr=False, eq=False, order=False)
class ShortIntegerElement(IntegerElement):
    """
    Single short integer element that has a `value` attribute.

    Use with `@define(repr=False)` decorator.
    """

    @classmethod
    def read(cls: type[T], fp: IO[bytes], **kwargs: Any) -> T:
        try:
            return cls(read_fmt("H2x", fp)[0])  # type: ignore[call-arg]
        except IOError as e:
            logger.error(e)
        return cls(read_fmt("H", fp)[0])  # type: ignore[call-arg]

    def write(self, fp: IO[bytes], **kwargs: Any) -> int:
        return write_fmt(fp, "H2x", self.value)


@define(repr=False, eq=False, order=False)
class ByteElement(IntegerElement):
    """
    Single 1-byte integer element that has a `value` attribute.

    Use with `@define(repr=False)` decorator.
    """

    @classmethod
    def read(cls: type[T], fp: IO[bytes], **kwargs: Any) -> T:
        try:
            return cls(read_fmt("B3x", fp)[0])  # type: ignore[call-arg]
        except IOError as e:
            logger.error(e)
        return cls(read_fmt("B", fp)[0])  # type: ignore[call-arg]

    def write(self, fp: IO[bytes], **kwargs: Any) -> int:
        return write_fmt(fp, "B3x", self.value)


@define(repr=False, eq=False, order=False)
class BooleanElement(IntegerElement):
    """
    Single bool value element that has a `value` attribute.

    Use with `@define(repr=False)` decorator.
    """

    value: bool = field(default=False, converter=bool)

    @classmethod
    def read(cls: type[T], fp: IO[bytes], **kwargs: Any) -> T:
        try:
            return cls(read_fmt("?3x", fp)[0])  # type: ignore[call-arg]
        except IOError as e:
            logger.error(e)
        return cls(read_fmt("?", fp)[0])  # type: ignore[call-arg]

    def write(self, fp: IO[bytes], **kwargs: Any) -> int:
        return write_fmt(fp, "?3x", self.value)


@define(repr=False, eq=False, order=False)
class StringElement(ValueElement):
    """
    Single unicode string.

    .. py:attribute:: value

        `str` value
    """

    value: str = ""

    @classmethod
    def read(cls: type[T], fp: IO[bytes], padding: int = 1, **kwargs: Any) -> T:
        return cls(read_unicode_string(fp, padding=padding))  # type: ignore[call-arg]

    def write(self, fp: IO[bytes], padding: int = 1, **kwargs: Any) -> int:
        return write_unicode_string(fp, self.value, padding=padding)


@define(repr=False)
class ListElement(BaseElement):
    """
    List-like element that has `items` list.
    """

    _items: list = field(factory=list, converter=list)

    def append(self, x: Any) -> None:
        return self._items.append(x)

    def extend(self, L: Any) -> None:
        return self._items.extend(L)

    def insert(self, i: int, x: Any) -> None:
        return self._items.insert(i, x)

    def remove(self, x: Any) -> None:
        return self._items.remove(x)

    def pop(self, *args: Any) -> Any:
        return self._items.pop(*args)

    def index(self, x: Any) -> int:
        return self._items.index(x)

    def count(self, x: Any) -> int:
        return self._items.count(x)

    def sort(self, *args: Any, **kwargs: Any) -> None:
        return self._items.sort(*args, **kwargs)

    def reverse(self) -> None:
        return self._items.reverse()

    def __len__(self) -> int:
        return self._items.__len__()

    def __iter__(self) -> Any:
        return self._items.__iter__()

    def __getitem__(self, key: Any) -> Any:
        return self._items.__getitem__(key)

    def __setitem__(self, key: Any, value: Any) -> None:
        return self._items.__setitem__(key, value)

    def __delitem__(self, key: Any) -> None:
        return self._items.__delitem__(key)

    def __repr__(self) -> str:
        return self._items.__repr__()

    def _repr_pretty_(self, p: Any, cycle: bool) -> None:
        if cycle:
            p.text("[...]")
            return

        with p.group(2, "[", "]"):
            p.breakable("")
            for idx in range(len(self._items)):
                if idx:
                    p.text(",")
                    p.breakable()
                value = self._items[idx]
                if isinstance(value, bytes):
                    value = trimmed_repr(value)
                p.pretty(value)
            p.breakable("")

    def write(self, fp: IO[bytes], *args: Any, **kwargs: Any) -> int:
        written = 0
        for item in self:
            if hasattr(item, "write"):
                written += item.write(fp, *args, **kwargs)
            elif isinstance(item, bytes):
                written += write_bytes(fp, item)
        return written


@define(repr=False)
class DictElement(BaseElement):
    """
    Dict-like element that has `items` OrderedDict.
    """

    _items: OrderedDict = field(factory=OrderedDict, converter=OrderedDict)

    def clear(self) -> None:
        return self._items.clear()

    def copy(self) -> OrderedDict:
        return self._items.copy()

    @classmethod
    def fromkeys(cls, seq: Any, *args: Any) -> "DictElement":
        return cls(OrderedDict.fromkeys(seq, *args))

    def get(self, key: Any, *args: Any) -> Any:
        key = self._key_converter(key)
        return self._items.get(key, *args)

    def items(self) -> Any:
        return self._items.items()

    def keys(self) -> Any:
        return self._items.keys()

    def pop(self, key: Any, *args: Any) -> Any:
        key = self._key_converter(key)
        return self._items.pop(key, *args)

    def popitem(self) -> Any:
        return self._items.popitem()

    def setdefault(self, key: Any, *args: Any) -> Any:
        key = self._key_converter(key)
        return self._items.setdefault(key, *args)

    def update(self, *args: Any) -> None:
        return self._items.update(*args)

    def values(self) -> Any:
        return self._items.values()

    def __len__(self) -> int:
        return self._items.__len__()

    def __iter__(self) -> Any:
        return self._items.__iter__()

    def __getitem__(self, key: Any) -> Any:
        key = self._key_converter(key)
        return self._items.__getitem__(key)

    def __setitem__(self, key: Any, value: Any) -> None:
        key = self._key_converter(key)
        return self._items.__setitem__(key, value)

    def __delitem__(self, key: Any) -> None:
        key = self._key_converter(key)
        return self._items.__delitem__(key)

    def __contains__(self, key: Any) -> bool:
        key = self._key_converter(key)
        return self._items.__contains__(key)

    def __repr__(self) -> str:
        return dict.__repr__(self._items)

    def _repr_pretty_(self, p: Any, cycle: bool) -> None:
        if cycle:
            p.text("{...}")
            return

        with p.group(2, "{", "}"):
            p.breakable("")
            for idx, key in enumerate(self._items):
                if idx:
                    p.text(",")
                    p.breakable()
                value = self._items[key]
                p.pretty(key)
                p.text(": ")
                if isinstance(value, bytes):
                    value = trimmed_repr(value)
                p.pretty(value)
            p.breakable("")

    @classmethod
    def _key_converter(cls, key: Any) -> Any:
        return key

    @classmethod
    def read(cls: type[T], fp: IO[bytes], *args: Any, **kwargs: Any) -> T:
        raise NotImplementedError

    def write(self, fp: IO[bytes], *args: Any, **kwargs: Any) -> int:
        written = 0
        for key in self:
            value = self[key]
            if hasattr(value, "write"):
                written += value.write(fp, *args, **kwargs)
            elif isinstance(value, bytes):
                written += write_bytes(fp, value)
        return written
