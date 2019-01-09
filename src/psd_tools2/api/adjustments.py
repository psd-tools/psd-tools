"""
Adjustment module.

Example::

    if layer.kind == 'brightnesscontrast':
        print(layer.brightness)
"""
from __future__ import absolute_import
import logging


from psd_tools2.api.layers import AdjustmentLayer, FillLayer
from psd_tools2.constants import TaggedBlockID


logger = logging.getLogger(__name__)


class SolidColorFill(FillLayer):
    """Solid color fill."""
    _KEY = TaggedBlockID.SOLID_COLOR_SHEET_SETTING


class PatternFill(FillLayer):
    """Solid color fill."""
    _KEY = TaggedBlockID.PATTERN_FILL_SETTING


class GradientFill(FillLayer):
    """Solid color fill."""
    _KEY = TaggedBlockID.GRADIENT_FILL_SETTING



class BrightnessContrast(AdjustmentLayer):
    """Brightness and contrast adjustment."""
    # TaggedBlockID.BRIGHTNESS_AND_CONTRAST is obsolete.
    _KEY = TaggedBlockID.CONTENT_GENERATOR_EXTRA_DATA

    @property
    def brightness(self):
        return self._data.get(b'Brgh', 0)

    @property
    def contrast(self):
        return self._data.get(b'Cntr', 0)

    @property
    def mean(self):
        return self._data.get(b'means', 0)

    @property
    def lab(self):
        return bool(self._data.get(b'Lab ', False))

    @property
    def use_legacy(self):
        return bool(self._data.get(b'useLegacy', False))

    @property
    def vrsn(self):
        return self._data.get(b'Vrsn', 1)

    @property
    def automatic(self):
        return bool(self._data.get(b'auto', False))


class Curves(AdjustmentLayer):
    """
    Curves adjustment.
    """
    _KEY = TaggedBlockID.CURVES

    @property
    def data(self):
        """
        List of :py:class:`~psd_tools.decoder.tagged_blocks.CurveData`

        :rtype: list
        """
        return self._data.data

    @property
    def extra(self):
        return self._data.extra


class Exposure(AdjustmentLayer):
    """
    Exposure adjustment.
    """
    _KEY = TaggedBlockID.EXPOSURE

    @property
    def exposure(self):
        """Exposure.

        :rtype: float
        """
        return self._data.exposure

    @property
    def offset(self):
        """Offset.

        :rtype: float
        """
        return self._data.offset

    @property
    def gamma(self):
        """Gamma.

        :rtype: float
        """
        return self._data.gamma


class Levels(AdjustmentLayer):
    """
    Levels adjustment.

    Levels contain a list of
    :py:class:`~psd_tools.decoder.tagged_blocks.LevelRecord`.
    """
    _KEY = TaggedBlockID.LEVELS

    @property
    def data(self):
        """
        List of level records. The first record is the master.

        :rtype: list
        """
        return self._data

    @property
    def master(self):
        """Master record.

        :rtype: psd_tools.decoder.tagged_blocks.LevelRecord
        """
        return self.data[0]


class Vibrance(AdjustmentLayer):
    """Vibrance adjustment."""
    _KEY = TaggedBlockID.VIBRANCE

    @property
    def vibrance(self):
        """Vibrance.

        :rtype: int
        """
        return self._data.get(b'vibrance', 0)

    @property
    def saturation(self):
        """Saturation.

        :rtype: int
        """
        return self._data.get(b'Strt', 0)


class HueSaturation(AdjustmentLayer):
    """
    Hue/Saturation adjustment.

    HueSaturation contains a list of data.
    """
    _KEY = TaggedBlockID.HUE_SATURATION

    @property
    def data(self):
        """
        List of Hue/Saturation records.

        :rtype: list
        """
        return self._data.items

    @property
    def enable_colorization(self):
        """Enable colorization.

        :rtype: int
        """
        return self._data.enable

    @property
    def colorization(self):
        """Colorization.

        :rtype: tuple
        """
        return self._data.colorization

    @property
    def master(self):
        """Master record.

        :rtype: tuple
        """
        return self._data.master


