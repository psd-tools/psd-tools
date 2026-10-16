"""Color mode data structure."""

import array
import logging
from typing import IO, Any, TypeVar

from attrs import define

from psd_tools.psd.base import ValueElement
from psd_tools.psd.bin_utils import read_length_block, write_bytes, write_length_block

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="ColorModeData")

# The ``hdrt`` (HDR toning) block Photoshop writes into every 32-bit document;
# it rejects a 32-bit file whose color mode data lacks one (#869).
HDRT_DEFAULT = bytes.fromhex(
    "68647274000000033f000000000000020000000800440065006600610075006c00740000000200020000000000ff00ff010100000000000000004180000000000001000000003f800000"
)


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
    def read(cls: type[T], fp: IO[bytes], **kwargs: Any) -> T:
        """Read the structure from a file-like object."""
        value = read_length_block(fp)
        logger.debug("reading color mode data, len=%d" % (len(value)))
        # TODO: Parse color table.
        return cls(value)

    def write(self, fp: IO[bytes], **kwargs: Any) -> int:
        """Write the structure to a file-like object and return the bytes written."""

        def writer(f: IO[bytes]) -> int:
            return write_bytes(f, self.value)

        logger.debug("writing color mode data, len=%d" % (len(self.value)))
        return write_length_block(fp, writer)

    def interleave(self) -> bytes:
        """
        Return interleaved color table in bytes.

        :raises ValueError: if the table is shorter than 256 entries.
        """
        if len(self.value) < 768:
            raise ValueError(
                "Color table is %d bytes, expected at least 768" % len(self.value)
            )
        return b"".join(
            array.array(
                "B", [(self.value[i]), (self.value[i + 256]), (self.value[i + 512])]
            ).tobytes()
            for i in range(256)
        )
