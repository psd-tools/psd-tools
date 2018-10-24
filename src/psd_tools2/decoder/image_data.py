"""
Image data section structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import logging
from psd_tools2.constants import Compression
from psd_tools2.decoder.base import BaseElement
from psd_tools2.validators import in_
from psd_tools2.utils import read_fmt, write_fmt, write_bytes

logger = logging.getLogger(__name__)


@attr.s
class ImageData(BaseElement):
    """
    Merged channel image data.

    .. py:attribute:: compression

        :py:class:`~psd_tools2.constants.Compression`

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


# @classmethod
# def read(cls, fp, header):
#     """
#     Reads merged image pixel data which is stored at the end of PSD file.
#     """
#     w, h = header.width, header.height
#     compress_type = Compression(read_fmt('H', fp)[0])

#     bytes_per_pixel = header.depth // 8

#     channel_byte_counts = []
#     if compress_type == Compression.PACK_BITS:
#         for ch in range(header.channels):
#             channel_byte_counts.append(
#                 read_be_array(('H', 'I')[header.version - 1], h, fp)
#             )

#     items = []
#     for channel_id in range(header.channels):
#         data = None
#         if compress_type == Compression.RAW:
#             data_size = w * h * bytes_per_pixel
#             data = fp.read(data_size)

#         elif compress_type == Compression.PACK_BITS:
#             byte_counts = channel_byte_counts[channel_id]
#             data_size = sum(byte_counts)
#             data = fp.read(data_size)

#         # are there any ZIP-encoded composite images in a wild?
#         elif compress_type == Compression.ZIP:
#             warnings.warn(
#                 "ZIP compression of composite image is not supported."
#             )

#         elif compress_type == Compression.ZIP_WITH_PREDICTION:
#             warnings.warn(
#                 "ZIP_WITH_PREDICTION compression of composite image is "
#                 "not supported."
#             )

#         if data is None:
#             continue

#         items.append(ChannelData(compress_type, data))

#     return cls(items)

# def write(self, fp, header):
#     if len(self) == 0:
#         raise ValueError('Image data must be populated.')

#     compress_type = self[0].compression
#     written = write_fmt(fp, 'H', compression_type.value)

#     bytes_per_pixel = header.depth // 8
#     if compress_type == Compression.PACK_BITS:
#         # TODO: Calculate channel byte counts from packbits.
#         raise NotImplementedError

#     for channel in self:
#         if compress_type in (Compression.RAW, Compression.PACK_BITS):
#             written += fp.write(channel.data)
#             written += fp.write(channel.data)
#         elif compress_type in (Compression.ZIP,
#                                Compression.ZIP_WITH_PREDICTION):
#             warnings.warn(
#                 "ZIP compression of composite image is not supported."
#             )

#     return written
