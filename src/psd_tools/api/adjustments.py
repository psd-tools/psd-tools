"""
Adjustment and fill layers.

Example::

    if layer.kind == 'brightnesscontrast':
        print(layer.brightness)

    if layer.kind == 'gradientfill':
        print(layer.gradient_kind)
"""

import logging
from typing import Any

from psd_tools.api.layers import AdjustmentLayer, FillLayer
from psd_tools.constants import Tag
from psd_tools.psd.adjustments import Curves as CurvesData
from psd_tools.psd.adjustments import LevelRecord
from psd_tools.psd.adjustments import Levels as LevelsData
from psd_tools.psd.descriptor import DescriptorBlock
from psd_tools.registry import new_registry

logger = logging.getLogger(__name__)

TYPES, register = new_registry(attribute="_KEY")


def _assert_data(data: Any) -> Any:
    """Validate that data is not None and return it.

    :raises ValueError: If data is None
    """
    if data is None:
        raise ValueError("Adjustment layer data is None")
    return data


@register(Tag.SOLID_COLOR_SHEET_SETTING)
class SolidColorFill(FillLayer):
    """Solid color fill."""

    @property
    def data(self) -> DescriptorBlock:
        """Color in Descriptor(RGB)."""
        return _assert_data(self._data).get(b"Clr ")


@register(Tag.PATTERN_FILL_SETTING)
class PatternFill(FillLayer):
    """Pattern fill."""

    @property
    def data(self) -> DescriptorBlock:
        """Pattern in Descriptor(PATTERN)."""
        return _assert_data(self._data).get(b"Ptrn")


@register(Tag.GRADIENT_FILL_SETTING)
class GradientFill(FillLayer):
    """Gradient fill."""

    @property
    def angle(self) -> float:
        return float(_assert_data(self._data).get(b"Angl"))

    @property
    def gradient_kind(self) -> str:
        """
        Kind of the gradient, one of the following:

         - `Linear`
         - `Radial`
         - `Angle`
         - `Reflected`
         - `Diamond`
        """
        return _assert_data(self._data).get(b"Type").get_name()

    @property
    def data(self) -> DescriptorBlock:
        """Gradient in Descriptor(GRADIENT)."""
        return _assert_data(self._data).get(b"Grad")


@register(Tag.CONTENT_GENERATOR_EXTRA_DATA)
class BrightnessContrast(AdjustmentLayer):
    """Brightness and contrast adjustment."""

    # Tag.BRIGHTNESS_AND_CONTRAST is obsolete.

    @property
    def brightness(self) -> int:
        return int(_assert_data(self._data).get(b"Brgh", 0))

    @property
    def contrast(self) -> int:
        return int(_assert_data(self._data).get(b"Cntr", 0))

    @property
    def mean(self) -> int:
        return int(_assert_data(self._data).get(b"means", 0))

    @property
    def lab(self) -> bool:
        return bool(_assert_data(self._data).get(b"Lab ", False))

    @property
    def use_legacy(self) -> bool:
        return bool(_assert_data(self._data).get(b"useLegacy", False))

    @property
    def vrsn(self) -> int:
        return int(_assert_data(self._data).get(b"Vrsn", 1))

    @property
    def automatic(self) -> bool:
        return bool(_assert_data(self._data).get(b"auto", False))


@register(Tag.CURVES)
class Curves(AdjustmentLayer):
    """
    Curves adjustment.
    """

    @property
    def data(self) -> CurvesData:
        """
        Raw data.

        :return: :py:class:`~psd_tools.psd.adjustments.Curves`
        """
        return _assert_data(self._data)

    @property
    def extra(self) -> Any:
        return self.data.extra


@register(Tag.EXPOSURE)
class Exposure(AdjustmentLayer):
    """
    Exposure adjustment.
    """

    @property
    def exposure(self) -> float:
        """Exposure.

        :return: `float`
        """
        return float(_assert_data(self._data).exposure)

    @property
    def exposure_offset(self) -> float:
        """Exposure offset.

        :return: `float`
        """
        return float(_assert_data(self._data).offset)

    @property
    def gamma(self) -> float:
        """Gamma.

        :return: `float`
        """
        return float(_assert_data(self._data).gamma)


@register(Tag.LEVELS)
class Levels(AdjustmentLayer):
    """
    Levels adjustment.

    Levels contain a list of
    :py:class:`~psd_tools.psd.adjustments.LevelRecord`.
    """

    @property
    def data(self) -> LevelsData:
        """
        List of level records. The first record is the master.

        :return: :py:class:`~psd_tools.psd.adjustments.Levels`.
        """
        return _assert_data(self._data)

    @property
    def master(self) -> LevelRecord:
        """Master record."""
        return self.data[0]


@register(Tag.VIBRANCE)
class Vibrance(AdjustmentLayer):
    """Vibrance adjustment."""

    @property
    def vibrance(self) -> int:
        """Vibrance.

        :return: `int`
        """
        return int(_assert_data(self._data).get(b"vibrance", 0))

    @property
    def saturation(self) -> int:
        """Saturation.

        :return: `int`
        """
        return int(_assert_data(self._data).get(b"Strt", 0))


@register(Tag.HUE_SATURATION)
class HueSaturation(AdjustmentLayer):
    """
    Hue/Saturation adjustment.

    HueSaturation contains a list of data.
    """

    @property
    def data(self) -> list:
        """
        List of Hue/Saturation records.

        :return: `list`
        """
        return _assert_data(self._data).items

    @property
    def enable_colorization(self) -> int:
        """Enable colorization.

        :return: `int`
        """
        return int(_assert_data(self._data).enable)

    @property
    def colorization(self) -> tuple:
        """Colorization.

        :return: `tuple`
        """
        return _assert_data(self._data).colorization

    @property
    def master(self) -> tuple:
        """Master record.

        :return: `tuple`
        """
        return _assert_data(self._data).master


