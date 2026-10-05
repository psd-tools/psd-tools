"""
Adjustment and fill layers.

Example::

    if layer.kind == 'brightnesscontrast':
        print(layer.brightness)

    if layer.kind == 'gradientfill':
        print(layer.gradient_kind)
"""

import logging

from psd_tools.api._descriptor import get_descriptor, get_enum, get_scalar
from psd_tools.api.layers import AdjustmentLayer, FillLayer
from psd_tools.constants import GradientType, Tag
from psd_tools.psd.adjustments import Curves as CurvesData
from psd_tools.psd.adjustments import CurvesExtraMarker
from psd_tools.psd.adjustments import LevelRecord
from psd_tools.psd.adjustments import Levels as LevelsData
from psd_tools.psd.descriptor import Descriptor
from psd_tools.registry import new_registry

logger = logging.getLogger(__name__)

TYPES, register = new_registry(attribute="_KEY")


@register(Tag.SOLID_COLOR_SHEET_SETTING)
class SolidColorFill(FillLayer):
    """Solid color fill."""

    @property
    def data(self) -> Descriptor | None:
        """Color in Descriptor(RGB)."""
        return get_descriptor(self._data, b"Clr ")


@register(Tag.PATTERN_FILL_SETTING)
class PatternFill(FillLayer):
    """Pattern fill."""

    @property
    def data(self) -> Descriptor | None:
        """Pattern in Descriptor(PATTERN)."""
        return get_descriptor(self._data, b"Ptrn")


@register(Tag.GRADIENT_FILL_SETTING)
class GradientFill(FillLayer):
    """Gradient fill."""

    @property
    def angle(self) -> float | None:
        return get_scalar(self._data, b"Angl", float, None)

    @property
    def gradient_kind(self) -> str | None:
        """
        Kind of the gradient, or `None` if the file does not record one.

        One of `Linear`, `Radial`, `Angle`, `Reflected` or `Diamond`.
        """
        kind = get_enum(self._data, b"Type", GradientType)
        if kind is None or kind is GradientType.SHAPE_BURST:  # Stroke only.
            return None
        return kind.name.capitalize()

    @property
    def data(self) -> Descriptor | None:
        """Gradient in Descriptor(GRADIENT)."""
        return get_descriptor(self._data, b"Grad")


@register(Tag.CONTENT_GENERATOR_EXTRA_DATA)
class BrightnessContrast(AdjustmentLayer):
    """Brightness and contrast adjustment."""

    # Tag.BRIGHTNESS_AND_CONTRAST is obsolete.

    @property
    def brightness(self) -> int:
        return get_scalar(self._data, b"Brgh", int, 0)

    @property
    def contrast(self) -> int:
        return get_scalar(self._data, b"Cntr", int, 0)

    @property
    def mean(self) -> int:
        return get_scalar(self._data, b"means", int, 0)

    @property
    def lab(self) -> bool:
        return get_scalar(self._data, b"Lab ", bool, False)

    @property
    def use_legacy(self) -> bool:
        return get_scalar(self._data, b"useLegacy", bool, False)

    @property
    def vrsn(self) -> int:
        return get_scalar(self._data, b"Vrsn", int, 1)

    @property
    def automatic(self) -> bool:
        return get_scalar(self._data, b"auto", bool, False)


@register(Tag.CURVES)
class Curves(AdjustmentLayer):
    """
    Curves adjustment.
    """

    @property
    def data(self) -> CurvesData | None:
        """
        Raw data.

        :return: :py:class:`~psd_tools.psd.adjustments.Curves`, or `None` if the
            block is absent
        """
        return self._data

    @property
    def extra(self) -> CurvesExtraMarker | None:
        """Extra curves records, or `None` if the file has none."""
        if self._data is None:
            return None
        extra = self._data.extra
        return extra if isinstance(extra, CurvesExtraMarker) else None


