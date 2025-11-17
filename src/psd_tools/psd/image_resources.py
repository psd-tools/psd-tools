"""
Image resources section structure. Image resources are used to store non-pixel
data associated with images, such as pen tool paths or slices.

See :py:class:`~psd_tools.constants.Resource` to check available
resource names.

Example::

    from psd_tools.constants import Resource

    version_info = psd.image_resources.get_data(Resource.VERSION_INFO)


The following resources are plain bytes::

    Resource.OBSOLETE1: 1000
    Resource.MAC_PRINT_MANAGER_INFO: 1001
    Resource.MAC_PAGE_FORMAT_INFO: 1002
    Resource.OBSOLETE2: 1003
    Resource.DISPLAY_INFO_OBSOLETE: 1007
    Resource.BORDER_INFO: 1009
    Resource.DUOTONE_IMAGE_INFO: 1018
    Resource.EFFECTIVE_BW: 1019
    Resource.OBSOLETE3: 1020
    Resource.EPS_OPTIONS: 1021
    Resource.QUICK_MASK_INFO: 1022
    Resource.OBSOLETE4: 1023
    Resource.WORKING_PATH: 1025
    Resource.OBSOLETE5: 1027
    Resource.IPTC_NAA: 1028
    Resource.IMAGE_MODE_RAW: 1029
    Resource.JPEG_QUALITY: 1030
    Resource.URL: 1035
    Resource.COLOR_SAMPLERS_RESOURCE_OBSOLETE: 1038
    Resource.ICC_PROFILE: 1039
    Resource.SPOT_HALFTONE: 1043
    Resource.JUMP_TO_XPEP: 1052
    Resource.EXIF_DATA_1: 1058
    Resource.EXIF_DATA_3: 1059
    Resource.XMP_METADATA: 1060
    Resource.CAPTION_DIGEST: 1061
    Resource.ALTERNATE_DUOTONE_COLORS: 1066
    Resource.ALTERNATE_SPOT_COLORS: 1067
    Resource.HDR_TONING_INFO: 1070
    Resource.PRINT_INFO_CS2: 1071
    Resource.COLOR_SAMPLERS_RESOURCE: 1073
    Resource.DISPLAY_INFO: 1077
    Resource.MAC_NSPRINTINFO: 1084
    Resource.WINDOWS_DEVMODE: 1085
    Resource.PATH_INFO_N: 2000-2999
    Resource.PLUGIN_RESOURCES_N: 4000-4999
    Resource.IMAGE_READY_VARIABLES: 7000
    Resource.IMAGE_READY_DATA_SETS: 7001
    Resource.IMAGE_READY_DEFAULT_SELECTED_STATE: 7002
    Resource.IMAGE_READY_7_ROLLOVER_EXPANDED_STATE: 7003
    Resource.IMAGE_READY_ROLLOVER_EXPANDED_STATE: 7004
    Resource.IMAGE_READY_SAVE_LAYER_SETTINGS: 7005
    Resource.IMAGE_READY_VERSION: 7006
    Resource.LIGHTROOM_WORKFLOW: 8000
"""

import io
import logging
from typing import Any, BinaryIO, Optional, TypeVar

from attrs import define, field, astuple

from psd_tools.constants import PrintScaleStyle, Resource, AlphaChannelMode
from psd_tools.psd.base import (
    BaseElement,
    ByteElement,
    DictElement,
    IntegerElement,
    ListElement,
    NumericElement,
    ShortIntegerElement,
    StringElement,
    ValueElement,
)
from psd_tools.psd.color import Color
from psd_tools.psd.descriptor import DescriptorBlock
from psd_tools.psd.bin_utils import (
    is_readable,
    read_fmt,
    read_length_block,
    read_pascal_string,
    read_unicode_string,
    trimmed_repr,
    write_bytes,
    write_fmt,
    write_length_block,
    write_pascal_string,
    write_unicode_string,
)
from psd_tools.registry import new_registry
from psd_tools.validators import in_
from psd_tools.version import __version__

