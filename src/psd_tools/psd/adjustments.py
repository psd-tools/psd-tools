"""
Adjustment layer structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import io
import logging

from psd_tools.constants import TaggedBlockID
from psd_tools.psd.base import (
    BaseElement, EmptyElement, ListElement, ShortIntegerElement,
)
from psd_tools.psd.color import Color
from psd_tools.psd.descriptor import DescriptorBlock, DescriptorBlock2
from psd_tools.validators import in_
from psd_tools.utils import (
    read_fmt, write_fmt, read_length_block, write_length_block, is_readable,
    write_bytes, read_unicode_string, write_unicode_string, write_padding,
    read_pascal_string, write_pascal_string, trimmed_repr, new_registry
)

logger = logging.getLogger(__name__)


ADJUSTMENT_TYPES, register = new_registry()

ADJUSTMENT_TYPES.update({
    TaggedBlockID.BLACK_AND_WHITE: DescriptorBlock,
    TaggedBlockID.GRADIENT_FILL_SETTING: DescriptorBlock,
    TaggedBlockID.INVERT: EmptyElement,
    TaggedBlockID.PATTERN_FILL_SETTING: DescriptorBlock,
    TaggedBlockID.POSTERIZE: ShortIntegerElement,
    TaggedBlockID.SOLID_COLOR_SHEET_SETTING: DescriptorBlock,
    TaggedBlockID.THRESHOLD: ShortIntegerElement,
    TaggedBlockID.VIBRANCE: DescriptorBlock,
})


@register(TaggedBlockID.BRIGHTNESS_AND_CONTRAST)
@attr.s(slots=True)
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
@attr.s(slots=True)
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
    :py:class:`~psd_tools.psd.descriptor.Descriptor`.

    .. py:attribute:: version
    .. py:attribute:: data_version
    """
    @classmethod
    def read(cls, fp, **kwargs):
        version, data_version = read_fmt('HI', fp)
        return cls(version=version, data_version=data_version,
                   **cls._read_body(fp))

    def write(self, fp, padding=4, **kwargs):
        written = write_fmt(fp, 'HI', self.version, self.data_version)
        written += self._write_body(fp)
        written += write_padding(fp, written, padding)
        return written


@register(TaggedBlockID.CHANNEL_MIXER)
@attr.s(slots=True)
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


@register(TaggedBlockID.CURVES)
@attr.s(slots=True)
class Curves(BaseElement):
    """
    Curves structure.

    .. py:attribute:: is_map
    .. py:attribute:: version
    .. py:attribute:: count
    .. py:attribute:: data
    .. py:attribute:: extra
    """
    is_map = attr.ib(default=False, type=bool, converter=bool)
    version = attr.ib(default=0, type=int)
    count_map = attr.ib(default=0, type=int)
    data = attr.ib(factory=list, converter=list)
    extra = attr.ib(default=None)

    @classmethod
    def read(cls, fp, **kwargs):
        # NOTE: This is highly experimental and unstable.
        is_map, version, count_map = read_fmt('BHI', fp)
        assert version in (1, 4), 'Invalid version %d' % (version)

        if version == 1:
            count = bin(count_map).count('1')  # Bitmap = channel index?
        else:
            count = count_map

        if is_map:
            # This lookup format is never documented.
            data = [list(read_fmt('256B', fp)) for _ in range(count)]
        else:
            data = []
            for _ in range(count):
                point_count = read_fmt('H', fp)[0]
                assert 2 <= point_count and point_count <= 19, (
                    'Curves point count not in [2, 19]'
                )
                points = [read_fmt('2H', fp) for i in range(point_count)]
                data.append(points)

        extra = None
        if version == 1:
            extra = CurvesExtraMarker.read(fp, is_map=is_map)

        return cls(is_map, version, count_map, data, extra)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'BHI', self.is_map, self.version,
                            self.count_map)
        if self.is_map:
            written += sum(write_fmt(fp, '256B', *item) for item in self.data)
        else:
            for points in self.data:
                written += write_fmt(fp, 'H', len(points))
                written += sum(write_fmt(fp, '2H', *item) for item in points)

        if self.extra is not None:
            written += self.extra.write(fp)

        written += write_padding(fp, written, 4)
        return written


