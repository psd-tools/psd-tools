"""
Low-level API that translates binary data to Python structure.

All the data structure in this subpackage inherits from one of the object
defined in :py:mod:`psd_tools.psd.base` module.
"""
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


@attr.s(slots=True)
class PSD(BaseElement):
    """
    Low-level PSD file structure that resembles the specification_.

    .. _specification: https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/

    Example::

        from psd_tools.psd import PSD

        with open(input_file, 'rb') as f:
            psd = PSD.read(f)

        with open(output_file, 'wb') as f:
            psd.write(f)


    .. py:attribute:: header

        See :py:class:`.FileHeader`.

    .. py:attribute:: color_mode_data

        See :py:class:`.ColorModeData`.

    .. py:attribute:: image_resources

        See :py:class:`.ImageResources`.

    .. py:attribute:: layer_and_mask_information

        See :py:class:`.LayerAndMaskInformation`.

    .. py:attribute:: image_data

        See :py:class:`.ImageData`.
    """
    header = attr.ib(factory=FileHeader)
    color_mode_data = attr.ib(factory=ColorModeData)
    image_resources = attr.ib(factory=ImageResources)
    layer_and_mask_information = attr.ib(factory=LayerAndMaskInformation)
    image_data = attr.ib(factory=ImageData)

    @classmethod
    def read(cls, fp, encoding='macroman', **kwargs):
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
        logger.debug('writing %s' % self.header)
        written = self.header.write(fp)
        written += self.color_mode_data.write(fp)
        written += self.image_resources.write(fp, encoding)
        written += self.layer_and_mask_information.write(
            fp, encoding, self.header.version, **kwargs
        )
        written += self.image_data.write(fp)
        return written

    def _iter_layers(self):
        """
        Iterate over (layer_record, channel_data) pairs.
        """
        layer_info = self._get_layer_info()
        if layer_info is not None:
            records = layer_info.layer_records
            channel_data = layer_info.channel_image_data
            if records is not None and channel_data is not None:
                for record, channels in zip(records, channel_data):
                    yield record, channels

    def _get_layer_info(self):
        tagged_blocks = self.layer_and_mask_information.tagged_blocks
        if tagged_blocks is not None:
            for key in ('LAYER_16', 'LAYER_32'):
                if key in tagged_blocks:
                    return tagged_blocks.get_data(key)
        return self.layer_and_mask_information.layer_info
