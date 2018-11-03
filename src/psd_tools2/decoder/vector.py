"""
Vector mask and stroke structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import logging

from psd_tools2.decoder.base import BaseElement
from psd_tools2.decoder.path import Path
from psd_tools2.utils import (
    read_fmt, write_fmt, read_length_block, write_length_block, is_readable,
    write_bytes
)

logger = logging.getLogger(__name__)


@attr.s
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