logger = logging.getLogger(__name__)

T_ImageResources = TypeVar("T_ImageResources", bound="ImageResources")
T_ImageResource = TypeVar("T_ImageResource", bound="ImageResource")

TYPES, register = new_registry()

TYPES.update(
    {
        Resource.BACKGROUND_COLOR: Color,
        Resource.LAYER_COMPS: DescriptorBlock,
        Resource.MEASUREMENT_SCALE: DescriptorBlock,
        Resource.SHEET_DISCLOSURE: DescriptorBlock,
        Resource.TIMELINE_INFO: DescriptorBlock,
        Resource.ONION_SKINS: DescriptorBlock,
        Resource.COUNT_INFO: DescriptorBlock,
        Resource.PRINT_INFO_CS5: DescriptorBlock,
        Resource.PRINT_STYLE: DescriptorBlock,
        Resource.PATH_SELECTION_STATE: DescriptorBlock,
        Resource.ORIGIN_PATH_INFO: DescriptorBlock,
        Resource.AUTO_SAVE_FILE_PATH: StringElement,
        Resource.AUTO_SAVE_FORMAT: StringElement,
        Resource.WORKFLOW_URL: StringElement,
    }
)


@define(repr=False)
class ImageResources(DictElement):
    """
    Image resources section of the PSD file. Dict of
    :py:class:`.ImageResource`.
    """

    def get_data(self, key: Any, default: Any = None) -> Any:
        """
        Get data from the image resources.

        Shortcut for the following::

            if key in image_resources:
                value = tagged_blocks[key].data
        """
        if key in self:
            value = self[key].data
            if isinstance(value, ValueElement):
                return value.value
            else:
                return value
        return default

    @classmethod
    def new(cls: type[T_ImageResources], **kwargs: Any) -> T_ImageResources:
        """
        Create a new default image resouces.

        :return: ImageResources
        """
        return cls(  # type: ignore[arg-type]
            [
                (
                    Resource.VERSION_INFO,
                    ImageResource(
                        key=Resource.VERSION_INFO,
                        data=VersionInfo(  # type: ignore[arg-type]
                            has_composite=True,
                            writer="psd-tools %s" % __version__,
                            reader="psd-tools %s" % __version__,
                        ),
                    ),
                ),
            ]
        )

    @classmethod
    def read(
        cls: type[T_ImageResources],
        fp: BinaryIO,
        encoding: str = "macroman",
        **kwargs: Any,
    ) -> T_ImageResources:
        data = read_length_block(fp)
        logger.debug("reading image resources, len=%d" % (len(data)))
        with io.BytesIO(data) as f:
            return cls._read_body(f, encoding=encoding)

    @classmethod
    def _read_body(
        cls: type[T_ImageResources], fp: BinaryIO, *args: Any, **kwargs: Any
    ) -> T_ImageResources:
        items = []
        while is_readable(fp, 4):
            item = ImageResource.read(fp, *args, **kwargs)
            items.append((item.key, item))
        return cls(items)  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, encoding: str = "macroman", **kwargs: Any) -> int:
        def writer(f: BinaryIO) -> int:
            written = sum(self[key].write(f, encoding) for key in self)
            logger.debug("writing image resources, len=%d" % (written))
            return written

        return write_length_block(fp, writer)

    @classmethod
    def _key_converter(cls, key: Any) -> Any:
        return getattr(key, "value", key)

    def _repr_pretty_(self, p: Any, cycle: bool) -> None:
        if cycle:
            return p.text("{{...}")

        with p.group(2, "{", "}"):
            p.breakable("")
            for idx, key in enumerate(self._items):
                if idx:
                    p.text(",")
                    p.breakable()
                value = self._items[key]
                try:
                    p.text(Resource(key).name)
                except ValueError:
                    p.pretty(key)
                p.text(": ")
                if isinstance(value.data, bytes):
                    p.text(trimmed_repr(value.data))
                else:
                    p.pretty(value.data)
            p.breakable("")


