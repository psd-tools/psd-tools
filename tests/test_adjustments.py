# -*- coding: utf-8 -*-
from __future__ import absolute_import

import os

from psd_tools.user_api.psd_image import PSDImage
from psd_tools.constants import TaggedBlock
from psd_tools.decoder.tagged_blocks import (
    BrightnessContrast, LevelsSettings, CurvesSettings, Exposure, Vibrance,
    HueSaturation, ColorBalance, BlackWhite, PhotoFilter, ChannelMixer,
    ColorLookup, SelectiveColor, GradientSettings)
from PIL.Image import Image
from tests.utils import decode_psd, DATA_PATH


def test_adjustment_layers():
    psd = PSDImage(decode_psd('fill_adjustments.psd'))
    assert isinstance(psd.layers[15].get_tag(
        TaggedBlock.BRIGHTNESS_AND_CONTRAST), BrightnessContrast)
    assert isinstance(psd.layers[14].get_tag(
        TaggedBlock.LEVELS), LevelsSettings)
    assert isinstance(psd.layers[13].get_tag(
        TaggedBlock.CURVES), CurvesSettings)
    assert isinstance(psd.layers[12].get_tag(TaggedBlock.EXPOSURE), Exposure)
    assert isinstance(psd.layers[11].get_tag(TaggedBlock.VIBRANCE), Vibrance)
    assert isinstance(psd.layers[10].get_tag(
        TaggedBlock.HUE_SATURATION_5), HueSaturation)
    assert isinstance(psd.layers[9].get_tag(
        TaggedBlock.COLOR_BALANCE), ColorBalance)
    assert isinstance(psd.layers[8].get_tag(
        TaggedBlock.BLACK_AND_WHITE), BlackWhite)
    assert isinstance(psd.layers[7].get_tag(
        TaggedBlock.PHOTO_FILTER), PhotoFilter)
    assert isinstance(psd.layers[6].get_tag(
        TaggedBlock.CHANNEL_MIXER), ChannelMixer)
    assert isinstance(psd.layers[5].get_tag(
        TaggedBlock.COLOR_LOOKUP), ColorLookup)
    assert psd.layers[4].has_tag(TaggedBlock.INVERT)
    assert isinstance(psd.layers[3].get_tag(TaggedBlock.POSTERIZE), int)
    assert isinstance(psd.layers[2].get_tag(TaggedBlock.THRESHOLD), int)
    assert isinstance(psd.layers[1].get_tag(
        TaggedBlock.SELECTIVE_COLOR), SelectiveColor)
    assert isinstance(psd.layers[0].get_tag(
        TaggedBlock.GRADIENT_MAP_SETTING), GradientSettings)


def test_adjustment_types():
    psd = PSDImage(decode_psd('fill_adjustments.psd'))
    assert psd.layers[15].adjustment_type == 'brightness and contrast'
    assert psd.layers[14].adjustment_type == 'levels'
    assert psd.layers[13].adjustment_type == 'curves'
    assert psd.layers[12].adjustment_type == 'exposure'
    assert psd.layers[11].adjustment_type == 'vibrance'
    assert psd.layers[10].adjustment_type == 'hue saturation 5'
    assert psd.layers[9].adjustment_type == 'color balance'
    assert psd.layers[8].adjustment_type == 'black and white'
    assert psd.layers[7].adjustment_type == 'photo filter'
    assert psd.layers[6].adjustment_type == 'channel mixer'
    assert psd.layers[5].adjustment_type == 'color lookup'
    assert psd.layers[4].adjustment_type == 'invert'
    assert psd.layers[3].adjustment_type == 'posterize'
    assert psd.layers[2].adjustment_type == 'threshold'
    assert psd.layers[1].adjustment_type == 'selective color'
    assert psd.layers[0].adjustment_type == 'gradient map'


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
            if layer.has_stroke():
                assert layer.stroke
            if layer.has_stroke_content():
                assert layer.stroke_content
