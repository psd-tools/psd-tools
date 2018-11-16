"""
Vector mask and stroke structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import logging

from psd_tools2.psd.base import BaseElement
from psd_tools2.psd.descriptor import Descriptor
from psd_tools2.psd.path import Path
from psd_tools2.utils import (
    read_fmt, write_fmt, read_length_block, write_length_block, is_readable,
    write_bytes, write_padding
)
from psd_tools2.validators import in_

logger = logging.getLogger(__name__)


@attr.s(slots=True)
class VectorMaskSetting(BaseElement):
    """
    VectorMaskSetting structure.

    .. py:attribute:: version
    .. py:attribute:: invert
    .. py:attribute:: not_link
    .. py:attribute:: disable
    .. py:attribute:: path
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
        return self.flags & 1

    @property
    def not_link(self):
        return self.flags & 2

    @property
    def disable(self):
        return self.flags & 4


@attr.s(repr=False, slots=True)
class VectorStrokeContentSetting(Descriptor):
    """
    Dict-like Descriptor-based structure. See
    :py:class:`~psd_tools2.psd.descriptor.Descriptor`.

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
