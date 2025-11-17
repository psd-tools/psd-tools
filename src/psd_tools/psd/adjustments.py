"""
Adjustment layer structure.
"""

import logging
from typing import Any, BinaryIO, Optional, TypeVar

from attrs import define, field, astuple

from psd_tools.constants import Tag
from psd_tools.psd.base import (
    BaseElement,
    EmptyElement,
    ListElement,
    ShortIntegerElement,
)
from psd_tools.psd.descriptor import DescriptorBlock, DescriptorBlock2
from psd_tools.terminology import Enum, Key
from psd_tools.psd.bin_utils import (
    is_readable,
    read_fmt,
    read_unicode_string,
    write_bytes,
    write_fmt,
    write_padding,
    write_unicode_string,
)
from psd_tools.registry import new_registry
from psd_tools.validators import in_

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="BaseElement")

ADJUSTMENT_TYPES, register = new_registry()

ADJUSTMENT_TYPES.update(
    {
        Tag.BLACK_AND_WHITE: DescriptorBlock,
        Tag.GRADIENT_FILL_SETTING: DescriptorBlock,
        Tag.INVERT: EmptyElement,
        Tag.PATTERN_FILL_SETTING: DescriptorBlock,
        Tag.POSTERIZE: ShortIntegerElement,
        Tag.SOLID_COLOR_SHEET_SETTING: DescriptorBlock,
        Tag.THRESHOLD: ShortIntegerElement,
        Tag.VIBRANCE: DescriptorBlock,
    }
)


@register(Tag.BRIGHTNESS_AND_CONTRAST)
@define(repr=False)
class BrightnessContrast(BaseElement):
    """
    BrightnessContrast structure.

    .. py:attribute:: brightness
    .. py:attribute:: contrast
    .. py:attribute:: mean
    .. py:attribute:: lab_only
    """

    brightness: int = 0
    contrast: int = 0
    mean: int = 0
    lab_only: int = 0

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        return cls(*read_fmt("3HBx", fp))

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "3HBx", *astuple(self))


@register(Tag.COLOR_BALANCE)
@define(repr=False)
class ColorBalance(BaseElement):
    """
    ColorBalance structure.

    .. py:attribute:: shadows
    .. py:attribute:: midtones
    .. py:attribute:: highlights
    .. py:attribute:: luminosity
    """

    shadows: tuple = (0,) * 3
    midtones: tuple = (0,) * 3
    highlights: tuple = (0,) * 3
    luminosity: bool = False

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        shadows = read_fmt("3h", fp)
        midtones = read_fmt("3h", fp)
        highlights = read_fmt("3h", fp)
        luminosity = read_fmt("B", fp)[0]
        return cls(shadows, midtones, highlights, luminosity)  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "3h", *self.shadows)
        written += write_fmt(fp, "3h", *self.midtones)
        written += write_fmt(fp, "3h", *self.highlights)
        written += write_fmt(fp, "B", self.luminosity)
        written += write_padding(fp, written, 4)
        return written


@register(Tag.COLOR_LOOKUP)
class ColorLookup(DescriptorBlock2):
    """
    Dict-like Descriptor-based structure. See
    :py:class:`~psd_tools.psd.descriptor.Descriptor`.

    .. py:attribute:: version
    .. py:attribute:: data_version
    """

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        version, data_version = read_fmt("HI", fp)
        return cls(version=version, data_version=data_version, **cls._read_body(fp))  # type: ignore[call-arg, attr-defined]

    def write(self, fp: BinaryIO, padding: int = 4, **kwargs: Any) -> int:
        written = write_fmt(fp, "HI", self.version, self.data_version)
        written += self._write_body(fp)
        written += write_padding(fp, written, padding)
        return written


@register(Tag.CHANNEL_MIXER)
@define(repr=False)
class ChannelMixer(BaseElement):
    """
    ChannelMixer structure.

    .. py:attribute:: version
    .. py:attribute:: monochrome
    .. py:attribute:: data
    """

    version: int = field(default=1, validator=in_((1,)))
    monochrome: int = 0
    data: list = field(factory=list, converter=list)
    unknown: bytes = field(default=b"", repr=False)

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        version, monochrome = read_fmt("2H", fp)
        data = list(read_fmt("5h", fp))
        unknown = fp.read()
        return cls(version=version, monochrome=monochrome, data=data, unknown=unknown)  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "2H", self.version, self.monochrome)
        written += write_fmt(fp, "5h", *self.data)
        written += write_bytes(fp, self.unknown)
        return written


