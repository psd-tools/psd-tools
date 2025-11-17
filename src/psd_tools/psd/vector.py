"""
Vector mask, path, and stroke structure.
"""

import logging
from typing import Any, BinaryIO, Optional, Sequence, TypeVar

try:
    from typing import Self  # type: ignore[attr-defined]
except ImportError:
    from typing_extensions import Self

from attrs import define, field, astuple

from psd_tools.constants import PathResourceID
from psd_tools.psd.base import BaseElement, ListElement, ValueElement
from psd_tools.psd.descriptor import Descriptor
from psd_tools.psd.bin_utils import (
    is_readable,
    read_fmt,
    write_fmt,
    write_padding,
)
from psd_tools.registry import new_registry

logger = logging.getLogger(__name__)

TYPES, register = new_registry(attribute="selector")  # Path item types.

T_Path = TypeVar("T_Path", bound="Path")
T_Subpath = TypeVar("T_Subpath", bound="Subpath")
T_Knot = TypeVar("T_Knot", bound="Knot")
T_PathFillRule = TypeVar("T_PathFillRule", bound="PathFillRule")
T_ClipboardRecord = TypeVar("T_ClipboardRecord", bound="ClipboardRecord")
T_InitialFillRule = TypeVar("T_InitialFillRule", bound="InitialFillRule")
T_VectorMaskSetting = TypeVar("T_VectorMaskSetting", bound="VectorMaskSetting")
T_VectorStrokeContentSetting = TypeVar(
    "T_VectorStrokeContentSetting", bound="VectorStrokeContentSetting"
)


def decode_fixed_point(numbers: Sequence[int]) -> tuple[float, ...]:
    return tuple(float(x) / 0x01000000 for x in numbers)


def encode_fixed_point(numbers: Sequence[float]) -> tuple[int, ...]:
    return tuple(int(x * 0x01000000) for x in numbers)


@define(repr=False)
class Path(ListElement):
    """
    List-like Path structure. Elements are either PathFillRule,
    InitialFillRule, ClipboardRecord, ClosedPath, or OpenPath.
    """

    @classmethod
    def read(cls: type[T_Path], fp: BinaryIO, **kwargs: Any) -> T_Path:
        items = []
        while is_readable(fp, 26):
            selector = PathResourceID(read_fmt("H", fp)[0])
            kls = TYPES.get(selector)
            assert kls is not None
            items.append(kls.read(fp))
        return cls(items)

    def write(self, fp: BinaryIO, padding: int = 4, **kwargs: Any) -> int:
        written = 0
        for item in self:
            written += write_fmt(fp, "H", item.selector.value)
            written += item.write(fp)
        written += write_padding(fp, written, padding)
        return written


