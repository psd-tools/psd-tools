# -*- coding: utf-8 -*-
from __future__ import absolute_import

import pytest
from psd_tools.constants import TaggedBlock
from psd_tools.user_api.psd_image import PSDImage
from psd_tools.user_api import adjustments
from PIL.Image import Image
from .utils import decode_psd, DATA_PATH


@pytest.fixture(scope="module")
def psd():
    return PSDImage(decode_psd('fill_adjustments.psd'))


def test_adjustment_types(psd):
    assert psd.layers[15].adjustment_type == 'brightness-and-contrast'
    assert psd.layers[14].adjustment_type == 'levels'
    assert psd.layers[13].adjustment_type == 'curves'
    assert psd.layers[12].adjustment_type == 'exposure'
    assert psd.layers[11].adjustment_type == 'vibrance'
    assert psd.layers[10].adjustment_type == 'hue-saturation'
    assert psd.layers[9].adjustment_type == 'color-balance'
    assert psd.layers[8].adjustment_type == 'black-and-white'
    assert psd.layers[7].adjustment_type == 'photo-filter'
    assert psd.layers[6].adjustment_type == 'channel-mixer'
    assert psd.layers[5].adjustment_type == 'color-lookup'
    assert psd.layers[4].adjustment_type == 'invert'
    assert psd.layers[3].adjustment_type == 'posterize'
    assert psd.layers[2].adjustment_type == 'threshold'
    assert psd.layers[1].adjustment_type == 'selective-color'
    assert psd.layers[0].adjustment_type == 'gradient-map'


def test_brightness_contrast(psd):
    data = psd.layers[15].data
    assert isinstance(data, adjustments.BrightnessContrast)
    assert data.brightness == 34
    assert data.contrast == 18
    assert data.mean == 127
    assert data.use_legacy is False
    assert data.automatic is False


def test_levels(psd):
    data = psd.layers[14].data
    assert isinstance(data, adjustments.Levels)
    assert data.master


def test_curves(psd):
    data = psd.layers[13].data
    assert isinstance(data, adjustments.Curves)
    assert data.data
    assert data.count == len(data.data)
    assert data.extra


def test_exposure(psd):
    data = psd.layers[12].data
    assert isinstance(data, adjustments.Exposure)
    assert pytest.approx(data.exposure) == -0.39
    assert pytest.approx(data.offset) == 0.0168
    assert pytest.approx(data.gamma) == 0.91


def test_vibrance(psd):
    data = psd.layers[11].data
    assert isinstance(data, adjustments.Vibrance)
    assert data.vibrance == -6
    assert data.saturation == 2


def test_hue_saturation(psd):
    data = psd.layers[10].data
    assert isinstance(data, adjustments.HueSaturation)
    assert data.enable_colorization == 0
    assert data.colorization == (0, 25, 0)
    assert data.master == (-17, 19, 4)
    assert len(data.data) == 6


def test_hue_saturation(psd):
    data = psd.layers[9].data
    assert isinstance(data, adjustments.ColorBalance)
    assert data.shadows == (-4, 2, -5)
    assert data.midtones == (10, 4, -9)
    assert data.highlights == (1, -9, -3)
    assert data.preserve_luminosity == 1


def test_black_and_white(psd):
    data = psd.layers[8].data
    assert isinstance(data, adjustments.BlackWhite)
    assert data.red == 40
    assert data.yellow == 60
    assert data.green == 40
    assert data.cyan == 60
    assert data.blue == 20
    assert data.magenta == 80
    assert data.use_tint is False
    assert data.tint_color
    assert data.preset_kind == 1
    assert data.preset_file_name == ''


def test_photo_filter(psd):
    data = psd.layers[7].data
    assert isinstance(data, adjustments.PhotoFilter)
    assert data.xyz is None
    assert data.color_space == 7
    assert data.color_components == (6706, 3200, 12000, 0)
    assert data.density == 25
    assert data.preserve_luminosity == 1


def test_channel_mixer(psd):
    data = psd.layers[6].data
    assert isinstance(data, adjustments.ChannelMixer)
    assert data.monochrome == 0
    assert data.mixer_settings == (100, 0, 0, 0, 0)


def test_color_lookup(psd):
    data = psd.layers[5].data
    assert isinstance(data, adjustments.ColorLookup)


def test_invert(psd):
    data = psd.layers[4].data
    assert isinstance(data, adjustments.Invert)


def test_posterize(psd):
    data = psd.layers[3].data
    assert isinstance(data, adjustments.Posterize)
    assert data.posterize == 4


def test_threshold(psd):
    data = psd.layers[2].data
    assert isinstance(data, adjustments.Threshold)
    assert data.threshold == 128


def test_selective_color(psd):
    data = psd.layers[1].data
    assert isinstance(data, adjustments.SelectiveColor)
    assert data.method == 0
    assert len(data.data) == 10


def test_gradient_map(psd):
    data = psd.layers[0].data
    assert isinstance(data, adjustments.GradientMap)
    assert data.reversed == 0
    assert data.dithered == 0
    assert data.gradient_name == u'Foreground to Background'
    assert len(data.color_stops) == 2
    assert len(data.transparency_stops) == 2
    assert data.expansion == 2
    assert data.interpolation == 1.0
    assert data.length == 32
    assert data.mode == 0
    assert data.random_seed == 470415386
    assert data.show_transparency == 0
    assert data.use_vector_color == 1
    assert data.roughness == 2048
    assert data.color_model == 3
    assert data.min_color == (0, 0, 0, 0)
    assert data.max_color == (32768, 32768, 32768, 32768)


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


def test_adjustment_and_shapes():
    psd = PSDImage(decode_psd('adjustment-mask.psd'))
    for layer in psd.descendants():
        layer.as_PIL()
        if layer.has_mask():
            layer.mask.as_PIL()
