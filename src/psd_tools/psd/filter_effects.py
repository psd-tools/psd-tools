"""
Filter effects structure.
"""

import io
import logging
from typing import Any, BinaryIO, Optional, TypeVar

from attrs import define, field

from psd_tools.psd.base import BaseElement, ListElement
from psd_tools.psd.bin_utils import (
    is_readable,
    read_fmt,
    read_length_block,
    read_pascal_string,
    write_bytes,
    write_fmt,
    write_length_block,
    write_pascal_string,
)

logger = logging.getLogger(__name__)

T_FilterEffects = TypeVar("T_FilterEffects", bound="FilterEffects")
T_FilterEffect = TypeVar("T_FilterEffect", bound="FilterEffect")
T_FilterEffectChannel = TypeVar("T_FilterEffectChannel", bound="FilterEffectChannel")
T_FilterEffectExtra = TypeVar("T_FilterEffectExtra", bound="FilterEffectExtra")


@define(repr=False)
class FilterEffects(ListElement):
    """
    List-like FilterEffects structure. See :py:class:`FilterEffect`.

    .. py:attribute:: version
    """

    version: int = 1

    @classmethod
    def read(
        cls: type[T_FilterEffects], fp: BinaryIO, **kwargs: Any
    ) -> T_FilterEffects:
        version = read_fmt("I", fp)[0]
        assert version in (1, 2, 3), "Invalid version %d" % (version)
        items = []
        while is_readable(fp, 8):
            with io.BytesIO(read_length_block(fp, fmt="Q", padding=4)) as f:
                items.append(FilterEffect.read(f))
        return cls(version=version, items=items)  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "I", self.version)
        for item in self:
            written += write_length_block(fp, item.write, fmt="Q", padding=4)
        return written


@define(repr=False)
class FilterEffect(BaseElement):
    """
    FilterEffect structure.

    .. py:attribute:: uuid
    .. py:attribute:: version
    .. py:attribute:: rectangle
    .. py:attribute:: depth
    .. py:attribute:: max_channels
    .. py:attribute:: channels

        List of :py:class:`FilterEffectChannel`.

    .. py:attribute:: extra

        See :py:class:`FilterEffectExtra`.
    """

    uuid: Optional[str] = None
    version: Optional[int] = None
    rectangle: Optional[tuple] = None
    depth: Optional[int] = None
    max_channels: Optional[int] = None
    channels: Optional[list] = None
    extra: Optional[object] = None

    @classmethod
    def read(cls: type[T_FilterEffect], fp: BinaryIO, **kwargs: Any) -> T_FilterEffect:
        uuid = read_pascal_string(fp, encoding="ascii", padding=1)
        version = read_fmt("I", fp)[0]
        assert version <= 1, "Invalid version %d" % (version)
        with io.BytesIO(read_length_block(fp, fmt="Q")) as f:
            rectangle, depth, max_channels, channels = cls._read_body(f)
        # Documentation is incorrect here.
        extra = FilterEffectExtra.read(fp) if is_readable(fp) else None
        return cls(
            uuid=uuid,
            version=version,
            rectangle=rectangle,
            depth=depth,
            max_channels=max_channels,
            channels=channels,
            extra=extra,
        )

    @classmethod
    def _read_body(cls, fp: BinaryIO) -> tuple[tuple, int, int, list]:
        rectangle = read_fmt("4i", fp)
        depth, max_channels = read_fmt("2I", fp)
        channels = []
        for _ in range(max_channels + 2):
            channels.append(FilterEffectChannel.read(fp))
        return rectangle, depth, max_channels, channels

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_pascal_string(fp, self.uuid or "", encoding="ascii", padding=1)
        written += write_fmt(fp, "I", self.version)

        def writer(f: BinaryIO) -> int:
            return self._write_body(f)

        written += write_length_block(fp, writer, fmt="Q")

        if self.extra is not None and hasattr(self.extra, "write"):
            written += self.extra.write(fp)  # type: ignore[attr-defined]
        return written

    def _write_body(self, fp: BinaryIO) -> int:
        assert self.rectangle is not None
        assert self.depth is not None
        assert self.max_channels is not None
        assert self.channels is not None
        written = write_fmt(fp, "4i", *self.rectangle)
        written += write_fmt(fp, "2I", self.depth, self.max_channels)
        for channel in self.channels:
            written += channel.write(fp)
        return written


@define(repr=False)
class FilterEffectChannel(BaseElement):
    """
    FilterEffectChannel structure.

    .. py:attribute:: is_written
    .. py:attribute:: compression
    .. py:attribute:: data
    """

    is_written: int = 0
    compression: Optional[int] = None
    data: bytes = b""

    @classmethod
    def read(
        cls: type[T_FilterEffectChannel], fp: BinaryIO, **kwargs: Any
    ) -> T_FilterEffectChannel:
        is_written = read_fmt("I", fp)[0]
        if is_written == 0:
            return cls(is_written=is_written)
        data = read_length_block(fp, fmt="Q")
        if len(data) == 0:
            return cls(is_written=is_written)
        with io.BytesIO(data) as f:
            compression = read_fmt("H", f)[0]
            data = f.read()
        return cls(is_written, compression, data)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "I", self.is_written)
        if self.is_written == 0:
            return written

        def writer(f: BinaryIO) -> int:
            if self.compression is None:
                return 0
            length = write_fmt(f, "H", self.compression)
            length += write_bytes(f, self.data)
            return length

        written += write_length_block(fp, writer, fmt="Q")
        return written


@define(repr=False)
class FilterEffectExtra(BaseElement):
    """
    FilterEffectExtra structure.

    .. py:attribute:: is_written
    .. py:attribute:: rectangle
    .. py:attribute:: compression
    .. py:attribute:: data
    """

    is_written: int = 0
    rectangle: list = field(factory=lambda: [0, 0, 0, 0], converter=list)
    compression: int = 0
    data: bytes = b""

    @classmethod
    def read(
        cls: type[T_FilterEffectExtra], fp: BinaryIO, **kwargs: Any
    ) -> T_FilterEffectExtra:
        is_written = read_fmt("B", fp)[0]
        if not is_written:
            return cls(is_written=is_written)

        rectangle = read_fmt("4i", fp)
        compression = 0
        data = b""
        with io.BytesIO(read_length_block(fp, fmt="Q")) as f:
            compression = read_fmt("H", f)[0]
            data = f.read()

        return cls(
            is_written=is_written,
            rectangle=rectangle,
            compression=compression,
            data=data,
        )

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "B", self.is_written)

        def writer(f: BinaryIO) -> int:
            length = write_fmt(f, "H", self.compression)
            length += write_bytes(f, self.data)
            return length

        if self.is_written:
            written += write_fmt(fp, "4i", *self.rectangle)
            written += write_length_block(fp, writer, fmt="Q")
        return written
