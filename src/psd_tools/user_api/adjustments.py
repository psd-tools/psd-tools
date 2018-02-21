# -*- coding: utf-8 -*-
"""Adjustment API.

Adjustment classes are attached to ``data`` attribute of
:py:class:`~psd_tools.user_api.layers.AdjustmentLayer`.


Example::

    if layer.kind == 'adjustment':
        adjustment = layer.data
"""
from __future__ import absolute_import
import inspect
import logging
from psd_tools.constants import TaggedBlock
from psd_tools.decoder.actions import UnitFloat
import psd_tools.user_api.actions

logger = logging.getLogger(__name__)


class _NameMixin(object):
    """Nameable wrapper."""
    def __init__(self, data):
        self._data = data

    @property
    def name(self):
        return self.__class__.__name__.lower()

    def __repr__(self):
        return "<%s>" % (self.name,)


class _DescriptorMixin(_NameMixin):
    """Descriptor wrapper."""
    def __init__(self, descriptor):
        self._descriptor = descriptor

    def _get(self, key, default=None):
        """Get attribute in the low-level structure.

        :param key: property key
        :type key: bytes
        :param default: default value to return
        """
        return self._descriptor.get(key, default)


class BrightnessContrast(_DescriptorMixin):
    """Brightness and contrast adjustment."""

    @property
    def brightness(self):
        return self._get(b'Brgh', 0)

    @property
    def contrast(self):
        return self._get(b'Cntr', 0)

    @property
    def mean(self):
        return self._get(b'means', 0)

    @property
    def lab(self):
        return self._get(b'Lab ', False)

    @property
    def use_legacy(self):
        return self._get(b'useLegacy', False)

    @property
    def vrsn(self):
        return self._get(b'Vrsn', 1)

    @property
    def automatic(self):
        return self._get(b'auto', False)


class Curves(_NameMixin):
    """
    Curves adjustment.

    Curves contain a list of
    :py:class:`~psd_tools.decoder.tagged_blocks.CurveData`.
    """
    @property
    def count(self):
        return self._data.count

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

    def __repr__(self):
        return "<%s: data=%s>" % (self.name, self.data)


class Exposure(_NameMixin):
    """
    Exposure adjustment.
    """
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

    def __repr__(self):
        return "<%s: exposure=%g offset=%g gamma=%g>" % (
            self.name, self.exposure, self.offset,
            self.gamma)


class Levels(_NameMixin):
    """
    Levels adjustment.

    Levels contain a list of
    :py:class:`~psd_tools.decoder.tagged_blocks.LevelRecord`.
    """
    @property
    def data(self):
        """
        List of level records. The first record is the master.

        :rtype: list
        """
        return self._data.data

    @property
    def master(self):
        """Master record.

        :rtype: psd_tools.decoder.tagged_blocks.LevelRecord
        """
        return self._data.data[0]

    def __repr__(self):
        return "<%s: master=%s>" % (
            self.name, self.master)


class Vibrance(_DescriptorMixin):
    """Vibrance adjustment."""
    @property
    def vibrance(self):
        """Vibrance.

        :rtype: int
        """
        return self._get(b'vibrance', 0)

    @property
    def saturation(self):
        """Saturation.

        :rtype: int
        """
        return self._get(b'Strt', 0)

    def __repr__(self):
        return "<%s: vibrance=%g saturation=%g>" % (
            self.name, self.vibrance, self.saturation)


class HueSaturation(_NameMixin):
    """
    Hue/Saturation adjustment.

    HueSaturation contains a list of
    :py:class:`~psd_tools.decoder.tagged_blocks.HueSaturationData`.
    """
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
        return self._data.enable_colorization

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

    def __repr__(self):
        return "<%s: colorization=%s master=%s>" % (
            self.name, self.colorization, self.master)


class ColorBalance(_NameMixin):
    """Color balance adjustment."""
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
    def preserve_luminosity(self):
        return self._data.preserve_luminosity

    def __repr__(self):
        return "<%s: shadows=%s midtones=%s highlights=%s>" % (
            self.name, self.shadows, self.midtones, self.highlights)


class BlackWhite(_DescriptorMixin):
    """Black and white adjustment."""
    @property
    def red(self):
        return self._get(b'Rd  ', 0)

    @property
    def yellow(self):
        return self._get(b'Yllw', 0)

    @property
    def green(self):
        return self._get(b'Grn ', 0)

    @property
    def cyan(self):
        return self._get(b'Cyn ', 0)

    @property
    def blue(self):
        return self._get(b'Bl  ', 0)

    @property
    def magenta(self):
        return self._get(b'Mgnt', 0)

    @property
    def use_tint(self):
        return self._get(b'useTint', False)

    @property
    def tint_color(self):
        return self._get(b'tintColor')

    @property
    def preset_kind(self):
        return self._get(b'bwPresetKind', 1)

    @property
    def preset_file_name(self):
        return self._get(b'blackAndWhitePresetFileName', '')

    def __repr__(self):
        return (
            "<%s: red=%g yellow=%g green=%g cyan=%g blue=%g magenta=%g>" % (
                self.name, self.red, self.yellow, self.green, self.cyan,
                self.blue, self.magenta
            )
        )


class PhotoFilter(_NameMixin):
    """Photo filter adjustment."""
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
    def preserve_luminosity(self):
        return self._data.preserve_luminosity

    def __repr__(self):
        return (
            "<%s: xyz=%s color_space=%g color_components=%s density=%g>" % (
                self.name, self.xyz, self.color_space, self.color_components,
                self.density
            )
        )


class ChannelMixer(_NameMixin):
    """Channel mixer adjustment."""
    @property
    def monochrome(self):
        return self._data.monochrome

    @property
    def mixer_settings(self):
        return self._data.mixer_settings

    def __repr__(self):
        return (
            "<%s: monochrome=%g, settings=%s>" % (
                self.name, self.monochrome, self.mixer_settings
            )
        )


class ColorLookup(_DescriptorMixin):
    """Color lookup adjustment."""
    pass


class Invert(_NameMixin):
    """Invert adjustment."""
    pass


class Posterize(_NameMixin):
    """Posterize adjustment."""
    @property
    def posterize(self):
        """Posterize value.

        :rtype: int
        """
        return self._data.value

    def __repr__(self):
        return "<%s: posterize=%s>" % (self.name, self.posterize)


class Threshold(_NameMixin):
    """Threshold adjustment."""
    @property
    def threshold(self):
        """Threshold value.

        :rtype: int
        """
        return self._data.value

    def __repr__(self):
        return "<%s: threshold=%s>" % (self.name, self.threshold)


class SelectiveColor(_NameMixin):
    """Selective color adjustment."""
    @property
    def method(self):
        return self._data.method

    @property
    def data(self):
        return self._data.items

    def __repr__(self):
        return "<%s: method=%g>" % (self.name, self.method)


class GradientMap(_NameMixin):
    """Gradient map adjustment."""
    @property
    def reversed(self):
        return self._data.reversed

    @property
    def dithered(self):
        return self._data.dithered

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
        return self._data.min_color

    @property
    def max_color(self):
        return self._data.max_color

    def __repr__(self):
        return "<%s: name=%s>" % (self.name, self.gradient_name)
