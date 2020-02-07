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
from __future__ import absolute_import, unicode_literals, division
import attr
import io
import logging
from collections import OrderedDict
from enum import Enum
from psd_tools.utils import (
    read_fmt,
    write_fmt,
    trimmed_repr,
    read_unicode_string,
    write_unicode_string,
    write_bytes,
)

logger = logging.getLogger(__name__)


class BaseElement(object):
    """
    Base element of various PSD file structs. All the data objects in
    :py:mod:`psd_tools.psd` subpackage inherit from this class.

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
    def read(cls, fp):
        raise NotImplementedError()

    def write(self, fp):
        raise NotImplementedError()

    @classmethod
    def frombytes(self, data, *args, **kwargs):
        with io.BytesIO(data) as f:
            return self.read(f, *args, **kwargs)

    def tobytes(self, *args, **kwargs):
        with io.BytesIO() as f:
            self.write(f, *args, **kwargs)
            return f.getvalue()

    def validate(self):
        return attr.validate(self)

    def _repr_pretty_(self, p, cycle):
        if cycle:
            return "{name}(...)".format(name=self.__class__.__name__)

        with p.group(2, '{name}('.format(name=self.__class__.__name__), ')'):
            p.breakable('')
            fields = [f for f in attr.fields(self.__class__) if f.repr]
            for idx, field in enumerate(fields):
                if idx:
                    p.text(',')
                    p.breakable()
                p.text('{field}='.format(field=field.name))
                value = getattr(self, field.name)
                if isinstance(value, bytes):
                    p.text(trimmed_repr(value))
                elif isinstance(value, Enum):
                    p.text(value.name)
                else:
                    p.pretty(value)
            p.breakable('')

    def _find(self, condition=None):
        """
        Traversal API intended for debugging.
        """
        for _ in BaseElement._traverse(self, condition):
            yield _

    @staticmethod
    def _traverse(element, condition=None):
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
        elif attr.has(element.__class__):
            for field in attr.fields(element.__class__):
                child = getattr(element, field.name)
                for _ in BaseElement._traverse(child, condition):
                    yield _


@attr.s(slots=True)
class EmptyElement(BaseElement):
    """
    Empty element that does not have a value.
    """

    @classmethod
    def read(cls, fp, *args, **kwargs):
        return cls()

    def write(self, fp, *args, **kwargs):
        return 0


@attr.s(repr=False, eq=False, order=False)
class ValueElement(BaseElement):
    """
    Single value wrapper that has a `value` attribute.

    Pretty printing shows the internal value by default. Inherit with
    `@attr.s(repr=False)` decorator to keep this behavior.

    .. py:attribute:: value

        Internal value.
    """
    value = attr.ib(default=None)

    def __lt__(self, other):
        return self.value < other

    def __le__(self, other):
        return self.value <= other

    def __eq__(self, other):
        return self.value == other

    def __ne__(self, other):
        return self.value != other

    def __gt__(self, other):
        return self.value > other

    def __ge__(self, other):
        return self.value >= other

    def __add__(self, other):
        return self.value + other

    def __sub__(self, other):
        return self.value - other

    def __mul__(self, other):
        return self.value * other

    def __mod__(self, other):
        return self.value % other

    def __rmul__(self, other):
        return self.value.__rmul__(other)

    def __rmod__(self, other):
        return self.value.__rmod__(other)

    def __hash__(self):
        return self.value.__hash__()

    def __bool__(self):
        return self.value.__bool__()

    def __repr__(self):
        return self.value.__repr__()

    def _repr_pretty_(self, p, cycle):
        if cycle:
            return self.__repr__()
        if isinstance(self.value, bytes):
            p.text(trimmed_repr(self.value))
        else:
            p.pretty(self.value)


@attr.s(repr=False, eq=False, order=False)
class NumericElement(ValueElement):
    """
    Single value element that has a numeric `value` attribute.
    """
    value = attr.ib(default=0.0, type=float, converter=float)

    def __floordiv__(self, other):
        return self.value.__floordiv__(other)

    def __div__(self, other):
        return self.value.__div__(other)

    def __truediv__(self, other):
        return self.value.__truediv__(other)

    def __divmod__(self, other):
        return self.value.__divmod__(other)

    def __pow__(self, other):
        return self.value.__pow__(other)

    def __radd__(self, other):
        return self.value.__radd__(other)

    def __rsub__(self, other):
        return self.value.__rsub__(other)

    def __rfloordiv__(self, other):
        return self.value.__rfloordiv__(other)

    def __rdiv__(self, other):
        return self.value.__rdiv__(other)

    def __rtruediv__(self, other):
        return self.value.__rtruediv__(other)

    def __rdivmod__(self, other):
        return self.value.__rdivmod__(other)

    def __rpow__(self, other):
        return self.value.__rpow__(other)

    def __nonzero__(self):
        return self.value.__nonzero__()

    def __neg__(self):
        return self.value.__neg__()

    def __pos__(self):
        return self.value.__pos__()

    def __abs__(self):
        return self.value.__abs__()

    def __int__(self):
        return self.value.__int__()

    def __long__(self):
        return self.value.__long__()

    def __float__(self):
        return self.value.__float__()

    def __coerce__(self, other):
        return self.value.__coerce__(other)

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(read_fmt('d', fp)[0])

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'd', self.value)


@attr.s(repr=False, eq=False, order=False)
class IntegerElement(NumericElement):
    """
    Single integer value element that has a `value` attribute.

    Use with `@attr.s(repr=False)` decorator.
    """
    value = attr.ib(default=0, type=int, converter=int)

    def __cmp__(self, other):
        return self.value.__cmp__(other)

    def __lshift__(self, other):
        return self.value.__lshift__(other)

    def __rshift__(self, other):
        return self.value.__rshift__(other)

    def __and__(self, other):
        return self.value.__and__(other)

    def __xor__(self, other):
        return self.value.__xor__(other)

    def __or__(self, other):
        return self.value.__or__(other)

    def __rlshift__(self, other):
        return self.value.__rlshift__(other)

    def __rrshift__(self, other):
        return self.value.__rrshift__(other)

    def __rand__(self, other):
        return self.value.__rand__(other)

    def __rxor__(self, other):
        return self.value.__rxor__(other)

    def __ror__(self, other):
        return self.value.__ror__(other)

    def __invert__(self):
        return self.value.__invert__()

    def __oct__(self):
        return self.value.__oct__()

    def __hex__(self):
        return self.value.__hex__()

    def __index__(self):
        return self.value.__index__()

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(read_fmt('I', fp)[0])

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'I', self.value)


@attr.s(repr=False, eq=False, order=False)
class ShortIntegerElement(IntegerElement):
    """
    Single short integer element that has a `value` attribute.

    Use with `@attr.s(repr=False)` decorator.
    """

    @classmethod
    def read(cls, fp, **kwargs):
        try:
            return cls(read_fmt('H2x', fp)[0])
        except AssertionError as e:
            logger.error(e)
        return cls(read_fmt('H', fp)[0])

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'H2x', self.value)


@attr.s(repr=False, eq=False, order=False)
class ByteElement(IntegerElement):
    """
    Single 1-byte integer element that has a `value` attribute.

    Use with `@attr.s(repr=False)` decorator.
    """

    @classmethod
    def read(cls, fp, **kwargs):
        try:
            return cls(read_fmt('B3x', fp)[0])
        except AssertionError as e:
            logger.error(e)
        return cls(read_fmt('B', fp)[0])

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'B3x', self.value)


@attr.s(repr=False, eq=False, order=False)
class BooleanElement(IntegerElement):
    """
    Single bool value element that has a `value` attribute.

    Use with `@attr.s(repr=False)` decorator.
    """
    value = attr.ib(default=False, type=bool, converter=bool)

    @classmethod
    def read(cls, fp, **kwargs):
        try:
            return cls(read_fmt('?3x', fp)[0])
        except AssertionError as e:
            logger.error(e)
        return cls(read_fmt('?', fp)[0])

    def write(self, fp, **kwargs):
        return write_fmt(fp, '?3x', self.value)


@attr.s(repr=False, slots=True, eq=False, order=False)
class StringElement(ValueElement):
    """
    Single unicode string.

    .. py:attribute:: value

        `str` value
    """
    value = attr.ib(default='', type=str)

    @classmethod
    def read(cls, fp, padding=1, **kwargs):
        return cls(read_unicode_string(fp, padding=padding))

    def write(self, fp, padding=1, **kwargs):
        return write_unicode_string(fp, self.value, padding=padding)


@attr.s(repr=False)
class ListElement(BaseElement):
    """
    List-like element that has `items` list.
    """
    _items = attr.ib(factory=list, converter=list)

    def append(self, x):
        return self._items.append(x)

    def extend(self, L):
        return self._items.extend(L)

    def insert(self, i, x):
        return self._items.insert(i, x)

    def remove(self, x):
        return self._items.remove(x)

    def pop(self, *args):
        return self._items.pop(*args)

    def index(self, x):
        return self._items.index(x)

    def count(self, x):
        return self._items.count(x)

    def sort(self, *args, **kwargs):
        return self._items.sort(*args, **kwargs)

    def reverse(self):
        return self._items.reverse()

    def __len__(self):
        return self._items.__len__()

    def __iter__(self):
        return self._items.__iter__()

    def __getitem__(self, key):
        return self._items.__getitem__(key)

    def __setitem__(self, key, value):
        return self._items.__setitem__(key, value)

    def __delitem__(self, key):
        return self._items.__delitem__(key)

    def __repr__(self):
        return self._items.__repr__()

    def _repr_pretty_(self, p, cycle):
        if cycle:
            return "[...]".format(name=self.__class__.__name__)

        with p.group(2, '['.format(name=self.__class__.__name__), ']'):
            p.breakable('')
            for idx in range(len(self._items)):
                if idx:
                    p.text(',')
                    p.breakable()
                value = self._items[idx]
                if isinstance(value, bytes):
                    value = trimmed_repr(value)
                p.pretty(value)
            p.breakable('')

    def write(self, fp, *args, **kwargs):
        written = 0
        for item in self:
            if hasattr(item, 'write'):
                written += item.write(fp, *args, **kwargs)
            elif isinstance(item, bytes):
                written += write_bytes(fp, item)
        return written


@attr.s(repr=False)
class DictElement(BaseElement):
    """
    Dict-like element that has `items` OrderedDict.
    """
    _items = attr.ib(factory=OrderedDict, converter=OrderedDict)

    def clear(self):
        return self._items.clear()

    def copy(self):
        return self._items.copy()

    @classmethod
    def fromkeys(cls, seq, *args):
        return cls(OrderedDict.fromkeys(seq, *args))

    def get(self, key, *args):
        key = self._key_converter(key)
        return self._items.get(key, *args)

    def items(self):
        return self._items.items()

    def keys(self):
        return self._items.keys()

    def pop(self, key, *args):
        key = self._key_converter(key)
        return self._items.pop(key, *args)

    def popitem(self):
        return self._items.popitem()

    def setdefault(self, key, *args):
        key = self._key_converter(key)
        return self._items.setdefault(key, *args)

    def update(self, *args):
        return self._items.update(*args)

    def values(self):
        return self._items.values()

    def __len__(self):
        return self._items.__len__()

    def __iter__(self):
        return self._items.__iter__()

    def __getitem__(self, key):
        key = self._key_converter(key)
        return self._items.__getitem__(key)

    def __setitem__(self, key, value):
        key = self._key_converter(key)
        return self._items.__setitem__(key, value)

    def __delitem__(self, key):
        key = self._key_converter(key)
        return self._items.__delitem__(key)

    def __contains__(self, key):
        key = self._key_converter(key)
        return self._items.__contains__(key)

    def __repr__(self):
        return dict.__repr__(self._items)

    def _repr_pretty_(self, p, cycle):
        if cycle:
            return '{{...}'

        with p.group(2, '{', '}'):
            p.breakable('')
            for idx, key in enumerate(self._items):
                if idx:
                    p.text(',')
                    p.breakable()
                value = self._items[key]
                p.pretty(key)
                p.text(': ')
                if isinstance(value, bytes):
                    value = trimmed_repr(value)
                p.pretty(value)
            p.breakable('')

    @classmethod
    def _key_converter(cls, key):
        return key

    @classmethod
    def read(cls, fp, *args, **kwargs):
        raise NotImplementedError

    def write(self, fp, *args, **kwargs):
        written = 0
        for key in self:
            value = self[key]
            if hasattr(value, 'write'):
                written += value.write(fp, *args, **kwargs)
            elif isinstance(value, bytes):
                written += write_bytes(fp, value)
        return written
