from __future__ import absolute_import, unicode_literals
import pytest
from psd_tools2.decoder.image_data import ImageData

from ..utils import check_write_read


def test_image_data():
    check_write_read(ImageData())
    check_write_read(ImageData(data=b'\x00'))