@register(Tag.CURVES)
@define(repr=False)
class Curves(BaseElement):
    """
    Curves structure.

    .. py:attribute:: is_map
    .. py:attribute:: version
    .. py:attribute:: count
    .. py:attribute:: data
    .. py:attribute:: extra
    """

    is_map: bool = field(default=False, converter=bool)
    version: int = 0
    count_map: int = 0
    data: list = field(factory=list, converter=list)
    extra: object = None

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        # NOTE: This is highly experimental and unstable.
        is_map, version, count_map = read_fmt("BHI", fp)
        assert version in (1, 4), "Invalid version %d" % (version)

        if version == 1:
            count = bin(count_map).count("1")  # Bitmap = channel index?
        else:
            count = count_map

        if is_map:
            # This lookup format is never documented.
            data = [list(read_fmt("256B", fp)) for _ in range(count)]
        else:
            data = []
            for _ in range(count):
                point_count = read_fmt("H", fp)[0]
                assert 2 <= point_count and point_count <= 19, (
                    "Curves point count not in [2, 19]"
                )
                points = [read_fmt("2H", fp) for i in range(point_count)]
                data.append(points)

        extra = None
        if version == 1:
            try:
                extra = CurvesExtraMarker.read(fp, is_map=is_map)
            except IOError:
                logger.warning("Failed to read CurvesExtraMarker")

        return cls(is_map, version, count_map, data, extra)  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "BHI", self.is_map, self.version, self.count_map)
        if self.is_map:
            written += sum(write_fmt(fp, "256B", *item) for item in self.data)
        else:
            for points in self.data:
                written += write_fmt(fp, "H", len(points))
                written += sum(write_fmt(fp, "2H", *item) for item in points)

        if self.extra is not None:
            written += self.extra.write(fp)  # type: ignore[attr-defined]

        written += write_padding(fp, written, 4)
        return written


@define(repr=False)
class CurvesExtraMarker(ListElement):
    """
    Curves extra marker structure.

    .. py:attribute:: version
    """

    version: int = field(default=4, validator=in_((3, 4)))

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        signature, version, count = read_fmt("4sHI", fp)
        assert signature == b"Crv ", "Invalid signature %r" % (signature)
        items = []
        for _ in range(count):
            items.append(CurvesExtraItem.read(fp, **kwargs))
        return cls(version=version, items=items)  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "4sHI", b"Crv ", self.version, len(self))
        written += sum(item.write(fp) for item in self)
        return written


@define(repr=False)
class CurvesExtraItem(BaseElement):
    """
    Curves extra item.

    .. py:attribute:: channel_id
    .. py:attribute:: points
    """

    channel_id: int = 0
    points: list = field(factory=list, converter=list)

    @classmethod
    def read(cls: type[T], fp: BinaryIO, is_map: bool = False, **kwargs: Any) -> T:
        if is_map:
            channel_id = read_fmt("H", fp)[0]
            points = list(read_fmt("256B", fp))
        else:
            channel_id, point_count = read_fmt("2H", fp)
            points = [read_fmt("2H", fp) for c in range(point_count)]
        return cls(channel_id, points)  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "H", self.channel_id)
        if len(self.points) > 0 and isinstance(self.points[0], int):
            written += write_fmt(fp, "256B", *self.points)
        else:
            written += write_fmt(fp, "H", len(self.points))
            written += sum(write_fmt(fp, "2H", *p) for p in self.points)
        return written


