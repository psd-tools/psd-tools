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
from __future__ import absolute_import, unicode_literals
import attr
import logging
import io

from psd_tools.version import __version__
from psd_tools.constants import Resource, PrintScaleStyle
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
from psd_tools.utils import (
    read_fmt, write_fmt, read_pascal_string, write_pascal_string,
    read_length_block, write_length_block, write_bytes, new_registry,
    read_unicode_string, write_unicode_string, is_readable, trimmed_repr
)
from psd_tools.validators import in_

logger = logging.getLogger(__name__)

TYPES, register = new_registry()

TYPES.update({
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
})


@attr.s(repr=False, slots=True)
class ImageResources(DictElement):
    """
    Image resources section of the PSD file. Dict of
    :py:class:`.ImageResource`.
    """

    def get_data(self, key, default=None):
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
    def new(cls, **kwargs):
        """
        Create a new default image resouces.

        :return: ImageResources
        """
        return cls([
            (
                Resource.VERSION_INFO,
                ImageResource(
                    key=Resource.VERSION_INFO,
                    data=VersionInfo(
                        has_composite=True,
                        writer='psd-tools %s' % __version__,
                        reader='psd-tools %s' % __version__,
                    )
                )
            ),
        ])

    @classmethod
    def read(cls, fp, encoding='macroman'):
        data = read_length_block(fp)
        logger.debug('reading image resources, len=%d' % (len(data)))
        with io.BytesIO(data) as f:
            return cls._read_body(f, encoding=encoding)

    @classmethod
    def _read_body(cls, fp, *args, **kwargs):
        items = []
        while is_readable(fp, 4):
            item = ImageResource.read(fp, *args, **kwargs)
            items.append((item.key, item))
        return cls(items)

    def write(self, fp, encoding='macroman'):
        def writer(f):
            written = sum(self[key].write(f, encoding) for key in self)
            logger.debug('writing image resources, len=%d' % (written))
            return written

        return write_length_block(fp, writer)

    @classmethod
    def _key_converter(self, key):
        return getattr(key, 'value', key)

    def _repr_pretty_(self, p, cycle):
        if cycle:
            return '{{...}'

        with p.group(2, '{', '}'):
            p.breakable('')
            for idx, key in enumerate(self._items):
                if idx:
                    p.text(',')
                    p.breakable()
                value = self._items[key]
                try:
                    p.text(Resource(key).name)
                except ValueError:
                    p.pretty(key)
                p.text(': ')
                if isinstance(value.data, bytes):
                    p.text(trimmed_repr(value.data))
                else:
                    p.pretty(value.data)
            p.breakable('')


@attr.s(repr=False, slots=True)
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
    signature = attr.ib(
        default=b'8BIM',
        type=bytes,
        repr=False,
        validator=in_({b'8BIM', b'MeSa', b'AgHg', b'PHUT', b'DCSR'})
    )
    key = attr.ib(default=1000, type=int)
    name = attr.ib(default='', type=str)
    data = attr.ib(default=b'', type=bytes, repr=False)

    @classmethod
    def read(cls, fp, encoding='macroman'):
        signature, key = read_fmt('4sH', fp)
        try:
            key = Resource(key)
        except ValueError:
            if Resource.is_path_info(key):
                logger.debug('Undefined PATH_INFO found: %d' % (key))
            elif Resource.is_plugin_resource(key):
                logger.debug('Undefined PLUGIN_RESOURCE found: %d' % (key))
            else:
                logger.warning('Unknown image resource %d' % (key))
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

    def write(self, fp, encoding='macroman'):
        written = write_fmt(
            fp, '4sH', self.signature, getattr(self.key, 'value', self.key)
        )
        written += write_pascal_string(fp, self.name, encoding, 2)

        def writer(f):
            if hasattr(self.data, 'write'):
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
    def read(cls, fp, **kwargs):
        items = []
        while is_readable(fp, 4):
            items.append(read_fmt('I', fp)[0])
        return cls(items)

    def write(self, fp, **kwargs):
        return sum(write_fmt(fp, 'I', item) for item in self)


@register(Resource.ALPHA_NAMES_PASCAL)
class AlphaNamesPascal(ListElement):
    """
    List of alpha names.
    """

    @classmethod
    def read(cls, fp, **kwargs):
        items = []
        while is_readable(fp):
            items.append(read_pascal_string(fp, 'macroman', padding=1))
        return cls(items)

    def write(self, fp, **kwargs):
        return sum(write_pascal_string(fp, item, padding=1) for item in self)


