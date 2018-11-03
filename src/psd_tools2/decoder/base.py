from __future__ import absolute_import, unicode_literals, division
import attr
import io
from collections import OrderedDict
from psd_tools2.constants import ColorSpaceID
from psd_tools2.utils import read_fmt, write_fmt, trimmed_repr
from psd_tools2.validators import in_


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
            p.breakable('')


class ValueElement(BaseElement):
    """
    Single value element that has a `value` attribute.

    Use with `@attr.s(repr=False)` decorator.
    """
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


class NumericElement(ValueElement):

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


class IntegerElement(NumericElement):
    """
    Single integer or bool value element that has a `value` attribute.

    Use with `@attr.s(repr=False)` decorator.
    """
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


class ListElement(BaseElement):
    """
    List-like element that has `items` list.

    Use with `@attr.s(repr=False)` decorator.
    """

    def __len__(self):
        return self.items.__len__()

    def __iter__(self):
        return self.items.__iter__()

    def __getitem__(self, key):
        return self.items.__getitem__(key)

    def __setitem__(self, key, value):
        return self.items.__setitem__(key, value)

    def __delitem__(self, key):
        return self.items.__delitem__(key)

    def __repr__(self):
        return '%s%s' % (self.__class__.__name__, self.items.__repr__())

    def _repr_pretty_(self, p, cycle):
        if cycle:
            return "{name}[...]".format(name=self.__class__.__name__)

        with p.group(2, '{name}['.format(name=self.__class__.__name__), ']'):
            p.breakable('')
            for idx in range(len(self.items)):
                if idx:
                    p.text(',')
                    p.breakable()
                value = self.items[idx]
                if isinstance(value, bytes):
                    value = trimmed_repr(value)
                p.pretty(value)
            p.breakable('')

    def write(self, fp, *args, **kwargs):
        return sum(item.write(fp, *args, **kwargs) for item in self)


class DictElement(BaseElement):
    """
    Dict-like element that has `items` OrderedDict.

    Use with `@attr.s(repr=False)` decorator.
    """

    def __len__(self):
        return self.items.__len__()

    def __iter__(self):
        return self.items.__iter__()

    def __getitem__(self, key):
        return self.items.__getitem__(key)

    def __setitem__(self, key, value):
        return self.items.__setitem__(key, value)

    def __delitem__(self, key):
        return self.items.__delitem__(key)

    def __contains__(self, item):
        return self.items.__contains__(item)

    def __repr__(self):
        return '%s%s' % (self.__class__.__name__, dict.__repr__(self.items))

    def _repr_pretty_(self, p, cycle):
        if cycle:
            return "{name}[...]".format(name=self.__class__.__name__)

        with p.group(2, '{name}{{'.format(name=self.__class__.__name__), '}'):
            p.breakable('')
            for idx, key in enumerate(self.items):
                if idx:
                    p.text(',')
                    p.breakable()
                value = self.items[key]
                p.pretty(key)
                p.text(': ')
                if isinstance(value, bytes):
                    value = trimmed_repr(value)
                p.pretty(value)
            p.breakable('')

    def write(self, fp, *args, **kwargs):
        return sum(self.items[key].write(fp, *args, **kwargs) for key in self)