@register(Tag.EXPOSURE)
class Exposure(AdjustmentLayer):
    """
    Exposure adjustment.
    """

    @property
    def exposure(self) -> float | None:
        """Exposure.

        :return: `float`, or `None` if the block is absent
        """
        return None if self._data is None else float(self._data.exposure)

    @property
    def exposure_offset(self) -> float | None:
        """Exposure offset.

        :return: `float`, or `None` if the block is absent
        """
        return None if self._data is None else float(self._data.offset)

    @property
    def gamma(self) -> float | None:
        """Gamma.

        :return: `float`, or `None` if the block is absent
        """
        return None if self._data is None else float(self._data.gamma)


@register(Tag.LEVELS)
class Levels(AdjustmentLayer):
    """
    Levels adjustment.

    Levels contain a list of
    :py:class:`~psd_tools.psd.adjustments.LevelRecord`.
    """

    @property
    def data(self) -> LevelsData | None:
        """
        List of level records. The first record is the master.

        :return: :py:class:`~psd_tools.psd.adjustments.Levels`, or `None` if the
            block is absent
        """
        return self._data

    @property
    def master(self) -> LevelRecord | None:
        """Master record, or `None` if the block is absent or empty."""
        return self._data[0] if self._data else None


@register(Tag.VIBRANCE)
class Vibrance(AdjustmentLayer):
    """Vibrance adjustment."""

    @property
    def vibrance(self) -> int:
        """Vibrance.

        :return: `int`
        """
        return get_scalar(self._data, b"vibrance", int, 0)

    @property
    def saturation(self) -> int:
        """Saturation.

        :return: `int`
        """
        return get_scalar(self._data, b"Strt", int, 0)


@register(Tag.HUE_SATURATION)
class HueSaturation(AdjustmentLayer):
    """
    Hue/Saturation adjustment.

    HueSaturation contains a list of data.
    """

    @property
    def data(self) -> list | None:
        """
        List of Hue/Saturation records.

        :return: `list`, or `None` if the block is absent
        """
        return None if self._data is None else self._data.items

    @property
    def enable_colorization(self) -> int | None:
        """Enable colorization.

        :return: `int`, or `None` if the block is absent
        """
        return None if self._data is None else int(self._data.enable)

    @property
    def colorization(self) -> tuple | None:
        """Colorization.

        :return: `tuple`, or `None` if the block is absent
        """
        return None if self._data is None else self._data.colorization

    @property
    def master(self) -> tuple | None:
        """Master record.

        :return: `tuple`, or `None` if the block is absent
        """
        return None if self._data is None else self._data.master


@register(Tag.COLOR_BALANCE)
class ColorBalance(AdjustmentLayer):
    """Color balance adjustment."""

    @property
    def shadows(self) -> tuple | None:
        """Shadows.

        :return: `tuple`, or `None` if the block is absent
        """
        return None if self._data is None else self._data.shadows

    @property
    def midtones(self) -> tuple | None:
        """Mid-tones.

        :return: `tuple`, or `None` if the block is absent
        """
        return None if self._data is None else self._data.midtones

    @property
    def highlights(self) -> tuple | None:
        """Highlights.

        :return: `tuple`, or `None` if the block is absent
        """
        return None if self._data is None else self._data.highlights

    @property
    def luminosity(self) -> int | None:
        """Luminosity.

        :return: `int`, or `None` if the block is absent
        """
        return None if self._data is None else int(self._data.luminosity)


@register(Tag.BLACK_AND_WHITE)
class BlackAndWhite(AdjustmentLayer):
    """Black and white adjustment."""

    @property
    def red(self) -> int:
        return get_scalar(self._data, b"Rd  ", int, 40)

    @property
    def yellow(self) -> int:
        return get_scalar(self._data, b"Yllw", int, 60)

    @property
    def green(self) -> int:
        return get_scalar(self._data, b"Grn ", int, 40)

    @property
    def cyan(self) -> int:
        return get_scalar(self._data, b"Cyn ", int, 60)

    @property
    def blue(self) -> int:
        return get_scalar(self._data, b"Bl  ", int, 20)

    @property
    def magenta(self) -> int:
        return get_scalar(self._data, b"Mgnt", int, 80)

    @property
    def use_tint(self) -> bool:
        return get_scalar(self._data, b"useTint", bool, False)

    @property
    def tint_color(self) -> Descriptor | None:
        return get_descriptor(self._data, b"tintColor")

    @property
    def preset_kind(self) -> int:
        return get_scalar(self._data, b"bwPresetKind", int, 1)

    @property
    def preset_file_name(self) -> str:
        value = get_scalar(self._data, b"blackAndWhitePresetFileName", str, "")
        return value.strip("\x00")