@register(Tag.COLOR_BALANCE)
class ColorBalance(AdjustmentLayer):
    """Color balance adjustment."""

    @property
    def shadows(self) -> tuple:
        """Shadows.

        :return: `tuple`
        """
        return _assert_data(self._data).shadows

    @property
    def midtones(self) -> tuple:
        """Mid-tones.

        :return: `tuple`
        """
        return _assert_data(self._data).midtones

    @property
    def highlights(self) -> tuple:
        """Highlights.

        :return: `tuple`
        """
        return _assert_data(self._data).highlights

    @property
    def luminosity(self) -> int:
        """Luminosity.

        :return: `int`
        """
        return int(_assert_data(self._data).luminosity)


@register(Tag.BLACK_AND_WHITE)
class BlackAndWhite(AdjustmentLayer):
    """Black and white adjustment."""

    @property
    def red(self) -> int:
        return _assert_data(self._data).get(b"Rd  ", 40)

    @property
    def yellow(self) -> int:
        return _assert_data(self._data).get(b"Yllw", 60)

    @property
    def green(self) -> int:
        return _assert_data(self._data).get(b"Grn ", 40)

    @property
    def cyan(self) -> int:
        return _assert_data(self._data).get(b"Cyn ", 60)

    @property
    def blue(self) -> int:
        return _assert_data(self._data).get(b"Bl  ", 20)

    @property
    def magenta(self) -> int:
        return _assert_data(self._data).get(b"Mgnt", 80)

    @property
    def use_tint(self) -> bool:
        return bool(_assert_data(self._data).get(b"useTint", False))

    @property
    def tint_color(self) -> Any:
        return _assert_data(self._data).get(b"tintColor")

    @property
    def preset_kind(self) -> int:
        return _assert_data(self._data).get(b"bwPresetKind", 1)

    @property
    def preset_file_name(self) -> str:
        value = _assert_data(self._data).get(b"blackAndWhitePresetFileName", "") + ""
        return value.strip("\x00")


@register(Tag.PHOTO_FILTER)
class PhotoFilter(AdjustmentLayer):
    """Photo filter adjustment."""

    @property
    def xyz(self) -> bool:
        """xyz.

        :return: `bool`
        """
        return _assert_data(self._data).xyz

    @property
    def color_space(self) -> Any:
        return _assert_data(self._data).color_space

    @property
    def color_components(self) -> Any:
        return _assert_data(self._data).color_components

    @property
    def density(self) -> Any:
        return _assert_data(self._data).density

    @property
    def luminosity(self) -> Any:
        return _assert_data(self._data).luminosity


@register(Tag.CHANNEL_MIXER)
class ChannelMixer(AdjustmentLayer):
    """Channel mixer adjustment."""

    @property
    def monochrome(self) -> Any:
        return _assert_data(self._data).monochrome

    @property
    def data(self) -> Any:
        return _assert_data(self._data).data


@register(Tag.COLOR_LOOKUP)
class ColorLookup(AdjustmentLayer):
    """Color lookup adjustment."""

    pass


@register(Tag.INVERT)
class Invert(AdjustmentLayer):
    """Invert adjustment."""

    pass


@register(Tag.POSTERIZE)
class Posterize(AdjustmentLayer):
    """Posterize adjustment."""

    @property
    def posterize(self) -> int:
        """Posterize value.

        :return: `int`
        """
        return _assert_data(self._data)


@register(Tag.THRESHOLD)
class Threshold(AdjustmentLayer):
    """Threshold adjustment."""

    @property
    def threshold(self) -> int:
        """Threshold value.

        :return: `int`
        """
        return _assert_data(self._data)


@register(Tag.SELECTIVE_COLOR)
class SelectiveColor(AdjustmentLayer):
    """Selective color adjustment."""

    @property
    def method(self) -> Any:
        return _assert_data(self._data).method

    @property
    def data(self) -> Any:
        return _assert_data(self._data).data


@register(Tag.GRADIENT_MAP)
class GradientMap(AdjustmentLayer):
    """Gradient map adjustment."""

    @property
    def reversed(self) -> Any:
        return _assert_data(self._data).is_reversed

    @property
    def dithered(self) -> Any:
        return _assert_data(self._data).is_dithered

    @property
    def gradient_name(self) -> Any:
        return _assert_data(self._data).name.strip("\x00")

    @property
    def color_stops(self) -> Any:
        return _assert_data(self._data).color_stops

    @property
    def transparency_stops(self) -> Any:
        return _assert_data(self._data).transparency_stops

    @property
    def expansion(self) -> Any:
        return _assert_data(self._data).expansion

    @property
    def interpolation(self) -> float:
        """Interpolation between 0.0 and 1.0."""
        return _assert_data(self._data).interpolation / 4096.0

    @property
    def length(self) -> Any:
        return _assert_data(self._data).length

    @property
    def mode(self) -> Any:
        return _assert_data(self._data).mode

    @property
    def random_seed(self) -> Any:
        return _assert_data(self._data).random_seed

    @property
    def show_transparency(self) -> Any:
        return _assert_data(self._data).show_transparency

    @property
    def use_vector_color(self) -> Any:
        return _assert_data(self._data).use_vector_color

    @property
    def roughness(self) -> Any:
        return _assert_data(self._data).roughness

    @property
    def color_model(self) -> Any:
        return _assert_data(self._data).color_model

    @property
    def min_color(self) -> Any:
        return _assert_data(self._data).minimum_color

    @property
    def max_color(self) -> Any:
        return _assert_data(self._data).maximum_color
