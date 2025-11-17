"""
Patterns structure.
"""

import io
import logging
from typing import Any, BinaryIO, Optional, TypeVar

try:
    from typing import Self  # type: ignore[attr-defined]
except ImportError:
    from typing_extensions import Self

from attrs import define, field

from psd_tools.compression import compress, decompress
from psd_tools.constants import ColorMode, Compression
from psd_tools.psd.base import BaseElement, ListElement
from psd_tools.psd.bin_utils import (
    is_readable,
    read_fmt,
    read_length_block,
    read_pascal_string,
    read_unicode_string,
    write_bytes,
    write_fmt,
    write_length_block,
    write_pascal_string,
    write_unicode_string,
)
from psd_tools.validators import in_

logger = logging.getLogger(__name__)

T_Patterns = TypeVar("T_Patterns", bound="Patterns")
T_Pattern = TypeVar("T_Pattern", bound="Pattern")


class Patterns(ListElement):
    """
    List of Pattern structure. See
    :py:class:`~psd_tools.psd.patterns.Pattern`.
    """

    @classmethod
    def read(cls: type[T_Patterns], fp: BinaryIO, **kwargs: Any) -> T_Patterns:
        items = []
        while is_readable(fp, 4):
            data = read_length_block(fp, padding=4)
            with io.BytesIO(data) as f:
                items.append(Pattern.read(f))
        return cls(items)  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = 0
        for item in self:
            written += write_length_block(fp, item.write, padding=4)
        return written


@define(repr=False)
class Pattern(BaseElement):
    """
    Pattern structure.

    .. py:attribute:: version
    .. py:attribute:: image_mode

        See :py:class:`ColorMode`

    .. py:attribute:: point

        Size in tuple.

    .. py:attribute:: name

        `str` name of the pattern.

    .. py:attribute:: pattern_id

        ID of this pattern.

    .. py:attribute:: color_table

        Color table if the mode is INDEXED.

    .. py:attribute:: data

        See :py:class:`VirtualMemoryArrayList`
    """

    version: int = 1
    image_mode: ColorMode = field(
        default=ColorMode.RGB, converter=ColorMode, validator=in_(ColorMode)
    )
    point: tuple[int, int] = field(default=(0, 0))
    name: str = ""
    pattern_id: str = ""
    color_table: list[tuple[int, int, int]] = field(factory=list)
    data: "VirtualMemoryArrayList" = field(default=None)

    @classmethod
    def read(cls: type[T_Pattern], fp: BinaryIO, **kwargs: Any) -> T_Pattern:
        version = read_fmt("I", fp)[0]
        assert version == 1, "Invalid version %d" % (version)
        image_mode = ColorMode(read_fmt("I", fp)[0])
        point = read_fmt("2h", fp)
        name = read_unicode_string(fp)
        pattern_id = read_pascal_string(fp, encoding="ascii", padding=1)
        color_table = None
        if image_mode == ColorMode.INDEXED:
            color_table = [read_fmt("3B", fp) for i in range(256)]
            read_fmt("4x", fp)

        data = VirtualMemoryArrayList.read(fp)
        return cls(version, image_mode, point, name, pattern_id, color_table, data)  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "2I", self.version, self.image_mode.value)
        written += write_fmt(fp, "2h", *self.point)
        written += write_unicode_string(fp, self.name)
        written += write_pascal_string(fp, self.pattern_id, encoding="ascii", padding=1)
        if self.color_table:
            for row in self.color_table:
                written += write_fmt(fp, "3B", *row)
            written += write_fmt(fp, "4x")
        written += self.data.write(fp)
        return written


@define(repr=False)
class VirtualMemoryArrayList(BaseElement):
    """
    VirtualMemoryArrayList structure. Container of channels.

    .. py:attribute:: version
    .. py:attribute:: rectangle

        Tuple of `int`

    .. py:attribute:: channels

        List of :py:class:`VirtualMemoryArray`
    """

    version: int = 3
    rectangle: tuple[int, int, int, int] = field(default=(0, 0, 0, 0))
    channels: list["VirtualMemoryArray"] = field(factory=list)

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> Self:
        version = read_fmt("I", fp)[0]
        assert version == 3, "Invalid version %d" % (version)

        data = read_length_block(fp)
        with io.BytesIO(data) as f:
            rectangle = read_fmt("4I", f)
            num_channels = read_fmt("I", f)[0]
            channels = []
            for _ in range(num_channels + 2):
                channels.append(VirtualMemoryArray.read(f))

        return cls(version, rectangle, channels)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "I", self.version)
        return written + write_length_block(fp, lambda f: self._write_body(f))

    def _write_body(self, fp: BinaryIO) -> int:
        written = write_fmt(fp, "4I", *self.rectangle)
        written += write_fmt(fp, "I", len(self.channels) - 2)
        for channel in self.channels:
            written += channel.write(fp)
        return written


@define(repr=False)
class VirtualMemoryArray(BaseElement):
    """
    VirtualMemoryArrayList structure, corresponding to each channel.

    .. py:attribute:: is_written
    .. py:attribute:: depth
    .. py:attribute:: rectangle
    .. py:attribute:: pixel_depth
    .. py:attribute:: compression
    .. py:attribute:: data
    """

    is_written: int = 0
    depth: Optional[int] = None
    rectangle: Optional[tuple[int, int, int, int]] = None
    pixel_depth: Optional[int] = None
    compression: Compression = field(
        default=Compression.RAW, converter=Compression, validator=in_(Compression)
    )
    data: bytes = b""

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> Self:
        is_written = read_fmt("I", fp)[0]
        if is_written == 0:
            return cls(is_written=is_written)
        length = read_fmt("I", fp)[0]
        if length == 0:
            return cls(is_written=is_written)
        depth = read_fmt("I", fp)[0]
        rectangle = read_fmt("4I", fp)
        pixel_depth, compression = read_fmt("HB", fp)
        data = fp.read(length - 23)
        return cls(is_written, depth, rectangle, pixel_depth, compression, data)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "I", self.is_written)
        if self.is_written == 0:
            return written
        if self.depth is None:
            written += write_fmt(fp, "I", 0)
            return written

        return written + write_length_block(fp, lambda f: self._write_body(f))

    def _write_body(self, fp: BinaryIO) -> int:
        assert self.depth is not None
        assert self.rectangle is not None
        written = write_fmt(fp, "I", self.depth)
        written += write_fmt(fp, "4I", *self.rectangle)
        written += write_fmt(fp, "HB", self.pixel_depth, self.compression.value)
        written += write_bytes(fp, self.data)
        return written

    def get_data(self) -> Optional[bytes]:
        """Get decompressed bytes."""
        if not self.is_written:
            return None
        assert self.rectangle is not None
        assert self.depth is not None
        width, height = self.rectangle[3], self.rectangle[2]
        return decompress(
            self.data, self.compression, width, height, self.depth, version=1
        )

    def set_data(
        self, size: tuple[int, int], data: bytes, depth: int, compression: int = 0
    ) -> None:
        """Set bytes."""
        from psd_tools.constants import Compression as CompressionEnum

        self.data = compress(
            data, CompressionEnum(compression), size[0], size[1], depth, version=1
        )
        self.depth = int(depth)
        self.pixel_depth = int(depth)
        self.rectangle = (0, 0, int(size[1]), int(size[0]))
        self.compression = Compression(compression)
        self.is_written = True
