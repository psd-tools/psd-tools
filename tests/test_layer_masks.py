# -*- coding: utf-8 -*-
from __future__ import absolute_import
import pytest
from .utils import decode_psd


@pytest.mark.parametrize('filename', ['masks.psd', 'masks2.psd'])
def test_file_with_masks_is_parsed(filename):
    psd = decode_psd(filename)
    for channels in psd.layer_and_mask_data.layers.channel_image_data:
        assert len(channels) >= 3
