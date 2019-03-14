"""
Adjustment and fill layers.

Example::

    if layer.kind == 'brightnesscontrast':
        print(layer.brightness)

    if layer.kind == 'gradientfill':
        print(layer.gradient_kind)
"""
from __future__ import absolute_import
import logging


from psd_tools.api.layers import AdjustmentLayer, FillLayer
from psd_tools.constants import TaggedBlockID
from psd_tools.utils import new_registry


logger = logging.getLogger(__name__)


TYPES, register = new_registry(attribute='_KEY')


@register(TaggedBlockID.SOLID_COLOR_SHEET_SETTING)
class SolidColorFill(FillLayer):
    """Solid color fill."""

    @property
    def data(self):
        """Color in Descriptor(RGB)."""
        return self._data.get(b'Clr ')


@register(TaggedBlockID.PATTERN_FILL_SETTING)
class PatternFill(FillLayer):
    """Pattern fill."""

    @property
    def data(self):
        """Pattern in Descriptor(PATTERN)."""
        return self._data.get(b'Ptrn')


@register(TaggedBlockID.GRADIENT_FILL_SETTING)
class GradientFill(FillLayer):
    """Gradient fill."""

    @property
    def angle(self):
        return float(self._data.get(b'Angl'))

    @property
    def gradient_kind(self):
        """
        Kind of the gradient, one of the following:

         - `Linear`
         - `Radial`
         - `Angle`
         - `Reflected`
         - `Diamond`
        """
        return self._data.get(b'Type').get_name()

    @property
    def data(self):
        """Gradient in Descriptor(GRADIENT)."""
        return self._data.get(b'Grad')


@register(TaggedBlockID.CONTENT_GENERATOR_EXTRA_DATA)
class BrightnessContrast(AdjustmentLayer):
    """Brightness and contrast adjustment."""
    # TaggedBlockID.BRIGHTNESS_AND_CONTRAST is obsolete.

    @property
    def brightness(self):
        return int(self._data.get(b'Brgh', 0))

    @property
    def contrast(self):
        return int(self._data.get(b'Cntr', 0))

    @property
    def mean(self):
        return int(self._data.get(b'means', 0))

    @property
    def lab(self):
        return bool(self._data.get(b'Lab ', False))

    @property
    def use_legacy(self):
        return bool(self._data.get(b'useLegacy', False))

    @property
    def vrsn(self):
        return int(self._data.get(b'Vrsn', 1))

    @property
    def automatic(self):
        return bool(self._data.get(b'auto', False))


@register(TaggedBlockID.CURVES)
class Curves(AdjustmentLayer):
    """
    Curves adjustment.
    """

    @property
    def data(self):
        """
        Raw data.

        :return: :py:class:`~psd_tools.psd.adjustments.Curves`
        """
        return self._data

    @property
    def extra(self):
        return self._data.extra


@register(TaggedBlockID.EXPOSURE)
class Exposure(AdjustmentLayer):
    """
    Exposure adjustment.
    """

    @property
    def exposure(self):
        """Exposure.

        :return: `float`
        """
        return float(self._data.exposure)

    @property
    def offset(self):
        """Offset.

        :return: `float`
        """
        return float(self._data.offset)

    @property
    def gamma(self):
        """Gamma.

        :return: `float`
        """
        return float(self._data.gamma)


@register(TaggedBlockID.LEVELS)
class Levels(AdjustmentLayer):
    """
    Levels adjustment.

    Levels contain a list of
    :py:class:`~psd_tools.psd.adjustments.LevelRecord`.
    """

    @property
    def data(self):
        """
        List of level records. The first record is the master.

        :return: :py:class:`~psd_tools.psd.adjustments.Levels`.
        """
        return self._data

    @property
    def master(self):
        """Master record."""
        return self.data[0]


@register(TaggedBlockID.VIBRANCE)
class Vibrance(AdjustmentLayer):
    """Vibrance adjustment."""

    @property
    def vibrance(self):
        """Vibrance.

        :return: `int`
        """
        return int(self._data.get(b'vibrance', 0))

    @property
    def saturation(self):
        """Saturation.

        :return: `int`
        """
        return int(self._data.get(b'Strt', 0))


@register(TaggedBlockID.HUE_SATURATION)
class HueSaturation(AdjustmentLayer):
    """
    Hue/Saturation adjustment.

    HueSaturation contains a list of data.
    """

    @property
    def data(self):
        """
        List of Hue/Saturation records.

        :return: `list`
        """
        return self._data.items

    @property
    def enable_colorization(self):
        """Enable colorization.

        :return: `int`
        """
        return int(self._data.enable)

    @property
    def colorization(self):
        """Colorization.

        :return: `tuple`
        """
        return self._data.colorization

    @property
    def master(self):
        """Master record.

        :return: `tuple`
        """
        return self._data.master


@register(TaggedBlockID.COLOR_BALANCE)
class ColorBalance(AdjustmentLayer):
    """Color balance adjustment."""

    @property
    def shadows(self):
        """Shadows.

        :return: `tuple`
        """
        return self._data.shadows

    @property
    def midtones(self):
        """Mid-tones.

        :return: `tuple`
        """
        return self._data.midtones

    @property
    def highlights(self):
        """Highlights.

        :return: `tuple`
        """
        return self._data.highlights

    @property
    def luminosity(self):
        """Luminosity.

        :return: `int`
        """
        return int(self._data.luminosity)


@register(TaggedBlockID.BLACK_AND_WHITE)
class BlackAndWhite(AdjustmentLayer):
    """Black and white adjustment."""

    @property
    def red(self):
        return self._data.get(b'Rd  ', 40)

    @property
    def yellow(self):
        return self._data.get(b'Yllw', 60)

    @property
    def green(self):
        return self._data.get(b'Grn ', 40)

    @property
    def cyan(self):
        return self._data.get(b'Cyn ', 60)

    @property
    def blue(self):
        return self._data.get(b'Bl  ', 20)

    @property
    def magenta(self):
        return self._data.get(b'Mgnt', 80)

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


@register(TaggedBlockID.PHOTO_FILTER)
class PhotoFilter(AdjustmentLayer):
    """Photo filter adjustment."""

    @property
    def xyz(self):
        """xyz.

        :return: `bool`
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


@register(TaggedBlockID.CHANNEL_MIXER)
class ChannelMixer(AdjustmentLayer):
    """Channel mixer adjustment."""

    @property
    def monochrome(self):
        return self._data.monochrome

    @property
    def data(self):
        return self._data.data


@register(TaggedBlockID.COLOR_LOOKUP)
class ColorLookup(AdjustmentLayer):
    """Color lookup adjustment."""
    pass


@register(TaggedBlockID.INVERT)
class Invert(AdjustmentLayer):
    """Invert adjustment."""
    pass


@register(TaggedBlockID.POSTERIZE)
class Posterize(AdjustmentLayer):
    """Posterize adjustment."""

    @property
    def posterize(self):
        """Posterize value.

        :return: `int`
        """
        return self._data


@register(TaggedBlockID.THRESHOLD)
class Threshold(AdjustmentLayer):
    """Threshold adjustment."""

    @property
    def threshold(self):
        """Threshold value.

        :return: `int`
        """
        return self._data


@register(TaggedBlockID.SELECTIVE_COLOR)
class SelectiveColor(AdjustmentLayer):
    """Selective color adjustment."""

    @property
    def method(self):
        return self._data.method

    @property
    def data(self):
        return self._data.data


@register(TaggedBlockID.GRADIENT_MAP)
class GradientMap(AdjustmentLayer):
    """Gradient map adjustment."""

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
