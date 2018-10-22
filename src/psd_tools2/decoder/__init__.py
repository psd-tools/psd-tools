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
    def read(cls, fp, encoding='macroman', **kwargs):
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: PSD
        """
        header = FileHeader.read(fp)
        logger.debug('read %s' % header)
        return cls(
            header,
            ColorModeData.read(fp),
            ImageResources.read(fp, encoding),
            LayerAndMaskInformation.read(fp, encoding, header.version),
            ImageData.read(fp),
        )

    def write(self, fp, encoding='macroman', **kwargs):
        """Write the element to a file-like object.
        """
        logger.debug('writing %s' % self.header)
        written = self.header.write(fp)
        written += self.color_mode_data.write(fp)
        written += self.image_resources.write(fp, encoding)
        written += self.layer_and_mask_information.write(
            fp, encoding, self.header.version, **kwargs
        )
        written += self.image_data.write(fp)
        return written
