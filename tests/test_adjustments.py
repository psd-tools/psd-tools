# -*- coding: utf-8 -*-
from __future__ import absolute_import

import os

from psd_tools.user_api.psd_image import PSDImage
from psd_tools.constants import TaggedBlock
from psd_tools.decoder.tagged_blocks import (
    BrightnessContrast, LevelsSettings, CurvesSettings, Exposure)
from PIL.Image import Image
from .utils import decode_psd, DATA_PATH


def test_adjustment_layers():
    decoded = decode_psd('fill_adjustments.psd')
    layers = decoded.layer_and_mask_data.layers.layer_records
    assert isinstance(dict(layers[7].tagged_blocks)[b'expA'], Exposure)
    assert isinstance(dict(layers[6].tagged_blocks)[b'curv'], CurvesSettings)
    assert isinstance(dict(layers[5].tagged_blocks)[b'levl'], LevelsSettings)
    assert isinstance(dict(layers[4].tagged_blocks)[b'brit'],
                      BrightnessContrast)


def test_adjustment_and_shapes():
    psd = PSDImage(decode_psd('adjustment-fillers.psd'))
    for layer in psd.layers:
        if layer.bbox.width:
            assert isinstance(layer.as_PIL(), Image)
        if layer.kind == "adjustment":
            assert layer.adjustment_type
            assert layer.data
        if layer.kind == "shape":
            assert isinstance(layer.get_anchors(), list)
            if layer.has_origination():
                assert layer.origination
            if layer.has_vector_mask():
                vector_mask = layer.vector_mask
                assert vector_mask
                if layer.has_path():
                    assert len(vector_mask.anchors) > 0
                assert len(vector_mask.anchors) == vector_mask.num_knots
                vector_mask.closed
            if layer.has_stroke():
                assert layer.stroke
            if layer.has_stroke_content():
                assert layer.stroke_content