@define(repr=False)
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
    operation: int = 1  # Type of shape operation.
    _unknown1: int = 1
    _unknown2: int = 0
    index: int = 0  # type: ignore[assignment]  # Origination index.
    _unknown3: bytes = field(default=b"\x00" * 10, repr=False)

    @classmethod
    def read(cls: type[T_Subpath], fp: BinaryIO, **kwargs: Any) -> T_Subpath:
        items = []
        length, operation, _unknown1, _unknown2, index, _unknown3 = read_fmt(
            "HhH2I10s", fp
        )
        for _ in range(length):
            selector = PathResourceID(read_fmt("H", fp)[0])
            kls = TYPES.get(selector)
            assert kls is not None
            items.append(kls.read(fp))
        return cls(
            items=items,
            operation=operation,
            index=index,
            unknown1=_unknown1,
            unknown2=_unknown2,
            unknown3=_unknown3,
        )

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(
            fp,
            "HhH2I10s",
            len(self),
            self.operation,
            self._unknown1,
            self._unknown2,
            self.index,
            self._unknown3,
        )
        for item in self:
            written += write_fmt(fp, "H", item.selector.value)
            written += item.write(fp)
        return written

    def is_closed(self) -> bool:
        """
        Returns whether if the path is closed or not.

        :return: `bool`.
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        """Return a string representation of the subpath."""
        return "%s(index=%d, operation=%d)" % (
            self.__class__.__name__,
            self.index,
            self.operation,
        )

    def _repr_pretty_(self, p: Any, cycle: bool) -> None:
        if cycle:
            p.text(f"({self.__class__.__name__} ...)")
            return
        p.text(self.__repr__())
        super()._repr_pretty_(p, cycle)


@define(repr=False)
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

    preceding: tuple = (0.0,)
    anchor: tuple = (0.0,)
    leaving: tuple = (0.0,)

    @classmethod
    def read(cls: type[T_Knot], fp: BinaryIO, **kwargs: Any) -> T_Knot:
        preceding = decode_fixed_point(read_fmt("2i", fp))
        anchor = decode_fixed_point(read_fmt("2i", fp))
        leaving = decode_fixed_point(read_fmt("2i", fp))
        return cls(preceding, anchor, leaving)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        values = self.preceding + self.anchor + self.leaving
        return write_fmt(fp, "6i", *encode_fixed_point(values))


@register(PathResourceID.CLOSED_LENGTH)
class ClosedPath(Subpath):
    def is_closed(self) -> bool:
        return True


@register(PathResourceID.OPEN_LENGTH)
class OpenPath(Subpath):
    def is_closed(self) -> bool:
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
@define(repr=False)
class PathFillRule(BaseElement):
    """
    Path fill rule record, empty.
    """

    @classmethod
    def read(cls: type[T_PathFillRule], fp: BinaryIO, **kwargs: Any) -> T_PathFillRule:
        read_fmt("24x", fp)
        return cls()

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "24x")


@register(PathResourceID.CLIPBOARD)
@define(repr=False)
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

    top: int = 0
    left: int = 0
    bottom: int = 0
    right: int = 0
    resolution: int = 0

    @classmethod
    def read(
        cls: type[T_ClipboardRecord], fp: BinaryIO, **kwargs: Any
    ) -> T_ClipboardRecord:
        return cls(*decode_fixed_point(read_fmt("5i4x", fp)))  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "5i4x", *encode_fixed_point(astuple(self)))


@register(PathResourceID.INITIAL_FILL)
@define(repr=False)
class InitialFillRule(ValueElement):
    """
    Initial fill rule record.

    .. py:attribute:: rule

        A value of 1 means that the fill starts with all pixels. The value
        will be either 0 or 1.
    """

    value: int = field(default=0, converter=int)

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> Self:
        return cls(*read_fmt("H22x", fp))

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "H22x", *astuple(self))


@define(repr=False)
class VectorMaskSetting(BaseElement):
    """
    VectorMaskSetting structure.

    .. py:attribute:: version
    .. py:attribute:: path

        List of :py:class:`~psd_tools.psd.vector.Subpath` objects.
    """

    version: int = 3
    flags: int = 0
    path: Optional["Path"] = None

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> Self:
        version, flags = read_fmt("2I", fp)
        assert version == 3, "Unknown vector mask version %d" % version
        path = Path.read(fp)
        return cls(version=version, flags=flags, path=path)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "2I", self.version, self.flags)
        if self.path:
            written += self.path.write(fp)
        return written

    @property
    def invert(self) -> bool:
        """Flag to indicate that the vector mask is inverted."""
        return bool(self.flags & 1)

    @property
    def not_link(self) -> bool:
        """Flag to indicate that the vector mask is not linked."""
        return bool(self.flags & 2)

    @property
    def disable(self) -> bool:
        """Flag to indicate that the vector mask is disabled."""
        return bool(self.flags & 4)


@define(repr=False)
class VectorStrokeContentSetting(Descriptor):
    """
    Dict-like Descriptor-based structure. See
    :py:class:`~psd_tools.psd.descriptor.Descriptor`.

    .. py:attribute:: key
    .. py:attribute:: version
    """

    key: bytes = b"\x00\x00\x00\x00"
    version: int = 1

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> Self:
        key, version = read_fmt("4sI", fp)
        return cls(key=key, version=version, **cls._read_body(fp))

    def write(self, fp: BinaryIO, padding: int = 4, **kwargs: Any) -> int:
        written = write_fmt(fp, "4sI", self.key, self.version)
        written += self._write_body(fp)
        written += write_padding(fp, written, padding)
        return written