@register(Resource.ALPHA_NAMES_UNICODE)
class AlphaNamesUnicode(ListElement):
    """
    List of alpha names.
    """

    @classmethod
    def read(cls, fp, **kwargs):
        items = []
        while is_readable(fp):
            items.append(read_unicode_string(fp))
        return cls(items)

    def write(self, fp, **kwargs):
        return sum(write_unicode_string(fp, item) for item in self)


@register(Resource.ICC_UNTAGGED_PROFILE)
@register(Resource.COPYRIGHT_FLAG)
@register(Resource.EFFECTS_VISIBLE)
@register(Resource.WATERMARK)
class Byte(ByteElement):
    """
    Byte element.
    """

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(*read_fmt('B', fp))

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'B', self.value)


@register(Resource.GRID_AND_GUIDES_INFO)
@attr.s(repr=False, slots=True)
class GridGuidesInfo(BaseElement):
    """
    Grid and guides info structure.

    .. py:attribute: version
    """
    version = attr.ib(default=1, type=int)
    horizontal = attr.ib(default=0, type=int)
    vertical = attr.ib(default=0, type=int)
    data = attr.ib(factory=list, converter=list)

    @classmethod
    def read(cls, fp, **kwargs):
        version, horizontal, vertical, count = read_fmt('4I', fp)
        items = []
        for _ in range(count):
            items.append(read_fmt('IB', fp))
        return cls(version, horizontal, vertical, items)

    def write(self, fp, **kwargs):
        written = write_fmt(
            fp, '4I', self.version, self.horizontal, self.vertical,
            len(self.data)
        )
        written += sum(write_fmt(fp, 'IB', *item) for item in self.data)
        return written


@register(Resource.COLOR_HALFTONING_INFO)
@register(Resource.DUOTONE_HALFTONING_INFO)
@register(Resource.GRAYSCALE_HALFTONING_INFO)
class HalftoneScreens(ListElement):
    """
    Halftone screens.
    """

    @classmethod
    def read(cls, fp, **kwargs):
        items = []
        while is_readable(fp, 18):
            items.append(HalftoneScreen.read(fp))
        return cls(items)

    def write(self, fp, **kwargs):
        return sum(item.write(fp) for item in self)


@attr.s(repr=False, slots=True)
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
    freq = attr.ib(default=0, type=int)
    unit = attr.ib(default=0, type=int)
    angle = attr.ib(default=0, type=int)
    shape = attr.ib(default=0, type=int)
    use_accurate = attr.ib(default=False, type=bool)
    use_printer = attr.ib(default=False, type=bool)

    @classmethod
    def read(cls, fp, **kwargs):
        freq = float(read_fmt('I', fp)[0]) / 0x10000
        unit = read_fmt('H', fp)[0]
        angle = float(read_fmt('i', fp)[0]) / 0x10000
        shape, use_accurate, use_printer = read_fmt('H4x2?', fp)
        return cls(freq, unit, angle, shape, use_accurate, use_printer)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'I', int(self.freq * 0x10000))
        written += write_fmt(fp, 'H', self.unit)
        written += write_fmt(fp, 'i', int(self.angle * 0x10000))
        written += write_fmt(
            fp, 'H4x2?', self.shape, self.use_accurate, self.use_printer
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
    def read(cls, fp, **kwargs):
        return cls(*read_fmt('i', fp))

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'i', self.value)


@register(Resource.LAYER_GROUPS_ENABLED_ID)
class LayerGroupEnabledIDs(ListElement):
    """
    Layer group enabled ids.
    """

    @classmethod
    def read(cls, fp, **kwargs):
        items = []
        while is_readable(fp, 1):
            items.append(read_fmt('B', fp)[0])
        return cls(items)

    def write(self, fp, **kwargs):
        return sum(write_fmt(fp, 'B', item) for item in self)


@register(Resource.LAYER_GROUP_INFO)
class LayerGroupInfo(ListElement):
    """
    Layer group info list.
    """

    @classmethod
    def read(cls, fp, **kwargs):
        items = []
        while is_readable(fp, 2):
            items.append(read_fmt('H', fp)[0])
        return cls(items)

    def write(self, fp, **kwargs):
        return sum(write_fmt(fp, 'H', item) for item in self)


@register(Resource.LAYER_SELECTION_IDS)
class LayerSelectionIDs(ListElement):
    """
    Layer selection ids.
    """

    @classmethod
    def read(cls, fp, **kwargs):
        count = read_fmt('H', fp)[0]
        return cls(read_fmt('I', fp)[0] for _ in range(count))

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'H', len(self))
        written += sum(write_fmt(fp, 'I', item) for item in self)
        return written


