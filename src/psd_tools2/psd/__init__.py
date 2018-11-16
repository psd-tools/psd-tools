from __future__ import absolute_import, unicode_literals
import attr
import logging
from .base import BaseElement
from .header import FileHeader
from .color_mode_data import ColorModeData
from .image_resources import ImageResources
from .layer_and_mask import LayerAndMaskInformation
from .image_data import ImageData

from psd_tools2.constants import ColorMode

logger = logging.getLogger(__name__)


@attr.s(slots=True)
class PSD(BaseElement):
    """
    Low-level PSD file structure.

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

    @classmethod
    def new(cls, mode, size, color=0, depth=8, **kwargs):
        assert depth in (8, 16, 32), 'Invalid depth: %d' % (depth)
        color_mode, alpha = cls._get_color_mode(mode)
        channels = {
            ColorMode.BITMAP: 1,
            ColorMode.GRAYSCALE: 1,
            ColorMode.INDEXED: 1,
            ColorMode.RGB: 3,
            ColorMode.CMYK: 4,
            ColorMode.MULTICHANNEL: 3,
            ColorMode.DUOTONE: 1,
            ColorMode.LAB: 3,
        }.get(color_mode) + alpha

        header = FileHeader(
            width=size[0], height=size[1], depth=depth, channels=channels,
            color_mode=color_mode
        )
        image_data = ImageData.new(header, color=color, **kwargs)
        return cls(header=header, image_data=image_data)

    def _iter_layers(self):
        """
        Iterate over (layer_record, channel_data) pairs.
        """
        layer_info = self.layer_and_mask_information.layer_info
        tagged_blocks = self.layer_and_mask_information.tagged_blocks
        if tagged_blocks is not None:
            for key in ('LAYER_16', 'LAYER_32'):
                layer_info = tagged_blocks.get(key, layer_info)
        if layer_info is not None:
            records = layer_info.layer_records
            channel_data = layer_info.channel_image_data
            if records is not None and channel_data is not None:
                for record, channels in zip(records, channel_data):
                    yield record, channels

    @classmethod
    def _get_color_mode(cls, mode):
        """
        Parse color name from PIL-like mode.
        """
        color_mode = mode.upper()
        alpha = False
        if color_mode.endswith('A'):
            color_mode = color_mode.rstrip('A')
            alpha = True
        color_mode = {'L': 'GRAYSCALE'}.get(color_mode, color_mode)
        if not hasattr(ColorMode, color_mode):
            raise ValueError('Invalid mode: %s' % (mode))
        return getattr(ColorMode, color_mode), alpha

    def to_PIL(self):
        """
        Get PIL Image.
        """
        from PIL import Image
        version_info = self.image_resources.get_data('version_info')
        if version_info and not version_info.has_composite:
            return None
        size = (self.header.width, self.header.height)
        channels = []
        for raw_data in self.image_data.get_data(self.header):
            channels.append(Image.frombytes('L', size, raw_data, 'raw'))
        return Image.merge('RGB', channels)
