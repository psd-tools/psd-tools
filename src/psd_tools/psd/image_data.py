"""
Image data section structure.

:py:class:`ImageData` corresponds to the last section of the PSD/PSB file
where a composited image is stored. When the file does not contain layers,
this is the only place pixels are saved.
"""

import io
import logging
from typing import IO, Any, Sequence, TypeVar

from attrs import define, field

from psd_tools.compression import compress, decompress, decompressed_size_bound
from psd_tools.constants import Compression
from psd_tools.psd.header import FileHeader
from psd_tools.psd.base import BaseElement
from psd_tools.psd.bin_utils import pack, read_fmt, write_bytes, write_fmt
from psd_tools.validators import in_

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="ImageData")


@define(repr=False)
class ImageData(BaseElement):
    """
    Merged channel image data.

    .. py:attribute:: compression

        See :py:class:`~psd_tools.constants.Compression`.

    .. py:attribute:: data

        `bytes` as compressed in the `compression` flag.
    """

    compression: Compression = field(
        default=Compression.RAW, converter=Compression, validator=in_(Compression)
    )
    data: bytes = b""

    @classmethod
    def read(cls: type[T], fp: IO[bytes], **kwargs: Any) -> T:
        start_pos = fp.tell()
        compression = Compression(read_fmt("H", fp)[0])
        data = fp.read()  # TODO: Parse data here. Need header.
        logger.debug("  read image data, len=%d" % (fp.tell() - start_pos))
        return cls(compression, data)

    def write(self, fp: IO[bytes], **kwargs: Any) -> int:
        start_pos = fp.tell()
        written = write_fmt(fp, "H", self.compression.value)
        written += write_bytes(fp, self.data)
        logger.debug("  wrote image data, len=%d" % (fp.tell() - start_pos))
        return written

    def get_data(self, header: FileHeader, split: bool = True) -> list[bytes] | bytes:
        """
        Get decompressed data.

        :param header: See :py:class:`~psd_tools.psd.header.FileHeader`.
        :return: `list` of bytes corresponding each channel.
        """
        data = decompress(
            self.data,
            self.compression,
            header.width,
            header.height * header.channels,
            header.depth,
            header.version,
        )
        if split:
            plane_size = len(data) // header.channels
            with io.BytesIO(data) as f:
                return [f.read(plane_size) for _ in range(header.channels)]
        return data

    def decompressed_size_bound(self, header: FileHeader) -> int:
        """
        Upper bound on the number of bytes :py:meth:`get_data` will decompress.

        Answerable without decompressing anything, so an allocation guard can
        size the array before it exists -- see
        :py:func:`psd_tools.compression.decompressed_size_bound`. It lives next
        to :py:meth:`get_data` because it has to mirror that call exactly,
        including the part a caller would most easily get wrong: every channel
        is decompressed in one pass, ``height * channels`` rows at a time.

        :param header: See :py:class:`~psd_tools.psd.header.FileHeader`.
        :return: the maximum byte count, for all channels together.
        """
        return decompressed_size_bound(
            self.data,
            self.compression,
            header.width,
            header.height * header.channels,
            header.depth,
            header.version,
        )

    def set_data(self, data: Sequence[bytes], header: FileHeader) -> int:
        """
        Set raw data and compress.

        :param data: list of raw data bytes corresponding channels.
        :param compression: compression type,
            see :py:class:`~psd_tools.constants.Compression`.
        :param header: See :py:class:`~psd_tools.psd.header.FileHeader`.
        :return: length of compressed data.
        """
        self.data = compress(
            b"".join(data),
            self.compression,
            header.width,
            header.height * header.channels,
            header.depth,
            header.version,
        )
        return len(self.data)

    @classmethod
    def new(
        cls: type[T],
        header: FileHeader,
        color: int | Sequence[int] = 0,
        compression: Compression = Compression.RAW,
    ) -> T:
        """
        Create a new image data object.

        :param header: FileHeader.
        :param compression: compression type.
        :param color: default color. int or iterable for channel length.
        """
        plane_size = header.width * header.height
        if isinstance(color, (bool, int, float)):
            color = (color,) * header.channels
        if len(color) != header.channels:
            raise ValueError(
                "Invalid color %s for channel size %d" % (color, header.channels)
            )
        # Bitmap is not supported here.
        fmt = {8: "B", 16: "H", 32: "I"}[header.depth]
        data = []
        for i in range(header.channels):
            data.append(pack(fmt, color[i]) * plane_size)
        self = cls(compression=compression)
        self.set_data(data, header)
        return self
