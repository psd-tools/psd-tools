from __future__ import absolute_import, unicode_literals
import pytest
import logging

from psd_tools.api.psd_image import PSDImage
from psd_tools.api import adjustments

from ..utils import full_name

logger = logging.getLogger(__name__)

FILL_ADJUSTMENTS = PSDImage.open(full_name('fill_adjustments.psd'))


@pytest.fixture(scope="module")
def psd():
    return FILL_ADJUSTMENTS


def test_solid_color_fill():
    layer = PSDImage.open(full_name('layers/solid-color-fill.psd'))[0]
    assert layer.data


def test_gradient_fill():
    layer = PSDImage.open(full_name('layers/gradient-fill.psd'))[0]
    assert layer.angle
    assert layer.gradient_kind
    assert layer.data


def test_pattern_fill():
    layer = PSDImage.open(full_name('layers/pattern-fill.psd'))[0]
    assert layer.data


def test_brightness_contrast(psd):
    layer = psd[4]
    assert isinstance(layer, adjustments.BrightnessContrast)
    assert layer.brightness == 34
    assert layer.contrast == 18
    assert layer.mean == 127
    assert layer.use_legacy is False
    assert layer.automatic is False


def test_levels(psd):
    layer = psd[5]
    assert isinstance(layer, adjustments.Levels)
    assert layer.master


def test_curves(psd):
    layer = psd[6]
    assert isinstance(layer, adjustments.Curves)
    assert layer.data
    assert layer.extra


def test_exposure(psd):
    layer = psd[7]
    assert isinstance(layer, adjustments.Exposure)
    assert pytest.approx(layer.exposure) == -0.39
    assert pytest.approx(layer.offset) == 0.0168
    assert pytest.approx(layer.gamma) == 0.91


def test_vibrance(psd):
    layer = psd[8]
    assert isinstance(layer, adjustments.Vibrance)
    assert layer.vibrance == -6
    assert layer.saturation == 2


def test_hue_saturation(psd):
    layer = psd[9]
    assert isinstance(layer, adjustments.HueSaturation)
    assert layer.enable_colorization == 0
    assert layer.colorization == (0, 25, 0)
    assert layer.master == (-17, 19, 4)
    assert len(layer.data) == 6


def test_color_balance(psd):
    layer = psd[10]
    assert isinstance(layer, adjustments.ColorBalance)
    assert layer.shadows == (-4, 2, -5)
    assert layer.midtones == (10, 4, -9)
    assert layer.highlights == (1, -9, -3)
    assert layer.luminosity == 1


def test_black_and_white(psd):
    layer = psd[11]
    assert isinstance(layer, adjustments.BlackAndWhite)
    assert layer.red == 40
    assert layer.yellow == 60
    assert layer.green == 40
    assert layer.cyan == 60
    assert layer.blue == 20
    assert layer.magenta == 80
    assert layer.use_tint is False
    assert layer.tint_color
    assert layer.preset_kind == 1
    assert layer.preset_file_name == ''


def test_photo_filter(psd):
    layer = psd[12]
    assert isinstance(layer, adjustments.PhotoFilter)
    assert layer.xyz is None
    assert layer.color_space == 7
    assert layer.color_components == (6706, 3200, 12000, 0)
    assert layer.density == 25
    assert layer.luminosity == 1


def test_channel_mixer(psd):
    layer = psd[13]
    assert isinstance(layer, adjustments.ChannelMixer)
    assert layer.monochrome == 0
    assert layer.data == [100, 0, 0, 0, 0]


def test_color_lookup(psd):
    layer = psd[14]
    assert isinstance(layer, adjustments.ColorLookup)


def test_invert(psd):
    layer = psd[15]
    assert isinstance(layer, adjustments.Invert)


def test_posterize(psd):
    layer = psd[16]
    assert isinstance(layer, adjustments.Posterize)
    assert layer.posterize == 4


def test_threshold(psd):
    layer = psd[17]
    assert isinstance(layer, adjustments.Threshold)
    assert layer.threshold == 128


def test_selective_color(psd):
    layer = psd[18]
    assert isinstance(layer, adjustments.SelectiveColor)
    assert layer.method == 0
    assert len(layer.data) == 10


def test_gradient_map(psd):
    layer = psd[19]
    assert isinstance(layer, adjustments.GradientMap)
    assert layer.reversed == 0
    assert layer.dithered == 0
    assert layer.gradient_name == u'Foreground to Background'
    assert len(layer.color_stops) == 2
    assert len(layer.transparency_stops) == 2
    assert layer.expansion == 2
    assert layer.interpolation == 1.0
    assert layer.length == 32
    assert layer.mode == 0
    assert layer.random_seed == 470415386
    assert layer.show_transparency == 0
    assert layer.use_vector_color == 1
    assert layer.roughness == 2048
    assert layer.color_model == 3
    assert layer.min_color == [0, 0, 0, 0]
    assert layer.max_color == [32768, 32768, 32768, 32768]
