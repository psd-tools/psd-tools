from __future__ import absolute_import, unicode_literals
import pytest
from psd_tools.constants import Compression
from psd_tools.psd.header import FileHeader
from psd_tools.psd.image_data import ImageData

from ..utils import check_write_read

RAW_IMAGE_3x3_8bit = b'\x00\x01\x02\x01\x01\x01\x01\x00\x00'
RAW_IMAGE_2x2_16bit = b'\x00\x01\x00\x02\x00\x03\x00\x04'


def test_image_data():
    check_write_read(ImageData())
    check_write_read(ImageData(data=b'\x00'))


@pytest.mark.parametrize(
    'compression, data, header', [
        (
            Compression.RAW, [RAW_IMAGE_3x3_8bit] * 3,
            FileHeader(width=3, height=3, depth=8, channels=3, version=1)
        ),
        (
            Compression.RLE, [RAW_IMAGE_3x3_8bit] * 3,
            FileHeader(width=3, height=3, depth=8, channels=3, version=1)
        ),
        (
            Compression.ZIP, [RAW_IMAGE_3x3_8bit] * 3,
            FileHeader(width=3, height=3, depth=8, channels=3, version=1)
        ),
        (
            Compression.RAW, [RAW_IMAGE_3x3_8bit] * 3,
            FileHeader(width=3, height=3, depth=8, channels=3, version=2)
        ),
        (
            Compression.RLE, [RAW_IMAGE_3x3_8bit] * 3,
            FileHeader(width=3, height=3, depth=8, channels=3, version=2)
        ),
        (
            Compression.ZIP, [RAW_IMAGE_3x3_8bit] * 3,
            FileHeader(width=3, height=3, depth=8, channels=3, version=2)
        ),
        (
            Compression.RAW, [RAW_IMAGE_2x2_16bit] * 3,
            FileHeader(width=2, height=2, depth=16, channels=3, version=1)
        ),
        (
            Compression.RLE, [RAW_IMAGE_2x2_16bit] * 3,
            FileHeader(width=2, height=2, depth=16, channels=3, version=1)
        ),
        (
            Compression.ZIP, [RAW_IMAGE_2x2_16bit] * 3,
            FileHeader(width=2, height=2, depth=16, channels=3, version=1)
        ),
    ]
)
def test_image_data_data(compression, data, header):
    image_data = ImageData(compression)
    image_data.set_data(data, header)
    output = image_data.get_data(header)
    assert output == data, 'output=%r, expected=%r' % (output, data)
