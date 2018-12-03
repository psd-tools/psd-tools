# -*- coding: utf-8 -*-
from __future__ import absolute_import
from .utils import decode_psd


def test_metadata():
    decoded = decode_psd('metadata.psd')
    layers = decoded.layer_and_mask_data.layers.layer_records
    assert len(layers) == 1
    tagged_blocks = dict(layers[0].tagged_blocks)
    metadata = tagged_blocks[b'shmd']
    assert len(metadata) == 2

    # first block is not decoded yet
    assert metadata[0].key == b'mdyn'
    assert metadata[0].descriptor_version is None
    assert metadata[0].data == b'\x00\x00\x00\x01'

    # data from second block is decoded like a descriptor
    assert metadata[1].key == b'cust'
    assert metadata[1].descriptor_version == 16
    assert metadata[1].data.classID == b'metadata'
    assert len(metadata[1].data.items) == 1
    assert metadata[1].data.items[0][0] == b'layerTime'
    assert abs(metadata[1].data.items[0][1].value - 1408226375) < 1.0