@attr.s(repr=False, slots=True)
class CurvesExtraMarker(ListElement):
    """
    Curves extra marker structure.

    .. py:attribute:: version
    """
    version = attr.ib(default=4, type=int, validator=in_((3, 4)))

    @classmethod
    def read(cls, fp, **kwargs):
        signature, version, count = read_fmt('4sHI', fp)
        assert signature == b'Crv ', 'Invalid signature %r' % (signature)
        items = []
        for i in range(count):
            items.append(CurvesExtraItem.read(fp, **kwargs))
        return cls(version=version, items=items)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, '4sHI', b'Crv ', self.version, len(self))
        written += sum(item.write(fp) for item in self)
        return written


@attr.s(slots=True)
class CurvesExtraItem(BaseElement):
    """
    Curves extra item.

    .. py:attribute:: channel_id
    .. py:attribute:: points
    """
    channel_id = attr.ib(default=0, type=int)
    points = attr.ib(factory=list, converter=list)

    @classmethod
    def read(cls, fp, is_map=False, **kwargs):
        if is_map:
            channel_id = read_fmt('H', fp)[0]
            points = list(read_fmt('256B', fp))
        else:
            channel_id, point_count = read_fmt('2H', fp)
            points = [read_fmt('2H', fp) for c in range(point_count)]
        return cls(channel_id, points)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'H', self.channel_id)
        if len(self.points) > 0 and isinstance(self.points[0], int):
            written += write_fmt(fp, '256B', *self.points)
        else:
            written += write_fmt(fp, 'H', len(self.points))
            written += sum(write_fmt(fp, '2H', *p) for p in self.points)
        return written


@register(TaggedBlockID.GRADIENT_MAP)
@attr.s(slots=True)
class GradientMap(BaseElement):
    """
    GradientMap structure.

    .. py:attribute:: version
    .. py:attribute:: is_reversed
    .. py:attribute:: is_dithered
    .. py:attribute:: name
    .. py:attribute:: color_stops
    .. py:attribute:: transparency_stops
    .. py:attribute:: expansion
    .. py:attribute:: interpolation
    .. py:attribute:: length
    .. py:attribute:: mode
    .. py:attribute:: random_seed
    .. py:attribute:: show_transparency
    .. py:attribute:: use_vector_color
    .. py:attribute:: roughness
    .. py:attribute:: color_model
    .. py:attribute:: minimum_color
    .. py:attribute:: maximum_color
    """
    version = attr.ib(default=1, type=int, validator=in_((1,)))
    is_reversed = attr.ib(default=0, type=int)
    is_dithered = attr.ib(default=0, type=int)
    name = attr.ib(default='', type=str)
    color_stops = attr.ib(factory=list, converter=list)
    transparency_stops = attr.ib(factory=list, converter=list)
    expansion = attr.ib(default=2, type=int, validator=in_((2,)))
    interpolation = attr.ib(default=0, type=int)
    length = attr.ib(default=32, type=int, validator=in_((32,)))
    mode = attr.ib(default=0, type=int)
    random_seed = attr.ib(default=0, type=int)
    show_transparency = attr.ib(default=0, type=int)
    use_vector_color = attr.ib(default=0, type=int)
    roughness = attr.ib(default=0, type=int)
    color_model = attr.ib(default=0, type=int)
    minimum_color = attr.ib(factory=list, converter=list)
    maximum_color = attr.ib(factory=list, converter=list)

    @classmethod
    def read(cls, fp, **kwargs):
        version, is_reversed, is_dithered = read_fmt('H2B', fp)
        assert version == 1, 'Invalid version %s' % (version)
        name = read_unicode_string(fp)
        count = read_fmt('H', fp)[0]
        color_stops = [ColorStop.read(fp) for _ in range(count)]
        count = read_fmt('H', fp)[0]
        transparency_stops = [TransparencyStop.read(fp) for _ in range(count)]
        expansion, interpolation, length, mode = read_fmt('4H', fp)
        assert expansion == 2, 'Invalid expansion %d' % (expansion)
        random_seed, show_transparency, use_vector_color = read_fmt('I2H', fp)
        roughness, color_model = read_fmt('IH', fp)
        minimum_color = read_fmt('4H', fp)
        maximum_color = read_fmt('4H', fp)
        read_fmt('2x', fp)  # Dummy?
        return cls(version, is_reversed, is_dithered, name, color_stops,
                   transparency_stops, expansion, interpolation, length,
                   mode, random_seed, show_transparency, use_vector_color,
                   roughness, color_model, minimum_color, maximum_color)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'H2B', self.version, self.is_reversed,
                            self.is_dithered)
        written += write_unicode_string(fp, self.name)
        written += write_fmt(fp, 'H', len(self.color_stops))
        written += sum(stop.write(fp) for stop in self.color_stops)
        written += write_fmt(fp, 'H', len(self.transparency_stops))
        written += sum(stop.write(fp) for stop in self.transparency_stops)
        written += write_fmt(
            fp, '4HI2HIH', self.expansion, self.interpolation, self.length,
            self.mode, self.random_seed, self.show_transparency,
            self.use_vector_color, self.roughness, self.color_model
        )
        written += write_fmt(fp, '4H', *self.minimum_color)
        written += write_fmt(fp, '4H', *self.maximum_color)
        written += write_fmt(fp, '2x')
        written += write_padding(fp, written, 4)
        return written


