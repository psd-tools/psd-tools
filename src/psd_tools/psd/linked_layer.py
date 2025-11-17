"""
Linked layer structure.
"""

import io
import logging
from typing import Any, BinaryIO, Optional, TypeVar

from attrs import define, field

from psd_tools.constants import LinkedLayerType
from psd_tools.psd.base import BaseElement, ListElement
from psd_tools.psd.descriptor import DescriptorBlock
from psd_tools.psd.bin_utils import (
    is_readable,
    read_fmt,
    read_length_block,
    read_pascal_string,
    read_unicode_string,
    write_bytes,
    write_fmt,
    write_length_block,
    write_padding,
    write_pascal_string,
    write_unicode_string,
)
from psd_tools.validators import in_, range_

logger = logging.getLogger(__name__)

T_LinkedLayers = TypeVar("T_LinkedLayers", bound="LinkedLayers")
T_LinkedLayer = TypeVar("T_LinkedLayer", bound="LinkedLayer")


class LinkedLayers(ListElement):
    """
    List of LinkedLayer structure. See :py:class:`.LinkedLayer`.
    """

    @classmethod
    def read(cls: type[T_LinkedLayers], fp: BinaryIO, **kwargs: Any) -> T_LinkedLayers:
        items = []
        while is_readable(fp, 8):
            data = read_length_block(fp, fmt="Q", padding=4)
            with io.BytesIO(data) as f:
                items.append(LinkedLayer.read(f))
        return cls(items)  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = 0
        for item in self:
            written += write_length_block(fp, item.write, fmt="Q", padding=4)
        return written


@define(repr=False)
class LinkedLayer(BaseElement):
    """
    LinkedLayer structure.

    .. py:attribute:: kind
    .. py:attribute:: version
    .. py:attribute:: uuid
    .. py:attribute:: filename
    .. py:attribute:: filetype
    .. py:attribute:: creator
    .. py:attribute:: filesize
    .. py:attribute:: open_file
    .. py:attribute:: linked_file
    .. py:attribute:: timestamp
    .. py:attribute:: data
    .. py:attribute:: child_id
    .. py:attribute:: mod_time
    .. py:attribute:: lock_state
    """

    kind: LinkedLayerType = field(
        default=LinkedLayerType.ALIAS, validator=in_(LinkedLayerType)
    )
    version: int = field(default=1, validator=range_(1, 8))
    uuid: str = ""
    filename: str = ""
    filetype: bytes = b"\x00\x00\x00\x00"
    creator: bytes = b"\x00\x00\x00\x00"
    filesize: Optional[int] = None
    open_file: Optional[DescriptorBlock] = None
    linked_file: Optional[DescriptorBlock] = None
    timestamp: Optional[tuple] = None
    data: Optional[bytes] = None
    child_id: Optional[str] = None
    mod_time: Optional[float] = None
    lock_state: Optional[int] = None

    @classmethod
    def read(cls: type[T_LinkedLayer], fp: BinaryIO, **kwargs: Any) -> T_LinkedLayer:
        kind = LinkedLayerType(read_fmt("4s", fp)[0])
        version = read_fmt("I", fp)[0]
        assert 1 <= version and version <= 8, "Invalid version %d" % (version)
        uuid = read_pascal_string(fp, "macroman", padding=1)
        filename = read_unicode_string(fp)
        filetype, creator, datasize, open_file = read_fmt("4s4sQB", fp)
        if open_file:
            open_file = DescriptorBlock.read(fp, padding=1)
        else:
            open_file = None

        linked_file = None
        timestamp = None
        data = None
        filesize = None
        child_id = None
        mod_time = None
        lock_state = None

        if kind == LinkedLayerType.EXTERNAL:
            linked_file = DescriptorBlock.read(fp, padding=1)
            if version > 3:
                timestamp = read_fmt("I4Bd", fp)
            filesize = read_fmt("Q", fp)[0]  # External file size.
            if version > 2:
                data = fp.read(datasize)
        elif kind == LinkedLayerType.ALIAS:
            read_fmt("8x", fp)
        if kind == LinkedLayerType.DATA:
            data = fp.read(datasize)
            assert len(data) == datasize, "(%d vs %d)" % (len(data), datasize)

        # The followings are not well documented...
        if version >= 5:
            child_id = read_unicode_string(fp)
        if version >= 6:
            mod_time = read_fmt("d", fp)[0]
        if version >= 7:
            lock_state = read_fmt("B", fp)[0]
        if kind == LinkedLayerType.EXTERNAL and version == 2:
            data = fp.read(datasize)

        return cls(
            kind,
            version,
            uuid,
            filename,
            filetype,
            creator,
            filesize,
            open_file,
            linked_file,
            timestamp,
            data,
            child_id,
            mod_time,
            lock_state,
        )

    def write(self, fp: BinaryIO, padding: int = 1, **kwargs: Any) -> int:
        written = write_fmt(fp, "4sI", self.kind.value, self.version)
        written += write_pascal_string(fp, self.uuid, "macroman", padding=1)
        written += write_unicode_string(fp, self.filename)
        written += write_fmt(
            fp,
            "4s4sQB",
            self.filetype,
            self.creator,
            len(self.data) if self.data is not None else 0,
            self.open_file is not None,
        )
        if self.open_file is not None:
            written += self.open_file.write(fp, padding=1)

        if self.kind == LinkedLayerType.EXTERNAL:
            written += self.linked_file.write(fp, padding=1)  # type: ignore[union-attr]
            if self.version > 3:
                written += write_fmt(fp, "I4Bd", *self.timestamp)  # type: ignore[misc,operator]
            written += write_fmt(fp, "Q", self.filesize)
            if self.version > 2:
                assert self.data is not None
                written += write_bytes(fp, self.data)
        elif self.kind == LinkedLayerType.ALIAS:
            written += write_fmt(fp, "8x")
        if self.kind == LinkedLayerType.DATA:
            assert self.data is not None
            written += write_bytes(fp, self.data)

        if self.child_id is not None:
            written += write_unicode_string(fp, self.child_id)
        if self.mod_time is not None:
            written += write_fmt(fp, "d", self.mod_time)
        if self.lock_state is not None:
            written += write_fmt(fp, "B", self.lock_state)

        if self.kind == LinkedLayerType.EXTERNAL and self.version == 2:
            assert self.data is not None
            written += write_bytes(fp, self.data)

        written += write_padding(fp, written, padding)
        return written
