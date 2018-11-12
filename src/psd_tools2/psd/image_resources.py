"""
Image resources section structure. Image resources are used to store non-pixel
data associated with images, such as pen tool paths.
"""
from __future__ import absolute_import, unicode_literals
import attr
import logging
import io

from psd_tools2.constants import ImageResourceID, PrintScaleStyle
from psd_tools2.psd.base import (
    BaseElement, BooleanElement, ByteElement, DictElement, IntegerElement,
    ListElement, NumericElement, ShortIntegerElement, ValueElement,
)
from psd_tools2.psd.color import Color
from psd_tools2.psd.descriptor import DescriptorBlock
from psd_tools2.utils import (
    read_fmt, write_fmt, read_pascal_string, write_pascal_string,
    read_length_block, write_length_block, write_bytes, new_registry,
    read_unicode_string, write_unicode_string, is_readable, trimmed_repr
)
from psd_tools2.validators import in_


logger = logging.getLogger(__name__)

TYPES, register = new_registry()

TYPES.update({
    ImageResourceID.BACKGROUND_COLOR: Color,
    ImageResourceID.LAYER_COMPS: DescriptorBlock,
    ImageResourceID.MEASUREMENT_SCALE: DescriptorBlock,
    ImageResourceID.SHEET_DISCLOSURE: DescriptorBlock,
    ImageResourceID.TIMELINE_INFO: DescriptorBlock,
    ImageResourceID.ONION_SKINS: DescriptorBlock,
    ImageResourceID.COUNT_INFO: DescriptorBlock,
    ImageResourceID.PRINT_INFO_CS5: DescriptorBlock,
    ImageResourceID.PRINT_STYLE: DescriptorBlock,
    ImageResourceID.PATH_SELECTION_STATE: DescriptorBlock,
    ImageResourceID.ORIGIN_PATH_INFO: DescriptorBlock,
})


@attr.s(repr=False)
class ImageResources(DictElement):
    """
    Image resources section of the PSD file. Dict of
    :py:class:`.ImageResource`.
    """
    @classmethod
    def read(cls, fp, encoding='macroman'):
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: :py:class:`.ImageResources`
        """
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
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        def writer(f):
            written = sum(self[key].write(f, encoding) for key in self)
            logger.debug('writing image resources, len=%d' % (written))
            return written

        return write_length_block(fp, writer)

    def _repr_pretty_(self, p, cycle):
        if cycle:
            return "{{...}".format(name=self.__class__.__name__)

        with p.group(2, '{{'.format(name=self.__class__.__name__), '}'):
            p.breakable('')
            for idx, key in enumerate(self._items):
                if idx:
                    p.text(',')
                    p.breakable()
                value = self._items[key]
                if hasattr(key, 'name'):
                    p.text(key.name)
                else:
                    p.pretty(key)
                p.text(': ')
                if isinstance(value.data, bytes):
                    p.text(trimmed_repr(value.data))
                else:
                    p.pretty(value.data)
            p.breakable('')


@attr.s
class ImageResource(BaseElement):
    """
    Image resource block.

    .. py:attribute:: signature

        Binary signature, always ``b'8BIM'``.

    .. py:attribute:: key

        Unique identifier for the resource. See
        :py:class:`~psd_tools2.constants.ImageResourceID`.

    .. py:attribute:: name
    .. py:attribute:: data

        The resource data.
    """
    signature = attr.ib(default=b'8BIM', type=bytes, repr=False,
                        validator=in_((b'8BIM', b'MeSa')))
    key = attr.ib(default=1000, type=int)
    name = attr.ib(default='', type=str)
    data = attr.ib(default=b'', type=bytes, repr=False)

    @classmethod
    def read(cls, fp, encoding='macroman'):
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: :py:class:`.ImageResource`
        """
        signature, key = read_fmt('4sH', fp)
        try:
            key = ImageResourceID(key)
        except ValueError:
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
        """Write the element to a file-like object.

        :param fp: file-like object
        :rtype: int
        """
        written = write_fmt(fp, '4sH', self.signature,
                            getattr(self.key, 'value', self.key))
        written += write_pascal_string(fp, self.name, encoding, 2)

        def writer(f):
            if hasattr(self.data, 'write'):
                return self.data.write(f, padding=1)
            return write_bytes(f, self.data)

        written += write_length_block(fp, writer, padding=2)
        return written


