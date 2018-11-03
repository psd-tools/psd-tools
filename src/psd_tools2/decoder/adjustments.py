"""
Adjustment layer structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import io
import logging

from psd_tools2.constants import TaggedBlockID
from psd_tools2.decoder.base import EmptyElement, BaseElement, IntegerElement
from psd_tools2.decoder.color import Color
from psd_tools2.decoder.descriptor import DescriptorBlock, DescriptorBlock2
from psd_tools2.validators import in_
from psd_tools2.utils import (
    read_fmt, write_fmt, read_length_block, write_length_block, is_readable,
    write_bytes, read_unicode_string, write_unicode_string, write_padding,
    read_pascal_string, write_pascal_string, trimmed_repr, new_registry
)

logger = logging.getLogger(__name__)


ADJUSTMENT_TYPES, register = new_registry()

ADJUSTMENT_TYPES.update({
    TaggedBlockID.BLACK_AND_WHITE: DescriptorBlock,
    TaggedBlockID.INVERT: EmptyElement,
    TaggedBlockID.VIBRANCE: DescriptorBlock,
})


@register(TaggedBlockID.BRIGHTNESS_AND_CONTRAST)
@attr.s
class BrightnessContrast(BaseElement):
    """
    BrightnessContrast structure.

    .. py:attribute:: brightness
    .. py:attribute:: contrast
    .. py:attribute:: mean
    .. py:attribute:: lab_only
    """
    brightness = attr.ib(default=0, type=int)
    contrast = attr.ib(default=0, type=int)
    mean = attr.ib(default=0, type=int)
    lab_only = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(*read_fmt('3HBx', fp))

    def write(self, fp, **kwargs):
        return write_fmt(fp, '3HBx', *attr.astuple(self))


@register(TaggedBlockID.COLOR_BALANCE)
@attr.s
class ColorBalance(BaseElement):
    """
    ColorBalance structure.

    .. py:attribute:: shadows
    .. py:attribute:: midtones
    .. py:attribute:: highlights
    .. py:attribute:: luminosity
    """
    shadows = attr.ib(default=(0,) * 3, type=tuple)
    midtones = attr.ib(default=(0,) * 3, type=tuple)
    highlights = attr.ib(default=(0,) * 3, type=tuple)
    luminosity = attr.ib(default=False, type=bool)

    @classmethod
    def read(cls, fp, **kwargs):
        shadows = read_fmt('3h', fp)
        midtones = read_fmt('3h', fp)
        highlights = read_fmt('3h', fp)
        luminosity = read_fmt('B', fp)[0]
        return cls(shadows, midtones, highlights, luminosity)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, '3h', *self.shadows)
        written += write_fmt(fp, '3h', *self.midtones)
        written += write_fmt(fp, '3h', *self.highlights)
        written += write_fmt(fp, 'B', self.luminosity)
        written += write_padding(fp, written, 4)
        return written


@register(TaggedBlockID.COLOR_LOOKUP)
class ColorLookup(DescriptorBlock2):
    """
    Dict-like Descriptor-based structure. See
    :py:class:`~psd_tools2.decoder.descriptor.Descriptor`.

    .. py:attribute:: version
    .. py:attribute:: data_version
    """
    @classmethod
    def read(cls, fp, **kwargs):
        version, data_version = read_fmt('HI', fp)
        return cls(version=version, data_version=data_version,
                   **cls._read_body(fp))

    def write(self, fp, padding=4):
        written = write_fmt(fp, 'HI', self.version, self.data_version)
        written += self._write_body(fp)
        written += write_padding(fp, written, padding)
        return written


@register(TaggedBlockID.CHANNEL_MIXER)
@attr.s
class ChannelMixer(BaseElement):
    """
    ChannelMixer structure.

    .. py:attribute:: version
    .. py:attribute:: monochrome
    .. py:attribute:: data
    """
    version = attr.ib(default=1, type=int, validator=in_((1,)))
    monochrome = attr.ib(default=0, type=int)
    data = attr.ib(factory=list, converter=list)
    unknown = attr.ib(default=b'', type=bytes, repr=False)

    @classmethod
    def read(cls, fp, **kwargs):
        version, monochrome = read_fmt('2H', fp)
        data = list(read_fmt('5h', fp))
        unknown = fp.read()
        return cls(version, monochrome, data, unknown)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, '2H', self.version, self.monochrome)
        written += write_fmt(fp, '5h', *self.data)
        written += write_bytes(fp, self.unknown)
        return written


# @register(TaggedBlockID.CURVES)
# @attr.s
# class Curves(BaseElement):
#     """
#     Curves structure.
#     """


# @register(TaggedBlockID.GRADIENT_MAP)
# @attr.s
# class GradientMap(BaseElement):
#     """
#     GradientMap structure.
#     """


@register(TaggedBlockID.EXPOSURE)
@attr.s
class Exposure(BaseElement):
    """
    Exposure structure.

    .. py:attribute:: version
    .. py:attribute:: exposure
    .. py:attribute:: offset
    .. py:attribute:: gamma
    """
    version = attr.ib(default=0, type=int)
    exposure = attr.ib(default=0., type=float)
    offset = attr.ib(default=0., type=float)
    gamma = attr.ib(default=0., type=float)

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(*read_fmt('H3f', fp))

    def write(self, fp, padding=4):
        written = write_fmt(fp, 'H3f', *attr.astuple(self))
        written += write_padding(fp, written, padding)
        return written


# @register(TaggedBlockID.HUE_SATURATION)
# @attr.s
# class Levels(BaseElement):
#     """
#     Levels structure.
#     """


# @register(TaggedBlockID.LEVELS)
# @attr.s
# class Levels(BaseElement):
#     """
#     Levels structure.
#     """


# @register(TaggedBlockID.PHOTO_FILTER)
# @attr.s
# class PhotoFilter(BaseElement):
#     """
#     PhotoFilter structure.
#     """


@register(TaggedBlockID.SELECTIVE_COLOR)
@attr.s
class SelectiveColor(BaseElement):
    """
    SelectiveColor structure.

    .. py:attribute:: version
    .. py:attribute:: method
    .. py:attribute:: data
    """
    version = attr.ib(default=1, type=int, validator=in_((1,)))
    method = attr.ib(default=0, type=int)
    data = attr.ib(factory=list, converter=list)

    @classmethod
    def read(cls, fp, **kwargs):
        version, method = read_fmt('2H', fp)
        data = [read_fmt('4h', fp) for i in range(10)]
        return cls(version, method, data)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, '2H', self.version, self.method)
        for plate in self.data:
            written += write_fmt(fp, '4h', *plate)
        return written


@register(TaggedBlockID.POSTERIZE)
@register(TaggedBlockID.THRESHOLD)
class ShortInteger(IntegerElement):
    """
    Short integer structure.
    """
    @classmethod
    def read(cls, fp, **kwargs):
        return cls(read_fmt('H2x', fp)[0])

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'H2x', self.value)