@define(repr=False)
class ImageResource(BaseElement):
    """
    Image resource block.

    .. py:attribute:: signature

        Binary signature, always ``b'8BIM'``.

    .. py:attribute:: key

        Unique identifier for the resource. See
        :py:class:`~psd_tools.constants.Resource`.

    .. py:attribute:: name
    .. py:attribute:: data

        The resource data.
    """

    signature: bytes = field(
        default=b"8BIM",
        repr=False,
        validator=in_({b"8BIM", b"MeSa", b"AgHg", b"PHUT", b"DCSR"}),
    )
    key: int = 1000
    name: str = ""
    data: bytes = field(default=b"", repr=False)

    @classmethod
    def read(
        cls: type[T_ImageResource],
        fp: BinaryIO,
        encoding: str = "macroman",
        **kwargs: Any,
    ) -> T_ImageResource:
        signature, key = read_fmt("4sH", fp)
        try:
            key = Resource(key)
        except ValueError:
            if Resource.is_path_info(key):
                logger.debug("Undefined PATH_INFO found: %d" % (key))
            elif Resource.is_plugin_resource(key):
                logger.debug("Undefined PLUGIN_RESOURCE found: %d" % (key))
            else:
                logger.info("Unknown image resource %d" % (key))
        name = read_pascal_string(fp, encoding, padding=2)
        raw_data = read_length_block(fp, padding=2)
        if key in TYPES:
            data = TYPES[key].frombytes(raw_data)
            # try:
            #     _raw_data = data.tobytes(padding=1)
            #     assert _raw_data == raw_data, '%r vs %r' % (
            #         _raw_data, raw_data
            #     )
            # except AssertionError as e:
            #     logger.error(e)
            #     raise
        else:
            data = raw_data
        return cls(signature, key, name, data)

    def write(self, fp: BinaryIO, encoding: str = "macroman", **kwargs: Any) -> int:
        written = write_fmt(
            fp, "4sH", self.signature, getattr(self.key, "value", self.key)
        )
        written += write_pascal_string(fp, self.name, encoding, 2)

        def writer(f: BinaryIO) -> int:
            if hasattr(self.data, "write"):
                return self.data.write(f, padding=1)
            return write_bytes(f, self.data)

        written += write_length_block(fp, writer, padding=2)
        return written


@register(Resource.ALPHA_IDENTIFIERS)
class AlphaIdentifiers(ListElement):
    """
    List of alpha identifiers.
    """

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "AlphaIdentifiers":
        items = []
        while is_readable(fp, 4):
            items.append(read_fmt("I", fp)[0])
        return cls(items)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return sum(write_fmt(fp, "I", item) for item in self)


@register(Resource.ALPHA_NAMES_PASCAL)
class AlphaNamesPascal(ListElement):
    """
    List of alpha names.
    """

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "AlphaNamesPascal":
        items = []
        while is_readable(fp):
            items.append(read_pascal_string(fp, "macroman", padding=1))
        return cls(items)  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return sum(write_pascal_string(fp, item, padding=1) for item in self)


@register(Resource.ALPHA_NAMES_UNICODE)
class AlphaNamesUnicode(ListElement):
    """
    List of alpha names.
    """

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "AlphaNamesUnicode":
        items = []
        while is_readable(fp):
            items.append(read_unicode_string(fp))
        return cls(items)  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return sum(write_unicode_string(fp, item) for item in self)