@register(ImageResourceID.COPYRIGHT_FLAG)
class Byte(ByteElement):
    """
    Byte element.
    """
    @classmethod
    def read(cls, fp, **kwargs):
        return cls(*read_fmt('B', fp))

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'B', self.value)


@register(ImageResourceID.GRID_AND_GUIDES_INFO)
@attr.s
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
        written = write_fmt(fp, '4I', self.version, self.horizontal,
                            self.vertical, len(self.data))
        written += sum(write_fmt(fp, 'IB', *item) for item in self.data)
        return written


@register(ImageResourceID.GLOBAL_ALTITUDE)
@register(ImageResourceID.GLOBAL_ANGLE)
@register(ImageResourceID.IDS_SEED_NUMBER)
class Integer(IntegerElement):
    """
    Integer element.
    """
    @classmethod
    def read(cls, fp, **kwargs):
        return cls(*read_fmt('i', fp))

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'i', self.value)


@register(ImageResourceID.LAYER_GROUPS_ENABLED_ID)
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


@register(ImageResourceID.LAYER_GROUP_INFO)
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


@register(ImageResourceID.LAYER_SELECTION_IDS)
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


@register(ImageResourceID.INDEXED_COLOR_TABLE_COUNT)
@register(ImageResourceID.LAYER_STATE_INFO)
@register(ImageResourceID.TRANSPARENCY_INDEX)
class ShortInteger(ShortIntegerElement):
    """
    Short integer element.
    """
    @classmethod
    def read(cls, fp, **kwargs):
        return cls(*read_fmt('H', fp))

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'H', self.value)


@register(ImageResourceID.ALPHA_NAMES_UNICODE)
@register(ImageResourceID.AUTO_SAVE_FILE_PATH)
@register(ImageResourceID.AUTO_SAVE_FORMAT)
@register(ImageResourceID.WORKFLOW_URL)
class String(ValueElement):
    """
    String element.
    """
    @classmethod
    def read(cls, fp, **kwargs):
        return cls(read_unicode_string(fp))

    def write(self, fp, **kwargs):
        return write_unicode_string(fp, self.value, padding=1)


@register(ImageResourceID.CAPTION_PASCAL)
@register(ImageResourceID.CLIPPING_PATH_NAME)
class PascalString(ValueElement):
    """
    Pascal string element.
    """
    @classmethod
    def read(cls, fp, **kwargs):
        return cls(read_pascal_string(fp, 'macroman'))

    def write(self, fp, **kwargs):
        return write_pascal_string(fp, 'macroman', padding=1)


@register(ImageResourceID.PIXEL_ASPECT_RATIO)
@attr.s
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


@register(ImageResourceID.PRINT_FLAGS)
@attr.s
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
    print_flags = attr.ib(default=False, type=bool)

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(*read_fmt('9?', fp))

    def write(self, fp, **kwargs):
        return write_fmt(fp, '9?', *attr.astuple(self))


@register(ImageResourceID.PRINT_FLAGS_INFO)
@attr.s
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


@register(ImageResourceID.PRINT_SCALE)
@attr.s
class PrintScale(BaseElement):
    """
    Print scale structure.

    .. py:attribute:: style
    .. py:attribute:: x
    .. py:attribute:: y
    .. py:attribute:: scale
    """
    style = attr.ib(default=PrintScaleStyle.CENTERED,
                    converter=PrintScaleStyle,
                    validator=in_(PrintScaleStyle))
    x = attr.ib(default=0., type=float)
    y = attr.ib(default=0., type=float)
    scale = attr.ib(default=0., type=float)

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(*read_fmt('H3f', fp))

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'H3f', self.style.value, self.x, self.y,
                         self.scale)


@register(ImageResourceID.RESOLUTION_INFO)
@attr.s
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


@register(ImageResourceID.VERSION_INFO)
@attr.s
class VersionInfo(BaseElement):
    """
    Version info structure.

    .. py:attribute:: version
    .. py:attribute:: has_composite
    .. py:attribute:: writer
    .. py:attribute:: reader
    .. py:attribute:: file_version
    """
    version = attr.ib(default=0, type=int)
    has_composite = attr.ib(default=False, type=bool)
    writer = attr.ib(default='', type=str)
    reader = attr.ib(default='', type=str)
    file_version = attr.ib(default=0, type=int)

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
