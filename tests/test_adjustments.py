# -*- coding: utf-8 -*-
from __future__ import absolute_import

import os

from psd_tools import PSDImage, BBox
from psd_tools.constants import TaggedBlock
from psd_tools.decoder.tagged_blocks import (
    BrightnessContrast, LevelsSettings, CurvesSettings, Exposure)
from .utils import decode_psd, DATA_PATH


def test_adjustment_layers():
    decoded = decode_psd('fill_adjustments.psd')
    layers = decoded.layer_and_mask_data.layers.layer_records
    assert isinstance(dict(layers[7].tagged_blocks)[b'expA'], Exposure)
    assert isinstance(dict(layers[6].tagged_blocks)[b'curv'], CurvesSettings)
    assert isinstance(dict(layers[5].tagged_blocks)[b'levl'], LevelsSettings)
    assert isinstance(dict(layers[4].tagged_blocks)[b'brit'],
                      BrightnessContrast)