@register(Tag.PHOTO_FILTER)
class PhotoFilter(AdjustmentLayer):
    """Photo filter adjustment."""

    @property
    def xyz(self) -> tuple[int, ...] | None:
        """XYZ coordinates, present in version 3 records.

        Version 2 records carry `color_space` and `color_components` instead,
        and leave this `None`.

        :return: `tuple` of three `int`, or `None`
        """
        return None if self._data is None else self._data.xyz

    @property
    def color_space(self) -> int | None:
        return None if self._data is None else self._data.color_space

    @property
    def color_components(self) -> tuple | None:
        return None if self._data is None else self._data.color_components

    @property
    def density(self) -> int | None:
        return None if self._data is None else self._data.density

    @property
    def luminosity(self) -> int | None:
        return None if self._data is None else self._data.luminosity


@register(Tag.CHANNEL_MIXER)
class ChannelMixer(AdjustmentLayer):
    """Channel mixer adjustment."""

    @property
    def monochrome(self) -> int | None:
        return None if self._data is None else self._data.monochrome

    @property
    def data(self) -> list | None:
        return None if self._data is None else self._data.data


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
    def posterize(self) -> int | None:
        """Posterize value.

        :return: `int`, or `None` if the block is absent
        """
        return self._data


@register(Tag.THRESHOLD)
class Threshold(AdjustmentLayer):
    """Threshold adjustment."""

    @property
    def threshold(self) -> int | None:
        """Threshold value.

        :return: `int`, or `None` if the block is absent
        """
        return self._data


@register(Tag.SELECTIVE_COLOR)
class SelectiveColor(AdjustmentLayer):
    """Selective color adjustment."""

    @property
    def method(self) -> int | None:
        return None if self._data is None else self._data.method

    @property
    def data(self) -> list | None:
        return None if self._data is None else self._data.data


@register(Tag.GRADIENT_MAP)
class GradientMap(AdjustmentLayer):
    """Gradient map adjustment."""

    @property
    def reversed(self) -> int | None:
        return None if self._data is None else self._data.is_reversed

    @property
    def dithered(self) -> int | None:
        return None if self._data is None else self._data.is_dithered

    @property
    def gradient_name(self) -> str | None:
        return None if self._data is None else self._data.name.strip("\x00")

    @property
    def color_stops(self) -> list | None:
        return None if self._data is None else self._data.color_stops

    @property
    def transparency_stops(self) -> list | None:
        return None if self._data is None else self._data.transparency_stops

    @property
    def expansion(self) -> int | None:
        return None if self._data is None else self._data.expansion

    @property
    def interpolation(self) -> float | None:
        """Interpolation between 0.0 and 1.0."""
        return None if self._data is None else self._data.interpolation / 4096.0

    @property
    def length(self) -> int | None:
        return None if self._data is None else self._data.length

    @property
    def mode(self) -> int | None:
        return None if self._data is None else self._data.mode

    @property
    def random_seed(self) -> int | None:
        return None if self._data is None else self._data.random_seed

    @property
    def show_transparency(self) -> int | None:
        return None if self._data is None else self._data.show_transparency

    @property
    def use_vector_color(self) -> int | None:
        return None if self._data is None else self._data.use_vector_color

    @property
    def roughness(self) -> int | None:
        return None if self._data is None else self._data.roughness

    @property
    def color_model(self) -> int | None:
        return None if self._data is None else self._data.color_model

    @property
    def min_color(self) -> list | None:
        return None if self._data is None else self._data.minimum_color

    @property
    def max_color(self) -> list | None:
        return None if self._data is None else self._data.maximum_color