@register(Resource.INDEXED_COLOR_TABLE_COUNT)
@register(Resource.LAYER_STATE_INFO)
@register(Resource.TRANSPARENCY_INDEX)
class ShortInteger(ShortIntegerElement):
    """
    Short integer element.
    """

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(*read_fmt('H', fp))

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'H', self.value)


@register(Resource.CAPTION_PASCAL)
@register(Resource.CLIPPING_PATH_NAME)
class PascalString(ValueElement):
    """
    Pascal string element.
    """

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(read_pascal_string(fp, 'macroman'))

    def write(self, fp, **kwargs):
        return write_pascal_string(fp, self.value, 'macroman', padding=1)


@register(Resource.PIXEL_ASPECT_RATIO)
@attr.s(repr=False, slots=True)
class PixelAspectRatio(NumericElement):
    """
    Pixel aspect ratio.

    .. py:attribute: version
    """
    version = attr.ib(default=1, type=int)

    @classmethod
    def read(cls, fp, **kwargs):
        version, value = read_fmt('Id', fp)
        return cls(version=version, value=value)

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'Id', self.version, self.value)


@register(Resource.PRINT_FLAGS)
@attr.s(repr=False, slots=True)
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
    labels = attr.ib(default=False, type=bool)
    crop_marks = attr.ib(default=False, type=bool)
    colorbars = attr.ib(default=False, type=bool)
    registration_marks = attr.ib(default=False, type=bool)
    negative = attr.ib(default=False, type=bool)
    flip = attr.ib(default=False, type=bool)
    interpolate = attr.ib(default=False, type=bool)
    caption = attr.ib(default=False, type=bool)
    print_flags = attr.ib(default=None)  # Not existing for old versions.

    @classmethod
    def read(cls, fp, **kwargs):
        values = read_fmt('8?', fp)
        if is_readable(fp):
            values += read_fmt('?', fp)
        return cls(*values)

    def write(self, fp, **kwargs):
        values = attr.astuple(self)
        if self.print_flags is None:
            values = values[:-1]
        return write_fmt(fp, '%d?' % len(values), *values)


@register(Resource.PRINT_FLAGS_INFO)
@attr.s(repr=False, slots=True)
class PrintFlagsInfo(BaseElement):
    """
    Print flags info structure.

    .. py:attribute:: version
    .. py:attribute:: center_crop
    .. py:attribute:: bleed_width_value
    .. py:attribute:: bleed_width_scale
    """
    version = attr.ib(default=0, type=int)
    center_crop = attr.ib(default=0, type=int)
    bleed_width_value = attr.ib(default=0, type=int)
    bleed_width_scale = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(*read_fmt('HBxIH', fp))

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'HBxIH', *attr.astuple(self))


@register(Resource.PRINT_SCALE)
@attr.s(repr=False, slots=True)
class PrintScale(BaseElement):
    """
    Print scale structure.

    .. py:attribute:: style
    .. py:attribute:: x
    .. py:attribute:: y
    .. py:attribute:: scale
    """
    style = attr.ib(
        default=PrintScaleStyle.CENTERED,
        converter=PrintScaleStyle,
        validator=in_(PrintScaleStyle)
    )
    x = attr.ib(default=0., type=float)
    y = attr.ib(default=0., type=float)
    scale = attr.ib(default=0., type=float)

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(*read_fmt('H3f', fp))

    def write(self, fp, **kwargs):
        return write_fmt(
            fp, 'H3f', self.style.value, self.x, self.y, self.scale
        )


@register(Resource.RESOLUTION_INFO)
@attr.s(repr=False, slots=True)
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
    horizontal = attr.ib(default=0, type=int)
    horizontal_unit = attr.ib(default=0, type=int)
    width_unit = attr.ib(default=0, type=int)
    vertical = attr.ib(default=0, type=int)
    vertical_unit = attr.ib(default=0, type=int)
    height_unit = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(*read_fmt('I2HI2H', fp))

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'I2HI2H', *attr.astuple(self))


@register(Resource.SLICES)
@attr.s(repr=False, slots=True)
class Slices(BaseElement):
    """
    Slices resource.

    .. py:attribute:: version
    .. py:attribute:: data
    """
    version = attr.ib(default=0, type=int, validator=in_((6, 7, 8)))
    data = attr.ib(default=None)

    @classmethod
    def read(cls, fp, **kwargs):
        version = read_fmt('I', fp)[0]
        assert version in (6, 7, 8), 'Invalid version %d' % (version)
        if version == 6:
            return cls(version=version, data=SlicesV6.read(fp))
        return cls(version=version, data=DescriptorBlock.read(fp))

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'I', self.version)
        written += self.data.write(fp, padding=1)
        return written


