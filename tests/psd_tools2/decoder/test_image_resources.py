from __future__ import absolute_import, unicode_literals
import pytest
from psd_tools2.decoder.image_resources import ImageResources, ImageResource

from ..utils import check_read_write, check_write_read


def test_image_resources_from_to():
    check_read_write(ImageResources, b'\x00\x00\x00\x00')


def test_image_resources_exception():
    with pytest.raises(AssertionError):
        ImageResources.frombytes(b'\x00\x00\x00\x01')


def test_image_resource_from_to():
    check_write_read(ImageResource(name='foo', data=b'\x01\x04\x02'))


def test_image_resource_exception():
    with pytest.raises(AssertionError):
        ImageResource.frombytes(b'\x00\x00\x00\x01')