@register(Resource.DISPLAY_INFO)
@define(repr=False)
class DisplayInfo(BaseElement):
    """
    DisplayInfo is a list of AlphaChannels
    """

    version: int = 1
    alpha_channels: list = field(factory=list, converter=list)

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "DisplayInfo":
        # ref: https://github.com/MolecularMatters/psd_sdk/blob/311b5c2e3fe04c8cc6a563665e66b19b3fcf8116/src/Psd/PsdParseImageResourcesSection.cpp#L83
        version = read_fmt("I", fp)[0]
        items = []
        while is_readable(fp, 13):
            items.append(AlphaChannel.read(fp))
        return cls(version=version, alpha_channels=items)  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "I", self.version)
        written += sum(item.write(fp) for item in self.alpha_channels)
        return written


@define(repr=False)
class AlphaChannel(BaseElement):
    color_space: int = 0
    c1: int = 0
    c2: int = 0
    c3: int = 0
    c4: int = 0
    opacity: int = 0
    mode: AlphaChannelMode = AlphaChannelMode.ALPHA  # type: ignore[assignment]

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "AlphaChannel":
        vals = read_fmt("6H", fp)
        mode = AlphaChannelMode(read_fmt("B", fp)[0])
        return cls(*vals, mode)  # type: ignore[call-arg]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(
            fp, "6H", self.color_space, self.c1, self.c2, self.c3, self.c4, self.opacity
        )
        written += write_fmt(fp, "B", self.mode)
        return written


@register(Resource.ICC_UNTAGGED_PROFILE)
@register(Resource.COPYRIGHT_FLAG)
@register(Resource.EFFECTS_VISIBLE)
@register(Resource.WATERMARK)
class Byte(ByteElement):
    """
    Byte element.
    """

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "Byte":
        return cls(*read_fmt("B", fp))

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "B", self.value)


@register(Resource.GRID_AND_GUIDES_INFO)
@define(repr=False)
class GridGuidesInfo(BaseElement):
    """
    Grid and guides info structure.

    .. py:attribute: version
    """

    version: int = 1
    horizontal: int = 0
    vertical: int = 0
    data: list = field(factory=list, converter=list)

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "GridGuidesInfo":
        version, horizontal, vertical, count = read_fmt("4I", fp)
        items = []
        for _ in range(count):
            items.append(read_fmt("IB", fp))
        return cls(
            version=version,
            horizontal=horizontal,
            vertical=vertical,
            data=items,  # type: ignore[arg-type]
        )

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(
            fp, "4I", self.version, self.horizontal, self.vertical, len(self.data)
        )
        written += sum(write_fmt(fp, "IB", *item) for item in self.data)
        return written


@register(Resource.COLOR_HALFTONING_INFO)
@register(Resource.DUOTONE_HALFTONING_INFO)
@register(Resource.GRAYSCALE_HALFTONING_INFO)
class HalftoneScreens(ListElement):
    """
    Halftone screens.
    """

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "HalftoneScreens":
        items = []
        while is_readable(fp, 18):
            items.append(HalftoneScreen.read(fp))
        return cls(items)  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return sum(item.write(fp) for item in self)


@define(repr=False)
class HalftoneScreen(BaseElement):
    """
    Halftone screen.

    .. py:attribute:: freq
    .. py:attribute:: unit
    .. py:attribute:: angle
    .. py:attribute:: shape
    .. py:attribute:: use_accurate
    .. py:attribute:: use_printer
    """

    freq: int = 0
    unit: int = 0
    angle: int = 0
    shape: int = 0
    use_accurate: bool = False
    use_printer: bool = False

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "HalftoneScreen":
        freq = float(read_fmt("I", fp)[0]) / 0x10000
        unit = read_fmt("H", fp)[0]
        angle = float(read_fmt("i", fp)[0]) / 0x10000
        shape, use_accurate, use_printer = read_fmt("H4x2?", fp)
        return cls(freq, unit, angle, shape, use_accurate, use_printer)  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "I", int(self.freq * 0x10000))
        written += write_fmt(fp, "H", self.unit)
        written += write_fmt(fp, "i", int(self.angle * 0x10000))
        written += write_fmt(
            fp, "H4x2?", self.shape, self.use_accurate, self.use_printer
        )
        return written