@attr.s(repr=False, slots=True)
class SlicesV6(BaseElement):
    """
    Slices resource version 6.

    .. py:attribute:: bbox
    .. py:attribute:: name
    .. py:attribute:: items
    """
    bbox = attr.ib(factory=lambda: [0, 0, 0, 0], converter=list)
    name = attr.ib(default='', type=str)
    items = attr.ib(factory=list, converter=list)

    @classmethod
    def read(cls, fp):
        bbox = read_fmt('4I', fp)
        name = read_unicode_string(fp)
        count = read_fmt('I', fp)[0]
        items = [SliceV6.read(fp) for _ in range(count)]
        return cls(bbox, name, items)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, '4I', *self.bbox)
        written += write_unicode_string(fp, self.name)
        written += write_fmt(fp, 'I', len(self.items))
        written += sum(item.write(fp) for item in self.items)
        return written


@attr.s(repr=False)
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
    slice_id = attr.ib(default=0, type=int)
    group_id = attr.ib(default=0, type=int)
    origin = attr.ib(default=0, type=int)
    associated_id = attr.ib(default=None)
    name = attr.ib(default='', type=str)
    slice_type = attr.ib(default=0, type=int)
    bbox = attr.ib(factory=lambda: [0, 0, 0, 0], converter=list)
    url = attr.ib(default='', type=str)
    target = attr.ib(default='', type=str)
    message = attr.ib(default='', type=str)
    alt_tag = attr.ib(default='', type=str)
    cell_is_html = attr.ib(default=False, type=bool)
    cell_text = attr.ib(default='', type=str)
    horizontal_align = attr.ib(default=0, type=int)
    vertical_align = attr.ib(default=0, type=int)
    alpha = attr.ib(default=0, type=int)
    red = attr.ib(default=0, type=int)
    green = attr.ib(default=0, type=int)
    blue = attr.ib(default=0, type=int)
    data = attr.ib(default=None)

    @classmethod
    def read(cls, fp):
        slice_id, group_id, origin = read_fmt('3I', fp)
        associated_id = read_fmt('I', fp)[0] if origin == 1 else None
        name = read_unicode_string(fp)
        slice_type = read_fmt('I', fp)[0]
        bbox = read_fmt('4I', fp)
        url = read_unicode_string(fp)
        target = read_unicode_string(fp)
        message = read_unicode_string(fp)
        alt_tag = read_unicode_string(fp)
        cell_is_html = read_fmt('?', fp)[0]
        cell_text = read_unicode_string(fp)
        horizontal_align, vertical_align = read_fmt('2I', fp)
        alpha, red, green, blue = read_fmt('4B', fp)
        data = None
        if is_readable(fp, 4):
            # There is no easy distinction between descriptor block and
            # next slice v6 item here...
            current_position = fp.tell()
            version = read_fmt('I', fp)[0]
            fp.seek(-4, 1)
            if version == 16:
                try:
                    data = DescriptorBlock.read(fp)
                    if data.classID == b'\x00\x00\x00\x00':
                        data = None
                        raise ValueError(data)
                except ValueError:
                    logger.debug('Failed to read DescriptorBlock')
                    fp.seek(current_position)
        return cls(
            slice_id, group_id, origin, associated_id, name, slice_type, bbox,
            url, target, message, alt_tag, cell_is_html, cell_text,
            horizontal_align, vertical_align, alpha, red, green, blue, data
        )

    def write(self, fp):
        written = write_fmt(
            fp, '3I', self.slice_id, self.group_id, self.origin
        )
        if self.origin == 1 and self.associated_id is not None:
            written += write_fmt(fp, 'I', self.associated_id)
        written += write_unicode_string(fp, self.name, padding=1)
        written += write_fmt(fp, 'I', self.slice_type)
        written += write_fmt(fp, '4I', *self.bbox)
        written += write_unicode_string(fp, self.url, padding=1)
        written += write_unicode_string(fp, self.target, padding=1)
        written += write_unicode_string(fp, self.message, padding=1)
        written += write_unicode_string(fp, self.alt_tag, padding=1)
        written += write_fmt(fp, '?', self.cell_is_html)
        written += write_unicode_string(fp, self.cell_text, padding=1)
        written += write_fmt(
            fp, '2I', self.horizontal_align, self.vertical_align
        )
        written += write_fmt(
            fp, '4B', self.alpha, self.red, self.green, self.blue
        )
        if self.data is not None:
            if hasattr(self.data, 'write'):
                written += self.data.write(fp, padding=1)
            elif self.data:
                written += write_bytes(fp, self.data)
        return written


