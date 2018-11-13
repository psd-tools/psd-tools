"""
Image data section structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import logging
import io

from psd_tools2.compression import compress, decompress
from psd_tools2.constants import Compression
from psd_tools2.psd.base import BaseElement
from psd_tools2.validators import in_
from psd_tools2.utils import read_fmt, write_fmt, write_bytes

logger = logging.getLogger(__name__)


@attr.s
class ImageData(BaseElement):
    """
    Merged channel image data.

    .. py:attribute:: compression

        See :py:class:`~psd_tools2.constants.Compression`.

    .. py:attribute:: data
    """
    compression = attr.ib(default=Compression.RAW, converter=Compression,
                          validator=in_(Compression))
    data = attr.ib(default=b'', type=bytes, repr=False)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: :py:class:`.ImageData`
        """
        start_pos = fp.tell()
        compression = Compression(read_fmt('H', fp)[0])
        data = fp.read()  # TODO: Parse data here. Need header.
        logger.debug('  read image data, len=%d' % (fp.tell() - start_pos))
        return cls(compression, data)

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        :rtype: int
        """
        start_pos = fp.tell()
        written = write_fmt(fp, 'H', self.compression.value)
        written += write_bytes(fp, self.data)
        logger.debug('  wrote image data, len=%d' % (fp.tell() - start_pos))
        return written

    def get_data(self, header):
        """Get decompressed data.

        :param header: See :py:class:`~psd_tools2.psd.header.FileHeader`.
        :return: list of bytes corresponding each channel.
        :rtype: list
        """
        data = decompress(self.data, self.compression, header.width,
                          header.height * header.channels, header.depth,
                          header.version)
        plane_size = len(data) // header.channels
        with io.BytesIO(data) as f:
            return [f.read(plane_size) for _ in range(header.channels)]

    def set_data(self, data, header):
        """Set raw data and compress.

        :param data: list of raw data bytes corresponding channels.
        :param compression: compression type,
            see :py:class:`~psd_tools2.constants.Compression`.
        :param header: See :py:class:`~psd_tools2.psd.header.FileHeader`.
        :return: length of compressed data.
        """
        self.data = compress(b''.join(data), self.compression, header.width,
                             header.height * header.channels, header.depth,
                             header.version)
        return len(self.data)