@register(Resource.GLOBAL_ALTITUDE)
@register(Resource.GLOBAL_ANGLE)
@register(Resource.IDS_SEED_NUMBER)
class Integer(IntegerElement):
    """
    Integer element.
    """

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "Integer":
        return cls(*read_fmt("i", fp))

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "i", self.value)


@register(Resource.LAYER_GROUPS_ENABLED_ID)
class LayerGroupEnabledIDs(ListElement):
    """
    Layer group enabled ids.
    """

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "LayerGroupEnabledIDs":
        items = []
        while is_readable(fp, 1):
            items.append(read_fmt("B", fp)[0])
        return cls(items)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return sum(write_fmt(fp, "B", item) for item in self)


@register(Resource.LAYER_GROUP_INFO)
class LayerGroupInfo(ListElement):
    """
    Layer group info list.
    """

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "LayerGroupInfo":
        items = []
        while is_readable(fp, 2):
            items.append(read_fmt("H", fp)[0])
        return cls(items)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return sum(write_fmt(fp, "H", item) for item in self)


@register(Resource.LAYER_SELECTION_IDS)
class LayerSelectionIDs(ListElement):
    """
    Layer selection ids.
    """

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "LayerSelectionIDs":
        count = read_fmt("H", fp)[0]
        return cls(read_fmt("I", fp)[0] for _ in range(count))

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "H", len(self))
        written += sum(write_fmt(fp, "I", item) for item in self)
        return written


@register(Resource.INDEXED_COLOR_TABLE_COUNT)
@register(Resource.LAYER_STATE_INFO)
@register(Resource.TRANSPARENCY_INDEX)
class ShortInteger(ShortIntegerElement):
    """
    Short integer element.
    """

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "ShortInteger":
        return cls(*read_fmt("H", fp))

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "H", self.value)


@register(Resource.CAPTION_PASCAL)
@register(Resource.CLIPPING_PATH_NAME)
class PascalString(ValueElement):
    """
    Pascal string element.
    """

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "PascalString":
        return cls(read_pascal_string(fp, "macroman"))

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_pascal_string(fp, self.value, "macroman", padding=1)  # type: ignore[arg-type]


@register(Resource.PIXEL_ASPECT_RATIO)
@define(repr=False)
class PixelAspectRatio(NumericElement):
    """
    Pixel aspect ratio.

    .. py:attribute: version
    """

    version: int = 1

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "PixelAspectRatio":
        version, value = read_fmt("Id", fp)
        return cls(version=version, value=value)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "Id", self.version, self.value)


@register(Resource.PRINT_FLAGS)
@define(repr=False)
class PrintFlags(BaseElement):
    """
    Print flags.

    .. py:attribute: labels
    .. py:attribute: crop_marks
    .. py:attribute: colorbars
    .. py:attribute: registration_marks
    .. py:attribute: negative
    .. py:attribute: flip
    .. py:attribute: interpolate
    .. py:attribute: caption
    .. py:attribute: print_flags
    """

    labels: bool = False
    crop_marks: bool = False
    colorbars: bool = False
    registration_marks: bool = False
    negative: bool = False
    flip: bool = False
    interpolate: bool = False
    caption: bool = False
    print_flags: Optional[bool] = None  # Not existing for old versions.

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "PrintFlags":
        values = read_fmt("8?", fp)
        print_flags_value = read_fmt("?", fp)[0] if is_readable(fp) else None
        return cls(
            labels=values[0],
            crop_marks=values[1],
            colorbars=values[2],
            registration_marks=values[3],
            negative=values[4],
            flip=values[5],
            interpolate=values[6],
            caption=values[7],
            print_flags=print_flags_value,
        )

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        values = astuple(self)
        if self.print_flags is None:
            values = values[:-1]
        return write_fmt(fp, "%d?" % len(values), *values)