class ColorBalance(AdjustmentLayer):
    """Color balance adjustment."""
    _KEY = TaggedBlockID.COLOR_BALANCE

    @property
    def shadows(self):
        """Shadows.

        :rtype: tuple
        """
        return self._data.shadows

    @property
    def midtones(self):
        """Mid-tones.

        :rtype: tuple
        """
        return self._data.midtones

    @property
    def highlights(self):
        """Highlights.

        :rtype: tuple
        """
        return self._data.highlights

    @property
    def luminosity(self):
        return self._data.luminosity


class BlackWhite(AdjustmentLayer):
    """Black and white adjustment."""
    _KEY = TaggedBlockID.BLACK_AND_WHITE

    @property
    def red(self):
        return self._data.get(b'Rd  ', 0)

    @property
    def yellow(self):
        return self._data.get(b'Yllw', 0)

    @property
    def green(self):
        return self._data.get(b'Grn ', 0)

    @property
    def cyan(self):
        return self._data.get(b'Cyn ', 0)

    @property
    def blue(self):
        return self._data.get(b'Bl  ', 0)

    @property
    def magenta(self):
        return self._data.get(b'Mgnt', 0)

    @property
    def use_tint(self):
        return bool(self._data.get(b'useTint', False))

    @property
    def tint_color(self):
        return self._data.get(b'tintColor')

    @property
    def preset_kind(self):
        return self._data.get(b'bwPresetKind', 1)

    @property
    def preset_file_name(self):
        value = self._data.get(b'blackAndWhitePresetFileName', '') + ''
        return value.strip('\x00')


class PhotoFilter(AdjustmentLayer):
    """Photo filter adjustment."""
    _KEY = TaggedBlockID.PHOTO_FILTER

    @property
    def xyz(self):
        """xyz.

        :rtype: bool
        """
        return self._data.xyz

    @property
    def color_space(self):
        return self._data.color_space

    @property
    def color_components(self):
        return self._data.color_components

    @property
    def density(self):
        return self._data.density

    @property
    def luminosity(self):
        return self._data.luminosity


class ChannelMixer(AdjustmentLayer):
    """Channel mixer adjustment."""
    _KEY = TaggedBlockID.CHANNEL_MIXER

    @property
    def monochrome(self):
        return self._data.monochrome

    @property
    def data(self):
        return self._data.data


class ColorLookup(AdjustmentLayer):
    """Color lookup adjustment."""
    _KEY = TaggedBlockID.COLOR_LOOKUP


class Invert(AdjustmentLayer):
    """Invert adjustment."""
    _KEY = TaggedBlockID.INVERT


class Posterize(AdjustmentLayer):
    """Posterize adjustment."""
    _KEY = TaggedBlockID.POSTERIZE

    @property
    def posterize(self):
        """Posterize value.

        :rtype: int
        """
        return self._data.value


class Threshold(AdjustmentLayer):
    """Threshold adjustment."""
    _KEY = TaggedBlockID.THRESHOLD

    @property
    def threshold(self):
        """Threshold value.

        :rtype: int
        """
        return self._data.value


class SelectiveColor(AdjustmentLayer):
    """Selective color adjustment."""
    _KEY = TaggedBlockID.SELECTIVE_COLOR

    @property
    def method(self):
        return self._data.method

    @property
    def data(self):
        return self._data.data


class GradientMap(AdjustmentLayer):
    """Gradient map adjustment."""
    _KEY = TaggedBlockID.GRADIENT_MAP

    @property
    def reversed(self):
        return self._data.is_reversed

    @property
    def dithered(self):
        return self._data.is_dithered

    @property
    def gradient_name(self):
        return self._data.name.strip('\x00')

    @property
    def color_stops(self):
        return self._data.color_stops

    @property
    def transparency_stops(self):
        return self._data.transparency_stops

    @property
    def expansion(self):
        return self._data.expansion

    @property
    def interpolation(self):
        """Interpolation between 0.0 and 1.0."""
        return self._data.interpolation / 4096.0

    @property
    def length(self):
        return self._data.length

    @property
    def mode(self):
        return self._data.mode

    @property
    def random_seed(self):
        return self._data.random_seed

    @property
    def show_transparency(self):
        return self._data.show_transparency

    @property
    def use_vector_color(self):
        return self._data.use_vector_color

    @property
    def roughness(self):
        return self._data.roughness

    @property
    def color_model(self):
        return self._data.color_model

    @property
    def min_color(self):
        return self._data.minimum_color

    @property
    def max_color(self):
        return self._data.maximum_color
