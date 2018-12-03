# -*- coding: utf-8 -*-
from __future__ import absolute_import
import pytest

from psd_tools.constants import ImageResourceID
from psd_tools.decoder.image_resources import (
    SlicesHeaderV6, SlicesResourceBlock)
from psd_tools.user_api.psd_image import PSDImage
from .utils import decode_psd, with_psb, full_name


SLICES_FILES = with_psb([
    ('slices.psd',),
])


THUMBNAIL_FILES = with_psb([
    ('layer_comps.psd',),
])


@pytest.mark.parametrize(["filename"], SLICES_FILES)
def test_slices_resource(filename):
    decoded = decode_psd(filename)
    for block in decoded.image_resource_blocks:
        if block.resource_id == ImageResourceID.SLICES:
            assert isinstance(block.data, SlicesHeaderV6)
            for item in block.data.items:
                assert isinstance(item, SlicesResourceBlock)


def test_resource_blocks():
    psd = PSDImage.load(full_name("fill_adjustments.psd"))
    blocks = psd.image_resource_blocks
    assert "version_info" in blocks


@pytest.mark.parametrize(["filename"], THUMBNAIL_FILES)
def test_thumbnail(filename):
    psd = PSDImage.load(full_name(filename))
    assert psd.thumbnail()