@register(Resource.PRINT_FLAGS_INFO)
@define(repr=False)
class PrintFlagsInfo(BaseElement):
    """
    Print flags info structure.

    .. py:attribute:: version
    .. py:attribute:: center_crop
    .. py:attribute:: bleed_width_value
    .. py:attribute:: bleed_width_scale
    """

    version: int = 0
    center_crop: int = 0
    bleed_width_value: int = 0
    bleed_width_scale: int = 0

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "PrintFlagsInfo":
        return cls(*read_fmt("HBxIH", fp))

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "HBxIH", *astuple(self))


@register(Resource.PRINT_SCALE)
@define(repr=False)
class PrintScale(BaseElement):
    """
    Print scale structure.

    .. py:attribute:: style
    .. py:attribute:: x
    .. py:attribute:: y
    .. py:attribute:: scale
    """

    style: PrintScaleStyle = field(
        default=PrintScaleStyle.CENTERED,
        converter=PrintScaleStyle,
        validator=in_(PrintScaleStyle),
    )
    x: float = 0.0
    y: float = 0.0
    scale: float = 0.0

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "PrintScale":
        return cls(*read_fmt("H3f", fp))

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "H3f", self.style.value, self.x, self.y, self.scale)


@register(Resource.RESOLUTION_INFO)
@define(repr=False)
class ResoulutionInfo(BaseElement):
    """
    Resoulution info structure.

    .. py:attribute:: horizontal
    .. py:attribute:: horizontal_unit
    .. py:attribute:: width_unit
    .. py:attribute:: vertical
    .. py:attribute:: vertical_unit
    .. py:attribute:: height_unit
    """

    horizontal: int = 0
    horizontal_unit: int = 0
    width_unit: int = 0
    vertical: int = 0
    vertical_unit: int = 0
    height_unit: int = 0

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "ResoulutionInfo":
        return cls(*read_fmt("I2HI2H", fp))

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "I2HI2H", *astuple(self))


@register(Resource.SLICES)
@define(repr=False)
class Slices(BaseElement):
    """
    Slices resource.

    .. py:attribute:: version
    .. py:attribute:: data
    """

    version: int = field(default=0, validator=in_((6, 7, 8)))
    data: object = None

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "Slices":
        version = read_fmt("I", fp)[0]
        assert version in (6, 7, 8), "Invalid version %d" % (version)
        if version == 6:
            return cls(version=version, data=SlicesV6.read(fp))
        return cls(version=version, data=DescriptorBlock.read(fp))

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "I", self.version)
        if hasattr(self.data, "write"):
            written += self.data.write(fp, padding=1)
        return written


@define(repr=False)
class SlicesV6(BaseElement):
    """
    Slices resource version 6.

    .. py:attribute:: bbox
    .. py:attribute:: name
    .. py:attribute:: items
    """

    bbox: list = field(factory=lambda: [0, 0, 0, 0], converter=list)
    name: str = ""
    items: list = field(factory=list, converter=list)

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "SlicesV6":
        bbox = read_fmt("4I", fp)
        name = read_unicode_string(fp)
        count = read_fmt("I", fp)[0]
        items = [SliceV6.read(fp) for _ in range(count)]
        return cls(bbox=bbox, name=name, items=items)  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "4I", *self.bbox)
        written += write_unicode_string(fp, self.name)
        written += write_fmt(fp, "I", len(self.items))
        written += sum(item.write(fp) for item in self.items)
        return written


