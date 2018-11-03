from __future__ import absolute_import, unicode_literals, division
import attr
import io
from collections import OrderedDict
from enum import Enum
from psd_tools2.utils import read_fmt, write_fmt, trimmed_repr
from psd_tools2.validators import in_


@attr.s
class BaseElement(object):
    """
    Base element of various PSD file structs.

    If FORMAT attribute is set, read/write method automatically parse binary.
    """
    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        """
        raise NotImplementedError()

    def write(self, fp):
        """Write the element to a file-like object.
        """
        raise NotImplementedError()

    @classmethod
    def frombytes(self, data, *args, **kwargs):
        """Read the element from bytes.

        :param data: bytes
        """
        with io.BytesIO(data) as f:
            return self.read(f, *args, **kwargs)

    def tobytes(self, *args, **kwargs):
        """Write the element to bytes.

        :rtype: bytes
        """
        with io.BytesIO() as f:
            self.write(f, *args, **kwargs)
            return f.getvalue()

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
                    value = trimmed_repr(value)
                    p.pretty(value)
                elif isinstance(value, Enum):
                    p.text(value.name)
                else:
                    p.pretty(value)
            p.breakable('')


@attr.s(repr=False)
class ValueElement(BaseElement):
    """
    Single value element that has a `value` attribute.

    Use with `@attr.s(repr=False)` decorator.
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

    def __repr__(self):
        return self.value.__repr__()

    def _repr_pretty_(self, p, cycle):
        if cycle:
            return self.__repr__()
        p.pretty(self.value)


@attr.s(repr=False)
class NumericElement(ValueElement):
    """
    Single value element that has a numeric `value` attribute.
    """
    value = attr.ib(default=1.0, type=float, converter=float)

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


@attr.s(repr=False)
class IntegerElement(NumericElement):
    """
    Single integer or bool value element that has a `value` attribute.

    Use with `@attr.s(repr=False)` decorator.
    """
    value = attr.ib(default=1, type=int, converter=int)

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


@attr.s(repr=False)
class BooleanElement(IntegerElement):
    """
    Single integer or bool value element that has a `value` attribute.

    Use with `@attr.s(repr=False)` decorator.
    """
    value = attr.ib(default=False, type=bool, converter=bool)


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
        return self._items.get(key, *args)

    def items(self):
        return self._items.items()

    def keys(self):
        return self._items.keys()

    def pop(self, key, *args):
        return self._items.pop(key, *args)

    def popitem(self):
        return self._items.popitem()

    def setdefault(self, key, *args):
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
        return self._items.__getitem__(key)

    def __setitem__(self, key, value):
        return self._items.__setitem__(key, value)

    def __delitem__(self, key):
        return self._items.__delitem__(key)

    def __contains__(self, item):
        return self._items.__contains__(item)

    def __repr__(self):
        return dict.__repr__(self._items)

    def _repr_pretty_(self, p, cycle):
        if cycle:
            return "{{...}".format(name=self.__class__.__name__)

        with p.group(2, '{{'.format(name=self.__class__.__name__), '}'):
            p.breakable('')
            for idx, key in enumerate(self._items):
                if idx:
                    p.text(',')
                    p.breakable()
                value = self._items[key]
                if hasattr(key, 'name'):
                    p.text(key.name)
                else:
                    p.pretty(key)
                p.text(': ')
                if isinstance(value, bytes):
                    value = trimmed_repr(value)
                p.pretty(value)
            p.breakable('')

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
