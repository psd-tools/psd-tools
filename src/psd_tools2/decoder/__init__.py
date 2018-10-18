from __future__ import absolute_import, unicode_literals
import attr
import logging
from .base import BaseElement
from .header import FileHeader
from .color_mode_data import ColorModeData
from .image_resources import ImageResources
from .layer_and_mask import LayerAndMaskInformation
from .image_data import ImageData

logger = logging.getLogger(__name__)


@attr.s
class PSD(BaseElement):
    """
    PSD file format.

    .. py:attribute:: header
    .. py:attribute:: color_mode_data
    .. py:attribute:: image_resources
    .. py:attribute:: layer_and_mask_information
    .. py:attribute:: image_data
    """
    header = attr.ib(factory=FileHeader)
    color_mode_data = attr.ib(factory=ColorModeData)
    image_resources = attr.ib(factory=ImageResources)
    layer_and_mask_information = attr.ib(factory=LayerAndMaskInformation)
    image_data = attr.ib(factory=ImageData)

    @classmethod
    def read(cls, fp, encoding='utf-8'):
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: PSD
        """
        header = FileHeader.read(fp)
        logger.debug(header)
        return cls(
            header,
            ColorModeData.read(fp),
            ImageResources.read(fp, encoding=encoding),
            LayerAndMaskInformation.read(
                fp, encoding=encoding, depth=header.depth,
                version=header.version
            ),
            ImageData.read(fp, header),
        )

    def write(self, fp, encoding='utf-8'):
        """Write the element to a file-like object.
        """
        written = self.header.write(fp)
        written += self.color_mode_data.write(fp)
        written += self.image_resources.write(fp, encoding=encoding)
        written += self.layer_and_mask_information.write(
            fp, depth=self.header.depth, encoding=encoding,
            version=self.header.version
        )
        # written += self.image_data.write(fp)
        return written
