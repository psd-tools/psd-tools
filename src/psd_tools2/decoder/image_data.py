"""
Image data section structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import io
import logging

import array
import packbits
import zlib
from psd_tools.compression import decode_prediction

from psd_tools2.constants import Compression
from psd_tools2.decoder.base import BaseElement
from psd_tools2.validators import in_
from psd_tools2.utils import (
    read_fmt, write_fmt, write_bytes, read_be_array, write_be_array
)

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

        :param header: See :py:class:`~psd_tools2.decoder.header.FileHeader`.
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
        :param header: See :py:class:`~psd_tools2.decoder.header.FileHeader`.
        :return: length of compressed data.
        """
        self.data = compress(b''.join(data), self.compression, header.width,
                             header.height * header.channels, header.depth,
                             header.version)
        return len(self.data)


def decompress(data, compression, width, height, depth, version):
    """Decompress raw data.

    :param data: compressed data bytes.
    :param compression: compression type,
            see :py:class:`~psd_tools2.constants.Compression`.
    :param width: width.
    :param height: height.
    :param depth: bit depth of the pixel.
    :param version: psd file version.
    :return: decompressed data bytes.
    """
    bytes_per_pixel = depth // 8
    length = width * height * bytes_per_pixel

    result = None
    if compression == Compression.RAW:
        result = data[:length]
    elif compression == Compression.PACK_BITS:
        with io.BytesIO(data) as fp:
            bytes_counts = read_be_array(
                ('H', 'I')[version - 1], height, fp
            )
            result = b''
            for count in bytes_counts:
                result += packbits.decode(fp.read(count))
    elif compression == Compression.ZIP:
        result = zlib.decompress(data)
    else:
        decompressed = zlib.decompress(data)
        result = decode_prediction(decompressed, w, h, bytes_per_pixel)

    assert len(result) == length, 'len=%d, expected=%d' % (
        len(result), length
    )

    return result


def compress(data, compression, width, height, depth, version=1):
    """Compress raw data.

    :param data: raw data bytes to write.
    :param compression: compression type, see :py:class:`.Compression`.
    :param width: width.
    :param height: height.
    :param depth: bit depth of the pixel.
    :param version: psd file version.
    :return: compressed data bytes.
    """
    bytes_per_pixel = depth // 8

    if compression == Compression.RAW:
        result = data
    elif compression == Compression.PACK_BITS:
        bytes_counts = array.array(('H', 'I')[version - 1])
        encoded = b''
        with io.BytesIO(data) as fp:
            row_size = width * bytes_per_pixel
            for index in range(height):
                row = packbits.encode(fp.read(row_size))
                bytes_counts.append(len(row))
                encoded += row

        with io.BytesIO() as fp:
            write_be_array(fp, bytes_counts)
            fp.write(encoded)
            result = fp.getvalue()
    elif compression == Compression.ZIP:
        result = zlib.compress(data)
    else:
        # TODO: Implement ZIP with prediction encoding.
        raise NotImplementedError(
            'ZIP with prediction encoding is not supported.'
        )

    return result
