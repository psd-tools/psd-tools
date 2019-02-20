"""
Color mode data structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import logging

from psd_tools.psd.base import ValueElement
from psd_tools.utils import (
    read_length_block, write_length_block, write_bytes
)

logger = logging.getLogger(__name__)


@attr.s(repr=False, slots=True)
class ColorModeData(ValueElement):
    """
    Color mode data section of the PSD file.

    For indexed color images the data is the color table for the image in a
    non-interleaved order.

    Duotone images also have this data, but the data format is undocumented.
    """
    value = attr.ib(default=b'', type=bytes)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: ColorModeData
        """
        value = read_length_block(fp)
        logger.debug('reading color mode data, len=%d' % (len(value)))
        # TODO: Parse color table.
        return cls(value)

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        def writer(f):
            return write_bytes(f, self.value)

        logger.debug('writing color mode data, len=%d' % (len(self.value)))
        return write_length_block(fp, writer)

    def interleave(self):
        import array
        if bytes == str:
            return b''.join(
                array.array('B', [
                    ord(self.value[i]),
                    ord(self.value[i + 256]),
                    ord(self.value[i + 512])
                ]).tostring()
                for i in range(256)
            )
        else:
            return b''.join(
                array.array('B', [
                    (self.value[i]),
                    (self.value[i + 256]),
                    (self.value[i + 512])
                ]).tobytes()
                for i in range(256)
            )
