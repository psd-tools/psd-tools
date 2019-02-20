"""
Linked layer structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import io
import logging

from psd_tools.constants import LinkedLayerType
from psd_tools.psd.base import BaseElement, ListElement
from psd_tools.psd.descriptor import DescriptorBlock
from psd_tools.validators import in_, range_
from psd_tools.utils import (
    read_fmt, write_fmt, read_length_block, write_length_block, is_readable,
    write_bytes, read_unicode_string, write_unicode_string,
    read_pascal_string, write_pascal_string, write_padding
)

logger = logging.getLogger(__name__)


class LinkedLayers(ListElement):
    """
    List of LinkedLayer structure. See :py:class:`.LinkedLayer`.
    """
    @classmethod
    def read(cls, fp, **kwargs):
        items = []
        while is_readable(fp, 8):
            data = read_length_block(fp, fmt='Q', padding=4)
            with io.BytesIO(data) as f:
                items.append(LinkedLayer.read(f))
        return cls(items)

    def write(self, fp, **kwargs):
        written = 0
        for item in self:
            written += write_length_block(fp, lambda f: item.write(f),
                                          fmt='Q', padding=4)
        return written


@attr.s(slots=True)
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
    kind = attr.ib(default=LinkedLayerType.ALIAS,
                   validator=in_(LinkedLayerType))
    version = attr.ib(default=1, validator=range_(1, 7))
    uuid = attr.ib(default='', type=str)
    filename = attr.ib(default='', type=str)
    filetype = attr.ib(default=b'\x00\x00\x00\x00', type=bytes)
    creator = attr.ib(default=b'\x00\x00\x00\x00', type=bytes)
    filesize = attr.ib(default=None)
    open_file = attr.ib(default=None)
    linked_file = attr.ib(default=None)
    timestamp = attr.ib(default=None)
    data = attr.ib(default=None)
    child_id = attr.ib(default=None)
    mod_time = attr.ib(default=None)
    lock_state = attr.ib(default=None)

    @classmethod
    def read(cls, fp, **kwargs):
        kind = LinkedLayerType(read_fmt('4s', fp)[0])
        version = read_fmt('I', fp)[0]
        assert 1 <= version and version <= 7, 'Invalid version %d' % (version)
        uuid = read_pascal_string(fp, 'macroman', padding=1)
        filename = read_unicode_string(fp)
        filetype, creator, datasize, open_file = read_fmt('4s4sQB', fp)
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
                timestamp = read_fmt('I4Bd', fp)
            filesize = read_fmt('Q', fp)[0]  # External file size.
            if version > 2:
                data = fp.read(datasize)
        elif kind == LinkedLayerType.ALIAS:
            read_fmt('8x', fp)
        if kind == LinkedLayerType.DATA:
            data = fp.read(datasize)
            assert len(data) == datasize, '(%d vs %d)' % (
                len(data), datasize
            )

        # The followings are not well documented...
        if version >= 5:
            child_id = read_unicode_string(fp)
        if version >= 6:
            mod_time = read_fmt('d', fp)[0]
        if version >= 7:
            lock_state = read_fmt('B', fp)[0]
        if kind == LinkedLayerType.EXTERNAL and version == 2:
            data = fp.read(datasize)

        return cls(kind, version, uuid, filename, filetype, creator, filesize,
                   open_file, linked_file, timestamp, data, child_id,
                   mod_time, lock_state)

    def write(self, fp, padding=1, **kwargs):
        written = write_fmt(fp, '4sI', self.kind.value, self.version)
        written += write_pascal_string(fp, self.uuid, 'macroman', padding=1)
        written += write_unicode_string(fp, self.filename)
        written += write_fmt(fp, '4s4sQB', self.filetype, self.creator,
                             len(self.data) if self.data is not None else 0,
                             self.open_file is not None)
        if self.open_file is not None:
            written += self.open_file.write(fp, padding=1)

        if self.kind == LinkedLayerType.EXTERNAL:
            written += self.linked_file.write(fp, padding=1)
            if self.version > 3:
                written += write_fmt(fp, 'I4Bd', *self.timestamp)
            written += write_fmt(fp, 'Q', self.filesize)
            if self.version > 2:
                written += write_bytes(fp, self.data)
        elif self.kind == LinkedLayerType.ALIAS:
            written += write_fmt(fp, '8x')
        if self.kind == LinkedLayerType.DATA:
            written += write_bytes(fp, self.data)

        if self.child_id is not None:
            written += write_unicode_string(fp, self.child_id)
        if self.mod_time is not None:
            written += write_fmt(fp, 'd', self.mod_time)
        if self.lock_state is not None:
            written += write_fmt(fp, 'B', self.lock_state)

        if self.kind == LinkedLayerType.EXTERNAL and self.version == 2:
            written += write_bytes(fp, self.data)

        written += write_padding(fp, written, padding)
        return written