@register(Tag.GRADIENT_MAP)
@define(repr=False)
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

    version: int = field(
        default=1,
        validator=in_(
            (
                1,
                3,
            )
        ),
    )
    is_reversed: int = 0
    is_dithered: int = 0
    name: str = ""
    method: bytes = field(
        default=b"Gcls",
        validator=in_(
            (
                b"Gcls",
                Enum.Linear,
                Enum.Perceptual,
                Key.Smooth,
            )
        ),
    )
    color_stops: list = field(factory=list, converter=list)
    transparency_stops: list = field(factory=list, converter=list)
    expansion: int = field(default=2, validator=in_((2,)))
    interpolation: int = 0
    length: int = field(default=32, validator=in_((32,)))
    mode: int = 0
    random_seed: int = 0
    show_transparency: int = 0
    use_vector_color: int = 0
    roughness: int = 0
    color_model: int = 0
    minimum_color: list = field(factory=list, converter=list)
    maximum_color: list = field(factory=list, converter=list)

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        version, is_reversed, is_dithered = read_fmt("H2B", fp)
        assert version in (1, 3), "Invalid version %s" % (version)
        method = read_fmt("4s", fp)[0] if version == 3 else b"Gcls"
        name = read_unicode_string(fp)
        count = read_fmt("H", fp)[0]
        color_stops = [ColorStop.read(fp) for _ in range(count)]
        count = read_fmt("H", fp)[0]
        transparency_stops = [TransparencyStop.read(fp) for _ in range(count)]
        expansion, interpolation, length, mode = read_fmt("4H", fp)
        assert expansion == 2, "Invalid expansion %d" % (expansion)
        random_seed, show_transparency, use_vector_color = read_fmt("I2H", fp)
        roughness, color_model = read_fmt("IH", fp)
        minimum_color = read_fmt("4H", fp)
        maximum_color = read_fmt("4H", fp)
        read_fmt("2x", fp)  # Dummy?
        return cls(
            version,
            is_reversed,
            is_dithered,
            name,
            method,
            color_stops,
            transparency_stops,
            expansion,
            interpolation,
            length,
            mode,
            random_seed,
            show_transparency,
            use_vector_color,
            roughness,
            color_model,
            minimum_color,
            maximum_color,
        )  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "H2B", self.version, self.is_reversed, self.is_dithered)
        if self.version == 3:
            written += write_fmt(fp, "4s", self.method)
        written += write_unicode_string(fp, self.name)
        written += write_fmt(fp, "H", len(self.color_stops))
        written += sum(stop.write(fp) for stop in self.color_stops)
        written += write_fmt(fp, "H", len(self.transparency_stops))
        written += sum(stop.write(fp) for stop in self.transparency_stops)
        written += write_fmt(
            fp,
            "4HI2HIH",
            self.expansion,
            self.interpolation,
            self.length,
            self.mode,
            self.random_seed,
            self.show_transparency,
            self.use_vector_color,
            self.roughness,
            self.color_model,
        )
        written += write_fmt(fp, "4H", *self.minimum_color)
        written += write_fmt(fp, "4H", *self.maximum_color)
        written += write_fmt(fp, "2x")
        written += write_padding(fp, written, 4)
        return written


@define(repr=False)
class ColorStop(BaseElement):
    """
    ColorStop of GradientMap.

    .. py:attribute:: location
    .. py:attribute:: midpoint
    .. py:attribute:: mode
    .. py:attribute:: color
    """

    location: int = 0
    midpoint: int = 0
    mode: int = 0
    color: tuple = (0,)

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        location, midpoint, mode = read_fmt("2IH", fp)
        color = read_fmt("4H2x", fp)
        return cls(location, midpoint, mode, color)  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(
            fp, "2I5H2x", self.location, self.midpoint, self.mode, *self.color
        )


@define(repr=False)
class TransparencyStop(BaseElement):
    """
    TransparencyStop of GradientMap.

    .. py:attribute:: location
    .. py:attribute:: midpoint
    .. py:attribute:: opacity
    """

    location: int = 0
    midpoint: int = 0
    opacity: int = 0

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        return cls(*read_fmt("2IH", fp))  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "2IH", *astuple(self))


@register(Tag.EXPOSURE)
@define(repr=False)
class Exposure(BaseElement):
    """
    Exposure structure.

    .. py:attribute:: version
    .. py:attribute:: exposure
    .. py:attribute:: offset
    .. py:attribute:: gamma
    """

    version: int = 0
    exposure: float = 0.0
    offset: float = 0.0
    gamma: float = 0.0

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        return cls(*read_fmt("H3f", fp))

    def write(self, fp: BinaryIO, padding: int = 4, **kwargs: Any) -> int:
        written = write_fmt(fp, "H3f", *astuple(self))
        written += write_padding(fp, written, padding)
        return written


@register(Tag.HUE_SATURATION_V4)
@register(Tag.HUE_SATURATION)
@define(repr=False)
class HueSaturation(BaseElement):
    """
    HueSaturation structure.

    .. py:attribute:: version
    .. py:attribute:: enable
    .. py:attribute:: colorization
    .. py:attribute:: master
    .. py:attribute:: items
    """

    version: int = 2
    enable: int = 1
    colorization: tuple = (0,)
    master: tuple = (0,)
    items: list = field(factory=list, converter=list)

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        version, enable = read_fmt("HBx", fp)
        assert version == 2, "Invalid version %d" % (version)
        colorization = read_fmt("3h", fp)
        master = read_fmt("3h", fp)
        items = []
        for _ in range(6):
            range_values = read_fmt("4h", fp)
            settings_values = read_fmt("3h", fp)
            items.append([range_values, settings_values])
        return cls(
            version=version,
            enable=enable,
            colorization=colorization,
            master=master,
            items=items,
        )  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "HBx", self.version, self.enable)
        written += write_fmt(fp, "3h", *self.colorization)
        written += write_fmt(fp, "3h", *self.master)
        for item in self.items:
            written += write_fmt(fp, "4h", *item[0])
            written += write_fmt(fp, "3h", *item[1])
        written += write_padding(fp, written, 4)
        return written


