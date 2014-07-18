# -*- coding: utf-8 -*-
from __future__ import absolute_import
from .utils import decode_psd


def test_file_with_masks_is_parsed():
    psd = decode_psd('masks.psd')
    for channels in psd.layer_and_mask_data.layers.channel_image_data:
        assert len(channels) >= 3
