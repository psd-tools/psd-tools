"""
Vector mask, path, and stroke structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import logging

from psd_tools.psd.base import BaseElement, ListElement, ValueElement
from psd_tools.constants import PathResourceID
from psd_tools.psd.descriptor import Descriptor
from psd_tools.utils import (
    read_fmt, write_fmt, is_readable, write_padding, new_registry
)

logger = logging.getLogger(__name__)

TYPES, register = new_registry(attribute='selector')  # Path item types.


def decode_fixed_point(numbers):
    return tuple(float(x) / 0x01000000 for x in numbers)


def encode_fixed_point(numbers):
    return tuple(int(x * 0x01000000) for x in numbers)


@attr.s(repr=False, slots=True)
class Path(ListElement):
    """
    List-like Path structure. Elements are either PathFillRule,
    InitialFillRule, ClipboardRecord, ClosedPath, or OpenPath.
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


@attr.s(repr=False, slots=True)
class Subpath(ListElement):
    """
    Subpath element. This is a list of Knot objects.

    .. note:: There are undocumented data associated with this structure.

    .. py:attribute:: operation

        `int` value indicating how multiple subpath should be combined:

        1: Or (union), 2: Not-Or, 3: And (intersect), 0: Xor (exclude)

        The first path element is applied to the background surface.
        Intersection does not have strokes.

    .. py:attribute:: index

        `int` index that specifies corresponding origination object.
    """

    # Undocumented data that seem to contain path operation info.
    operation = attr.ib(default=1, type=int)  # Type of shape operation.
    _unknown1 = attr.ib(default=1, type=int)
    _unknown2 = attr.ib(default=0, type=int)
    index = attr.ib(default=0, type=int)  # Origination index.
    _unknown3 = attr.ib(default=b'\x00' * 10, type=bytes, repr=False)

    @classmethod
    def read(cls, fp):
        items = []
        length, operation, _unknown1, _unknown2, index, _unknown3 = read_fmt(
            'HhH2I10s', fp
        )
        for _ in range(length):
            selector = PathResourceID(read_fmt('H', fp)[0])
            kls = TYPES.get(selector)
            items.append(kls.read(fp))
        return cls(
            items=items,
            operation=operation,
            index=index,
            unknown1=_unknown1,
            unknown2=_unknown2,
            unknown3=_unknown3
        )

    def write(self, fp):
        written = write_fmt(
            fp, 'HhH2I10s', len(self), self.operation, self._unknown1,
            self._unknown2, self.index, self._unknown3
        )
        for item in self:
            written += write_fmt(fp, 'H', item.selector.value)
            written += item.write(fp)
        return written

    def is_closed(self):
        """
        Returns whether if the path is closed or not.

        :return: `bool`.
        """
        raise NotImplementedError

    # TODO: Make subpath repr better.
    # def __repr__(self):


@attr.s(repr=False, slots=True)
class Knot(BaseElement):
    """
    Knot element consisting of 3 control points for Bezier curves.

    .. py:attribute:: preceding

        (y, x) tuple of preceding control point in relative coordinates.

    .. py:attribute:: anchor

        (y, x) tuple of anchor point in relative coordinates.

    .. py:attribute:: leaving

        (y, x) tuple of leaving control point in relative coordinates.

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
    def is_closed(self):
        return True


@register(PathResourceID.OPEN_LENGTH)
class OpenPath(Subpath):
    def is_closed(self):
        return False


@register(PathResourceID.CLOSED_KNOT_LINKED)
class ClosedKnotLinked(Knot):
    pass


@register(PathResourceID.CLOSED_KNOT_UNLINKED)
class ClosedKnotUnlinked(Knot):
    pass


@register(PathResourceID.OPEN_KNOT_LINKED)
class OpenKnotLinked(Knot):
    pass


@register(PathResourceID.OPEN_KNOT_UNLINKED)
class OpenKnotUnlinked(Knot):
    pass


@register(PathResourceID.PATH_FILL)
@attr.s(repr=False, slots=True)
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
@attr.s(repr=False, slots=True)
class ClipboardRecord(BaseElement):
    """
    Clipboard record.

    .. py:attribute:: top

        Top position in `int`

    .. py:attribute:: left

        Left position in `int`

    .. py:attribute:: bottom

        Bottom position in `int`

    .. py:attribute:: right

        Right position in `int`

    .. py:attribute:: resolution

        Resolution in `int`
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
@attr.s(repr=False, slots=True)
class InitialFillRule(ValueElement):
    """
    Initial fill rule record.

    .. py:attribute:: rule

        A value of 1 means that the fill starts with all pixels. The value
        will be either 0 or 1.
    """
    value = attr.ib(default=0, converter=int, type=int)

    @classmethod
    def read(cls, fp):
        return cls(*read_fmt('H22x', fp))

    def write(self, fp):
        return write_fmt(fp, 'H22x', *attr.astuple(self))


@attr.s(repr=False, slots=True)
class VectorMaskSetting(BaseElement):
    """
    VectorMaskSetting structure.

    .. py:attribute:: version
    .. py:attribute:: path

        List of :py:class:`~psd_tools.psd.vector.Subpath` objects.
    """
    version = attr.ib(default=3, type=int)
    flags = attr.ib(default=0, type=int)
    path = attr.ib(default=None)

    @classmethod
    def read(cls, fp, **kwargs):
        version, flags = read_fmt('2I', fp)
        assert version == 3, 'Unknown vector mask version %d' % version
        path = Path.read(fp)
        return cls(version, flags, path)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, '2I', self.version, self.flags)
        written += self.path.write(fp)
        return written

    @property
    def invert(self):
        """Flag to indicate that the vector mask is inverted."""
        return bool(self.flags & 1)

    @property
    def not_link(self):
        """Flag to indicate that the vector mask is not linked."""
        return bool(self.flags & 2)

    @property
    def disable(self):
        """Flag to indicate that the vector mask is disabled."""
        return bool(self.flags & 4)


@attr.s(repr=False, slots=True)
class VectorStrokeContentSetting(Descriptor):
    """
    Dict-like Descriptor-based structure. See
    :py:class:`~psd_tools.psd.descriptor.Descriptor`.

    .. py:attribute:: key
    .. py:attribute:: version
    """
    key = attr.ib(default=b'\x00\x00\x00\x00', type=bytes)
    version = attr.ib(default=1, type=int)

    @classmethod
    def read(cls, fp, **kwargs):
        key, version = read_fmt('4sI', fp)
        return cls(key=key, version=version, **cls._read_body(fp))

    def write(self, fp, padding=4, **kwargs):
        written = write_fmt(fp, '4sI', self.key, self.version)
        written += self._write_body(fp)
        written += write_padding(fp, written, padding)
        return written