@define(repr=False)
class SliceV6(BaseElement):
    """
    Slice element for version 6.

    .. py:attribute:: slice_id
    .. py:attribute:: group_id
    .. py:attribute:: origin
    .. py:attribute:: associated_id
    .. py:attribute:: name
    .. py:attribute:: slice_type
    .. py:attribute:: bbox
    .. py:attribute:: url
    .. py:attribute:: target
    .. py:attribute:: message
    .. py:attribute:: alt_tag
    .. py:attribute:: cell_is_html
    .. py:attribute:: cell_text
    .. py:attribute:: horizontal
    .. py:attribute:: vertical
    .. py:attribute:: alpha
    .. py:attribute:: red
    .. py:attribute:: green
    .. py:attribute:: blue
    .. py:attribute:: data
    """

    slice_id: int = 0
    group_id: int = 0
    origin: int = 0
    associated_id: Optional[int] = None
    name: str = ""
    slice_type: int = 0
    bbox: list = field(factory=lambda: [0, 0, 0, 0], converter=list)
    url: str = ""
    target: str = ""
    message: str = ""
    alt_tag: str = ""
    cell_is_html: bool = False
    cell_text: str = ""
    horizontal_align: int = 0
    vertical_align: int = 0
    alpha: int = 0
    red: int = 0
    green: int = 0
    blue: int = 0
    data: object = None

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "SliceV6":
        slice_id, group_id, origin = read_fmt("3I", fp)
        associated_id = read_fmt("I", fp)[0] if origin == 1 else None
        name = read_unicode_string(fp)
        slice_type = read_fmt("I", fp)[0]
        bbox = read_fmt("4I", fp)
        url = read_unicode_string(fp)
        target = read_unicode_string(fp)
        message = read_unicode_string(fp)
        alt_tag = read_unicode_string(fp)
        cell_is_html = read_fmt("?", fp)[0]
        cell_text = read_unicode_string(fp)
        horizontal_align, vertical_align = read_fmt("2I", fp)
        alpha, red, green, blue = read_fmt("4B", fp)
        data = None
        if is_readable(fp, 4):
            # There is no easy distinction between descriptor block and
            # next slice v6 item here...
            current_position = fp.tell()
            version = read_fmt("I", fp)[0]
            fp.seek(-4, 1)
            if version == 16:
                try:
                    data = DescriptorBlock.read(fp)
                    if data.classID == b"\x00\x00\x00\x00":
                        data = None
                        raise ValueError(data)
                except ValueError:
                    logger.debug("Failed to read DescriptorBlock")
                    fp.seek(current_position)
        return cls(
            slice_id=slice_id,
            group_id=group_id,
            origin=origin,
            associated_id=associated_id,
            name=name,
            slice_type=slice_type,
            bbox=bbox,
            url=url,
            target=target,
            message=message,
            alt_tag=alt_tag,
            cell_is_html=cell_is_html,
            cell_text=cell_text,
            horizontal_align=horizontal_align,
            vertical_align=vertical_align,
            alpha=alpha,
            red=red,
            green=green,
            blue=blue,
            data=data,
        )

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "3I", self.slice_id, self.group_id, self.origin)
        if self.origin == 1 and self.associated_id is not None:
            written += write_fmt(fp, "I", self.associated_id)
        written += write_unicode_string(fp, self.name, padding=1)
        written += write_fmt(fp, "I", self.slice_type)
        written += write_fmt(fp, "4I", *self.bbox)
        written += write_unicode_string(fp, self.url, padding=1)
        written += write_unicode_string(fp, self.target, padding=1)
        written += write_unicode_string(fp, self.message, padding=1)
        written += write_unicode_string(fp, self.alt_tag, padding=1)
        written += write_fmt(fp, "?", self.cell_is_html)
        written += write_unicode_string(fp, self.cell_text, padding=1)
        written += write_fmt(fp, "2I", self.horizontal_align, self.vertical_align)
        written += write_fmt(fp, "4B", self.alpha, self.red, self.green, self.blue)
        if self.data is not None:
            if hasattr(self.data, "write"):
                written += self.data.write(fp, padding=1)
            elif self.data:
                written += write_bytes(fp, self.data)  # type: ignore[arg-type]
        return written


