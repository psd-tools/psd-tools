# -*- coding: utf-8 -*-
from __future__ import absolute_import
import pytest

from psd_tools.constants import ImageResourceID
from psd_tools.decoder.image_resources import (
    SlicesHeaderV6, SlicesResourceBlock)
from .utils import decode_psd, with_psb


SLICES_FILES = with_psb([
    ('slices.psd',),
])


@pytest.mark.parametrize(["filename"], SLICES_FILES)
def test_slices_resource(filename):
    decoded = decode_psd(filename)
    for block in decoded.image_resource_blocks:
        if block.resource_id == ImageResourceID.SLICES:
            assert isinstance(block.data, SlicesHeaderV6)
            for item in block.data.items:
                assert isinstance(item, SlicesResourceBlock)