@register(Resource.THUMBNAIL_RESOURCE)
@attr.s(repr=False)
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
    _RAW_MODE = 'RGB'

    fmt = attr.ib(default=0, type=int)
    width = attr.ib(default=0, type=int)
    height = attr.ib(default=0, type=int)
    row = attr.ib(default=0, type=int)
    total_size = attr.ib(default=0, type=int)
    bits = attr.ib(default=0, type=int)
    planes = attr.ib(default=0, type=int)
    data = attr.ib(default=b'', type=bytes)

    @classmethod
    def read(cls, fp, **kwargs):
        fmt, width, height, row, total_size, size, bits, planes = read_fmt(
            '6I2H', fp
        )
        data = fp.read(size)
        return cls(fmt, width, height, row, total_size, bits, planes, data)

    def write(self, fp, **kwargs):
        written = write_fmt(
            fp, '6I2H', self.fmt, self.width, self.height, self.row,
            self.total_size, len(self.data), self.bits, self.planes
        )
        written += write_bytes(fp, self.data)
        return written

    def topil(self):
        """
        Get PIL Image.

        :return: PIL Image object.
        """
        from PIL import Image
        if self.fmt == 1:
            with io.BytesIO(self.data) as f:
                image = Image.open(f)
                image.load()
        else:
            image = Image.frombytes(
                'RGB', (self.width, self.height), self.data, 'raw',
                self._RAW_MODE, self.row
            )
        return image


@register(Resource.THUMBNAIL_RESOURCE_PS4)
class ThumbnailResourceV4(ThumbnailResource):
    _RAW_MODE = 'BGR'


@register(Resource.COLOR_TRANSFER_FUNCTION)
@register(Resource.DUOTONE_TRANSFER_FUNCTION)
@register(Resource.GRAYSCALE_TRANSFER_FUNCTION)
class TransferFunctions(ListElement):
    """
    Transfer functions.
    """

    @classmethod
    def read(cls, fp, **kwargs):
        items = []
        while is_readable(fp, 28):
            items.append(TransferFunction.read(fp))
        return cls(items)

    def write(self, fp, **kwargs):
        return sum(item.write(fp) for item in self)


@attr.s(repr=False)
class TransferFunction(BaseElement):
    """
    Transfer function
    """
    curve = attr.ib(factory=list, converter=list)
    override = attr.ib(default=False, type=bool)

    @classmethod
    def read(cls, fp, **kwargs):
        curve = read_fmt('13H', fp)
        override = read_fmt('H', fp)[0]
        return cls(curve, override)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, '13H', *self.curve)
        written += write_fmt(fp, 'H', self.override)
        return written


@register(Resource.URL_LIST)
class URLList(ListElement):
    """
    URL list structure.
    """

    @classmethod
    def read(cls, fp, **kwargs):
        count = read_fmt('I', fp)[0]
        items = []
        for _ in range(count):
            items.append(URLItem.read(fp))
        return cls(items)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'I', len(self))
        written += sum(item.write(fp) for item in self)
        return written


@attr.s(repr=False)
class URLItem(BaseElement):
    """
    URL item.

    .. py:attribute:: number
    .. py:attribute:: id
    .. py:attribute:: name
    """
    number = attr.ib(default=0, type=int)
    id = attr.ib(default=0, type=int)
    name = attr.ib(default='', type=str)

    @classmethod
    def read(cls, fp):
        number, id = read_fmt('2I', fp)
        name = read_unicode_string(fp)
        return cls(number, id, name)

    def write(self, fp):
        written = write_fmt(fp, '2I', self.number, self.id)
        written += write_unicode_string(fp, self.name)
        return written


@register(Resource.VERSION_INFO)
@attr.s(repr=False)
class VersionInfo(BaseElement):
    """
    Version info structure.

    .. py:attribute:: version
    .. py:attribute:: has_composite
    .. py:attribute:: writer
    .. py:attribute:: reader
    .. py:attribute:: file_version
    """
    version = attr.ib(default=1, type=int)
    has_composite = attr.ib(default=False, type=bool)
    writer = attr.ib(default='', type=str)
    reader = attr.ib(default='', type=str)
    file_version = attr.ib(default=1, type=int)

    @classmethod
    def read(cls, fp, **kwargs):
        version, has_composite = read_fmt('I?', fp)
        writer = read_unicode_string(fp)
        reader = read_unicode_string(fp)
        file_version = read_fmt('I', fp)[0]
        return cls(version, has_composite, writer, reader, file_version)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'I?', self.version, self.has_composite)
        written += write_unicode_string(fp, self.writer)
        written += write_unicode_string(fp, self.reader)
        written += write_fmt(fp, 'I', self.file_version)
        return written
