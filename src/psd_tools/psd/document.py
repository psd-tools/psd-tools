"""
PSD document structure module.

This module contains the main PSD class that represents the low-level
binary structure of a PSD/PSB file.
"""

import logging
from typing import Any, BinaryIO, Generator, Optional, TypeVar

from attrs import define, field

from .base import BaseElement
from .color_mode_data import ColorModeData
from .header import FileHeader
from .image_data import ImageData
from .image_resources import ImageResources
from .layer_and_mask import (
    LayerAndMaskInformation,
    LayerInfo,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="PSD")


@define(repr=False)
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

    header: FileHeader = field(factory=FileHeader)
    color_mode_data: ColorModeData = field(factory=ColorModeData)
    image_resources: ImageResources = field(factory=ImageResources)
    layer_and_mask_information: LayerAndMaskInformation = field(
        factory=LayerAndMaskInformation
    )
    image_data: ImageData = field(factory=ImageData)

    @classmethod
    def read(
        cls: type[T], fp: BinaryIO, encoding: str = "macroman", **kwargs: Any
    ) -> T:
        header = FileHeader.read(fp)
        logger.debug("read %s" % header)
        return cls(
            header,
            ColorModeData.read(fp),
            ImageResources.read(fp, encoding),
            LayerAndMaskInformation.read(fp, encoding, header.version),
            ImageData.read(fp),
        )

    def write(self, fp: BinaryIO, encoding: str = "macroman", **kwargs: Any) -> int:
        logger.debug("writing %s" % self.header)
        written = self.header.write(fp)
        written += self.color_mode_data.write(fp)
        written += self.image_resources.write(fp, encoding)
        written += self.layer_and_mask_information.write(
            fp, encoding, self.header.version, **kwargs
        )
        written += self.image_data.write(fp)
        return written

    def _iter_layers(self) -> Generator[tuple[Any, Any], None, None]:
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

    def _get_layer_info(self) -> Optional[LayerInfo]:
        from psd_tools.constants import Tag

        tagged_blocks = self.layer_and_mask_information.tagged_blocks
        if tagged_blocks is not None:
            for key in (Tag.LAYER_16, Tag.LAYER_32):
                if key in tagged_blocks:
                    return tagged_blocks.get_data(key)
        return self.layer_and_mask_information.layer_info