@register(Resource.THUMBNAIL_RESOURCE)
@define(repr=False)
class ThumbnailResource(BaseElement):
    """
    Thumbnail resource structure.

    .. py:attribute:: fmt
    .. py:attribute:: width
    .. py:attribute:: height
    .. py:attribute:: row
    .. py:attribute:: total_size
    .. py:attribute:: size
    .. py:attribute:: bits
    .. py:attribute:: planes
    .. py:attribute:: data
    """

    _RAW_MODE = "RGB"

    fmt: int = 0
    width: int = 0
    height: int = 0
    row: int = 0
    total_size: int = 0
    bits: int = 0
    planes: int = 0
    data: bytes = b""

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "ThumbnailResource":
        fmt, width, height, row, total_size, size, bits, planes = read_fmt("6I2H", fp)
        data = fp.read(size)
        return cls(fmt, width, height, row, total_size, bits, planes, data)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(
            fp,
            "6I2H",
            self.fmt,
            self.width,
            self.height,
            self.row,
            self.total_size,
            len(self.data),
            self.bits,
            self.planes,
        )
        written += write_bytes(fp, self.data)
        return written


@register(Resource.THUMBNAIL_RESOURCE_PS4)
class ThumbnailResourceV4(ThumbnailResource):
    _RAW_MODE = "BGR"


@register(Resource.COLOR_TRANSFER_FUNCTION)
@register(Resource.DUOTONE_TRANSFER_FUNCTION)
@register(Resource.GRAYSCALE_TRANSFER_FUNCTION)
class TransferFunctions(ListElement):
    """
    Transfer functions.
    """

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "TransferFunctions":
        items = []
        while is_readable(fp, 28):
            items.append(TransferFunction.read(fp))
        return cls(items)  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return sum(item.write(fp) for item in self)


@define(repr=False)
class TransferFunction(BaseElement):
    """
    Transfer function
    """

    curve: list = field(factory=list, converter=list)
    override: bool = False

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "TransferFunction":
        curve = read_fmt("13H", fp)
        override = read_fmt("H", fp)[0]
        return cls(curve=curve, override=override)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "13H", *self.curve)
        written += write_fmt(fp, "H", self.override)
        return written


@register(Resource.URL_LIST)
class URLList(ListElement):
    """
    URL list structure.
    """

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "URLList":
        count = read_fmt("I", fp)[0]
        items = []
        for _ in range(count):
            items.append(URLItem.read(fp))
        return cls(items)  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "I", len(self))
        written += sum(item.write(fp) for item in self)
        return written


@define(repr=False)
class URLItem(BaseElement):
    """
    URL item.

    .. py:attribute:: number
    .. py:attribute:: id
    .. py:attribute:: name
    """

    number: int = 0
    id: int = 0
    name: str = ""

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "URLItem":
        number, id = read_fmt("2I", fp)
        name = read_unicode_string(fp)
        return cls(number, id, name)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "2I", self.number, self.id)
        written += write_unicode_string(fp, self.name)
        return written


@register(Resource.VERSION_INFO)
@define(repr=False)
class VersionInfo(BaseElement):
    """
    Version info structure.

    .. py:attribute:: version
    .. py:attribute:: has_composite
    .. py:attribute:: writer
    .. py:attribute:: reader
    .. py:attribute:: file_version
    """

    version: int = 1
    has_composite: bool = False
    writer: str = ""
    reader: str = ""
    file_version: int = 1

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "VersionInfo":
        version, has_composite = read_fmt("I?", fp)
        writer = read_unicode_string(fp)
        reader = read_unicode_string(fp)
        file_version = read_fmt("I", fp)[0]
        return cls(version, has_composite, writer, reader, file_version)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "I?", self.version, self.has_composite)
        written += write_unicode_string(fp, self.writer)
        written += write_unicode_string(fp, self.reader)
        written += write_fmt(fp, "I", self.file_version)
        return written