@register(Tag.LEVELS)
@define(repr=False)
class Levels(ListElement):
    """
    List of level records. See :py:class:
    `~psd_tools.psd.adjustments.LevelRecord`.

    .. py:attribute:: version

        Version.

    .. py:attribute:: extra_version

        Version of the extra field.
    """

    version: int = field(default=0, validator=in_((2,)))
    extra_version: Optional[int] = None

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        version = read_fmt("H", fp)[0]
        if version != 2:
            raise ValueError("Invalid version %d" % (version))
        items = [LevelRecord.read(fp) for _ in range(29)]

        extra_version = None
        if is_readable(fp, 6):
            signature, extra_version = read_fmt("4sH", fp)
            if signature == b"ls\x00\x03":
                # Clip Studio Paint has an incorrect signature.
                logger.warning("Invalid signature %r, assuming b'Lvls'." % (signature))
                # Clip Studio Paint seems to incorrectly trim the last record.
                count = extra_version - 1
                extra_version = 3
                logger.debug(
                    "Levels extra version %d, count %d" % (extra_version, count)
                )
            elif signature != b"Lvls":
                raise ValueError("Invalid signature %r" % (signature))
            elif extra_version != 3:
                raise ValueError("Invalid extra version %d" % (extra_version))
            else:
                count = read_fmt("H", fp)[0]

            items += [LevelRecord.read(fp) for _ in range(count - 29)]

        return cls(version=version, extra_version=extra_version, items=items)  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "H", self.version)
        for index in range(29):
            written += self[index].write(fp)

        if self.extra_version is not None:
            written += write_fmt(fp, "4sH", b"Lvls", self.extra_version)
            written += write_fmt(fp, "H", len(self))
            for index in range(29, len(self)):
                written += self[index].write(fp)

        written += write_padding(fp, written, 4)
        return written


@define(repr=False)
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

    input_floor: int = 0
    input_ceiling: int = 0
    output_floor: int = 0
    output_ceiling: int = 0
    gamma: int = 0

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        return cls(*read_fmt("5H", fp))  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "5H", *astuple(self))


@register(Tag.PHOTO_FILTER)
@define(repr=False)
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

    version: int = field(default=0, validator=in_((2, 3)))
    xyz: tuple = (0,)
    color_space: Optional[int] = None
    color_components: Optional[tuple] = None
    density: Optional[int] = None
    luminosity: Optional[int] = None

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        version = read_fmt("H", fp)[0]
        assert version in (2, 3), "Invalid version %d" % (version)
        if version == 3:
            xyz = read_fmt("3I", fp)
            color_space = None
            color_components = None
        else:
            xyz = None
            color_space = read_fmt("H", fp)[0]
            color_components = read_fmt("4H", fp)
        density, luminosity = read_fmt("IB", fp)
        return cls(
            version=version,
            xyz=xyz,
            color_space=color_space,
            color_components=color_components,
            density=density,
            luminosity=luminosity,
        )  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "H", self.version)
        if self.version == 3:
            written += write_fmt(fp, "3I", *self.xyz)  # type: ignore[misc]
        else:
            written += write_fmt(fp, "H4H", self.color_space, *self.color_components)  # type: ignore[misc]
        written += write_fmt(fp, "IB", self.density, self.luminosity)
        written += write_padding(fp, written, 4)
        return written


@register(Tag.SELECTIVE_COLOR)
@define(repr=False)
class SelectiveColor(BaseElement):
    """
    SelectiveColor structure.

    .. py:attribute:: version
    .. py:attribute:: method
    .. py:attribute:: data
    """

    version: int = field(default=1, validator=in_((1,)))
    method: int = 0
    data: list = field(factory=list, converter=list)

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        version, method = read_fmt("2H", fp)
        data = [read_fmt("4h", fp) for i in range(10)]
        return cls(version=version, method=method, data=data)  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "2H", self.version, self.method)
        for plate in self.data:
            written += write_fmt(fp, "4h", *plate)
        return written