@attr.s(slots=True)
class ColorStop(BaseElement):
    """
    ColorStop of GradientMap.

    .. py:attribute:: location
    .. py:attribute:: midpoint
    .. py:attribute:: mode
    .. py:attribute:: color
    """
    location = attr.ib(default=0, type=int)
    midpoint = attr.ib(default=0, type=int)
    mode = attr.ib(default=0, type=int)
    color = attr.ib(default=(0, 0, 0, 0), type=tuple)

    @classmethod
    def read(cls, fp):
        location, midpoint, mode = read_fmt('2IH', fp)
        color = read_fmt('4H2x', fp)
        return cls(location, midpoint, mode, color)

    def write(self, fp):
        return write_fmt(
            fp, '2I5H2x', self.location, self.midpoint, self.mode, *self.color
        )


@attr.s(slots=True)
class TransparencyStop(BaseElement):
    """
    TransparencyStop of GradientMap.

    .. py:attribute:: location
    .. py:attribute:: midpoint
    .. py:attribute:: opacity
    """
    location = attr.ib(default=0, type=int)
    midpoint = attr.ib(default=0, type=int)
    opacity = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp):
        return cls(*read_fmt('2IH', fp))

    def write(self, fp):
        return write_fmt(fp, '2IH', *attr.astuple(self))


@register(TaggedBlockID.EXPOSURE)
@attr.s(slots=True)
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

    def write(self, fp, padding=4, **kwargs):
        written = write_fmt(fp, 'H3f', *attr.astuple(self))
        written += write_padding(fp, written, padding)
        return written


@register(TaggedBlockID.HUE_SATURATION_V4)
@register(TaggedBlockID.HUE_SATURATION)
@attr.s(slots=True)
class HueSaturation(BaseElement):
    """
    HueSaturation structure.

    .. py:attribute:: version
    .. py:attribute:: enable
    .. py:attribute:: colorization
    .. py:attribute:: master
    .. py:attribute:: items
    """
    version = attr.ib(default=2, type=int)
    enable = attr.ib(default=1, type=int)
    colorization = attr.ib(default=(0, 0, 0), type=tuple)
    master = attr.ib(default=(0, 0, 0), type=tuple)
    items = attr.ib(factory=list, converter=list)

    @classmethod
    def read(cls, fp, **kwargs):
        version, enable = read_fmt('HBx', fp)
        assert version == 2, 'Invalid version %d' % (version)
        colorization = read_fmt('3h', fp)
        master = read_fmt('3h', fp)
        items = []
        for _ in range(6):
            range_values = read_fmt('4h', fp)
            settings_values = read_fmt('3h', fp)
            items.append([range_values, settings_values])
        return cls(version, enable, colorization, master, items)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'HBx', self.version, self.enable)
        written += write_fmt(fp, '3h', *self.colorization)
        written += write_fmt(fp, '3h', *self.master)
        for item in self.items:
            written += write_fmt(fp, '4h', *item[0])
            written += write_fmt(fp, '3h', *item[1])
        written += write_padding(fp, written, 4)
        return written


