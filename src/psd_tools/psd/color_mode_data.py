"""
Color mode data structure.
"""

import array
import logging

from attrs import define

from psd_tools.psd.base import ValueElement
from psd_tools.utils import read_length_block, write_bytes, write_length_block

logger = logging.getLogger(__name__)


@define(repr=False)
class ColorModeData(ValueElement):
    """
    Color mode data section of the PSD file.

    For indexed color images the data is the color table for the image in a
    non-interleaved order.

    Duotone images also have this data, but the data format is undocumented.
    """

    value: bytes = b""

    @classmethod
    def read(cls, fp):
        value = read_length_block(fp)
        logger.debug("reading color mode data, len=%d" % (len(value)))
        # TODO: Parse color table.
        return cls(value)

    def write(self, fp):
        def writer(f):
            return write_bytes(f, self.value)

        logger.debug("writing color mode data, len=%d" % (len(self.value)))
        return write_length_block(fp, writer)

    def interleave(self):
        """
        Returns interleaved color table in bytes.
        """

        return b"".join(
            array.array(
                "B", [(self.value[i]), (self.value[i + 256]), (self.value[i + 512])]
            ).tobytes()
            for i in range(256)
        )
