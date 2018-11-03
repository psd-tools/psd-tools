"""
Path resources structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import logging

from psd_tools2.constants import PathResourceID
from psd_tools2.decoder.base import BaseElement, ListElement
from psd_tools2.utils import (
    read_fmt, write_fmt, write_padding, is_readable, new_registry,
)

logger = logging.getLogger(__name__)


TYPES, register = new_registry(attribute='selector')


def decode_fixed_point(numbers):
    return tuple(float(x) / 0x01000000 for x in numbers)


def encode_fixed_point(numbers):
    return tuple(int(x * 0x01000000) for x in numbers)


@attr.s(repr=False)
class Path(ListElement):
    """
    List-like Path structure. Elements are either of Knot.
    """
    @classmethod
    def read(cls, fp):
        items = []
        while is_readable(fp, 26):
            selector = PathResourceID(read_fmt('H', fp)[0])
            kls = TYPES.get(selector)
            items.append(kls.read(fp))
        return cls(items)

    def write(self, fp, padding=4):
        written = 0
        for item in self:
            written += write_fmt(fp, 'H', item.selector.value)
            written += item.write(fp)
        written += write_padding(fp, written, padding)
        return written


@attr.s(repr=False)
class Subpath(ListElement):
    """
    Subpath element.
    """

    # Undocumented data, that should be zeros.
    _unknown = attr.ib(default=b'\x00' * 22, type=bytes, repr=False)

    @classmethod
    def read(cls, fp):
        items = []
        length, _unknown = read_fmt('H22s', fp)
        for _ in range(length):
            selector = PathResourceID(read_fmt('H', fp)[0])
            kls = TYPES.get(selector)
            items.append(kls.read(fp))
        return cls(items=items, unknown=_unknown)

    def write(self, fp):
        written = write_fmt(fp, 'H22s', len(self), self._unknown)
        for item in self:
            written += write_fmt(fp, 'H', item.selector.value)
            written += item.write(fp)
        return written


@attr.s
class Knot(BaseElement):
    """
    Knot element consisting of 3 control point for Bezier curves.

    ..py:attribute: preceding
    ..py:attribute: anchor
    ..py:attribute: leaving
    """
    preceding = attr.ib(default=(0., 0.), type=tuple)
    anchor = attr.ib(default=(0., 0.), type=tuple)
    leaving = attr.ib(default=(0., 0.), type=tuple)

    @classmethod
    def read(cls, fp):
        preceding = decode_fixed_point(read_fmt('2i', fp))
        anchor = decode_fixed_point(read_fmt('2i', fp))
        leaving = decode_fixed_point(read_fmt('2i', fp))
        return cls(preceding, anchor, leaving)

    def write(self, fp):
        values = self.preceding + self.anchor + self.leaving
        return write_fmt(fp, '6i', *encode_fixed_point(values))


@register(PathResourceID.CLOSED_LENGTH)
class ClosedPath(Subpath):
    pass


@register(PathResourceID.OPEN_LENGTH)
class OpenPath(Subpath):
    pass


@register(PathResourceID.CLOSED_KNOT_LINKED)
class OpenKnotLinked(Knot):
    pass


@register(PathResourceID.CLOSED_KNOT_UNLINKED)
class OpenKnotLinked(Knot):
    pass


@register(PathResourceID.OPEN_KNOT_LINKED)
class OpenKnotLinked(Knot):
    pass


@register(PathResourceID.OPEN_KNOT_UNLINKED)
class OpenKnotLinked(Knot):
    pass


@register(PathResourceID.PATH_FILL)
@attr.s
class PathFillRule(BaseElement):
    """
    Path fill rule record, empty.
    """
    @classmethod
    def read(cls, fp):
        read_fmt('24x', fp)
        return cls()

    def write(self, fp):
        return write_fmt(fp, '24x')


@register(PathResourceID.CLIPBOARD)
@attr.s
class ClipboardRecord(BaseElement):
    """
    Clipboard record.

    ..py:attribute: top
    ..py:attribute: left
    ..py:attribute: bottom
    ..py:attribute: right
    ..py:attribute: resolution
    """
    top = attr.ib(default=0, type=int)
    left = attr.ib(default=0, type=int)
    bottom = attr.ib(default=0, type=int)
    right = attr.ib(default=0, type=int)
    resolution = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp):
        return cls(*decode_fixed_point(read_fmt('5i4x', fp)))

    def write(self, fp):
        return write_fmt(fp, '5i4x', *encode_fixed_point(attr.astuple(self)))


@register(PathResourceID.INITIAL_FILL)
@attr.s
class InitialFillRule(BaseElement):
    """
    Initial fill rule record.

    ..py:attribute: rule
    """
    rule = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp):
        return cls(*read_fmt('H22x', fp))

    def write(self, fp):
        return write_fmt(fp, 'H22x', *attr.astuple(self))