@register(TaggedBlockID.LEVELS)
@attr.s(slots=True)
class Levels(ListElement):
    """
    List of level records. See :py:class:
    `~psd_tools.psd.adjustments.LevelRecord`.

    .. py:attribute:: version

        Version.

    .. py:attribute:: extra_version

        Version of the extra field.
    """
    version = attr.ib(default=0, type=int, validator=in_((2,)))
    extra_version = attr.ib(default=None)

    @classmethod
    def read(cls, fp, **kwargs):
        version = read_fmt('H', fp)[0]
        assert version == 2, 'Invalid version %d' % (version)
        items = [LevelRecord.read(fp) for _ in range(29)]

        extra_version = None
        if is_readable(fp, 6):
            signature, extra_version = read_fmt('4sH', fp)
            assert signature == b'Lvls', 'Invalid signature %r' % (signature)
            assert extra_version == 3, 'Invalid extra version %d' % (
                extra_version
            )
            count = read_fmt('H', fp)[0]
            items += [LevelRecord.read(fp) for _ in range(count - 29)]

        return cls(version=version, extra_version=extra_version, items=items)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'H', self.version)
        for index in range(29):
            written += self[index].write(fp)

        if self.extra_version is not None:
            written += write_fmt(fp, '4sH', b'Lvls', self.extra_version)
            written += write_fmt(fp, 'H', len(self))
            for index in range(29, len(self)):
                written += self[index].write(fp)

        written += write_padding(fp, written, 4)
        return written


@attr.s(slots=True)
class LevelRecord(BaseElement):
    """
    Level record.

    .. py:attribute:: input_floor

        Input floor (0...253).

    .. py:attribute:: input_ceiling

        Input ceiling (2...255).

    .. py:attribute:: output_floor

        Output floor (0...255). Matched to input floor.

    .. py:attribute:: output_ceiling

        Output ceiling (0...255).

    .. py:attribute:: gamma

        Gamma. Short integer from 10...999 representing 0.1...9.99. Applied
        to all image data.
    """
    input_floor = attr.ib(default=0, type=int)
    input_ceiling = attr.ib(default=0, type=int)
    output_floor = attr.ib(default=0, type=int)
    output_ceiling = attr.ib(default=0, type=int)
    gamma = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp):
        return cls(*read_fmt('5H', fp))

    def write(self, fp):
        return write_fmt(fp, '5H', *attr.astuple(self))


@register(TaggedBlockID.PHOTO_FILTER)
@attr.s(slots=True)
class PhotoFilter(BaseElement):
    """
    PhotoFilter structure.

    .. py:attribute:: version
    .. py:attribute:: xyz
    .. py:attribute:: color_space
    .. py:attribute:: color_components
    .. py:attribute:: density
    .. py:attribute:: luminosity
    """
    version = attr.ib(default=0, type=int, validator=in_((2, 3)))
    xyz = attr.ib(default=(0, 0, 0), type=tuple)
    color_space = attr.ib(default=None)
    color_components = attr.ib(default=None)
    density = attr.ib(default=None)
    luminosity = attr.ib(default=None)

    @classmethod
    def read(cls, fp, **kwargs):
        version = read_fmt('H', fp)[0]
        assert version in (2, 3), 'Invalid version %d' % (version)
        if version == 3:
            xyz = read_fmt('3I', fp)
            color_space = None
            color_components = None
        else:
            xyz = None
            color_space = read_fmt('H', fp)[0]
            color_components = read_fmt('4H', fp)
        density, luminosity = read_fmt('IB', fp)
        return cls(version, xyz, color_space, color_components, density,
                   luminosity)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'H', self.version)
        if self.version == 3:
            written += write_fmt(fp, '3I', *self.xyz)
        else:
            written += write_fmt(fp, 'H4H', self.color_space,
                                 *self.color_components)
        written += write_fmt(fp, 'IB', self.density, self.luminosity)
        written += write_padding(fp, written, 4)
        return written


@register(TaggedBlockID.SELECTIVE_COLOR)
@attr.s(slots=True)
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
