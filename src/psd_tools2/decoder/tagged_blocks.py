"""
Tagged block data structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import io
import logging
from collections import OrderedDict

from psd_tools2.decoder.base import (
    BaseElement, ValueElement, ListElement, DictElement
)
from psd_tools2.decoder.descriptor import Descriptor
from psd_tools2.constants import (
    BlendMode, ColorMode, ColorSpaceID, SectionDivider, TaggedBlockID
)
from psd_tools2.validators import in_
from psd_tools2.utils import (
    read_fmt, write_fmt, read_length_block, write_length_block, is_readable,
    write_bytes, read_unicode_string, write_unicode_string, write_padding,
    read_pascal_string, write_pascal_string, trimmed_repr
)

logger = logging.getLogger(__name__)


TYPES = {}


def register(key):
    def _register(cls):
        TYPES[key] = cls
        return cls
    return _register


@attr.s(repr=False)
class TaggedBlocks(DictElement):
    """
    List of tagged blocks.

    .. py:attribute:: items
    """
    items = attr.ib(factory=OrderedDict, converter=OrderedDict)

    @classmethod
    def read(cls, fp, version=1, padding=1):
        """Read the element from a file-like object.

        :param fp: file-like object
        :param version: psd file version
        :rtype: :py:class:`.TaggedBlocks`
        """
        items = []
        while is_readable(fp, 8):  # len(signature) + len(key) = 8
            block = TaggedBlock.read(fp, version, padding)
            if block is None:
                break
            items.append((block.key, block))
        return cls(items)

    def _repr_pretty_(self, p, cycle):
        if cycle:
            return "{name}[...]".format(name=self.__class__.__name__)

        with p.group(2, '{name}{{'.format(name=self.__class__.__name__), '}'):
            p.breakable('')
            for idx, key in enumerate(self.items):
                if idx:
                    p.text(',')
                    p.breakable()
                value = self.items[key]
                p.pretty(key.name)
                p.text(': ')
                value = value.data
                if isinstance(value, bytes):
                    value = trimmed_repr(value)
                p.pretty(value)
            p.breakable('')


@attr.s
class TaggedBlock(BaseElement):
    """
    Layer tagged block with extra info.

    .. py:attribute:: key

        4-character code. See :py:class:`~psd_tools2.constants.TaggedBlock`

    .. py:attribute:: data

        Data.
    """
    _SIGNATURES = (b'8BIM', b'8B64')
    _BIG_KEYS = {
        TaggedBlockID.USER_MASK,
        TaggedBlockID.LAYER_16,
        TaggedBlockID.LAYER_32,
        TaggedBlockID.LAYER,
        TaggedBlockID.SAVING_MERGED_TRANSPARENCY16,
        TaggedBlockID.SAVING_MERGED_TRANSPARENCY32,
        TaggedBlockID.SAVING_MERGED_TRANSPARENCY,
        TaggedBlockID.SAVING_MERGED_TRANSPARENCY16,
        TaggedBlockID.ALPHA,
        TaggedBlockID.FILTER_MASK,
        TaggedBlockID.LINKED_LAYER2,
        TaggedBlockID.LINKED_LAYER_EXTERNAL,
        TaggedBlockID.FILTER_EFFECTS1,
        TaggedBlockID.FILTER_EFFECTS2,
        TaggedBlockID.PIXEL_SOURCE_DATA2,
        TaggedBlockID.UNICODE_PATH_NAME,
    }

    signature = attr.ib(default=b'8BIM', repr=False,
                        validator=in_(_SIGNATURES))
    key = attr.ib(default=b'')
    data = attr.ib(default=b'', repr=True)

    @classmethod
    def read(cls, fp, version=1, padding=1):
        """Read the element from a file-like object.

        :param fp: file-like object
        :param version: psd file version
        :rtype: :py:class:`.TaggedBlock`
        """
        signature = read_fmt('4s', fp)[0]
        if signature not in cls._SIGNATURES:
            logger.warning('Invalid signature (%r)' % (signature))
            fp.seek(-4, 1)
            return None

        key = read_fmt('4s', fp)[0]
        try:
            key = TaggedBlockID(key)
        except ValueError:
            logger.warning('Unknown key: %r' % (key))

        fmt = cls._length_format(key, version)
        data = read_length_block(fp, fmt=fmt, padding=padding)
        kls = TYPES.get(key)
        # logger.debug('%s %r' % (key, trimmed_repr(data)))
        if kls:
            # try:
            data = kls.frombytes(data)
            # except (ValueError,):  # AssertionError also.
            #     logger.warning('Failed to read tagged block: %r' % (key))
        else:
            logger.warning('Unknown tagged block: %r, %r' % (
                key, trimmed_repr(data))
            )
        return cls(signature, key, data)

    def write(self, fp, version=1, padding=1):
        """Write the element to a file-like object.

        :param fp: file-like object
        :param version: psd file version
        """
        key = self.key if isinstance(self.key, bytes) else self.key.value
        written = write_fmt(fp, '4s4s', self.signature, key)

        def writer(f):
            if hasattr(self.data, 'write'):
                # It seems padding size applies at the block level here.
                inner_padding = 1 if padding == 4 else 4
                return self.data.write(f, padding=inner_padding)
            return write_bytes(f, self.data)

        fmt = self._length_format(self.key, version)
        written += write_length_block(fp, writer, fmt=fmt, padding=padding)
        return written

    @classmethod
    def _length_format(cls, key, version):
        return ('I', 'Q')[int(version == 2 and key in cls._BIG_KEYS)]


@register(TaggedBlockID.LAYER_ID)
@register(TaggedBlockID.LAYER_VERSION)
@register(TaggedBlockID.USING_ALIGNED_RENDERING)
@attr.s(repr=False)
class Integer(ValueElement):
    """
    Integer structure.

    .. py:attribute:: value
    """
    value = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(read_fmt('I', fp)[0])

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'I', self.value)

    def __int__(self):
        return self.value

    def __index__(self):
        return self.value


@register(TaggedBlockID.POSTERIZE)
@register(TaggedBlockID.THRESHOLD)
@attr.s(repr=False)
class ShortInteger(ValueElement):
    """
    Short integer structure.

    .. py:attribute:: value
    """
    value = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(read_fmt('H2x', fp)[0])

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'H2x', self.value)

    def __int__(self):
        return self.value

    def __index__(self):
        return self.value


@register(TaggedBlockID.BLEND_CLIPPING_ELEMENTS)
@register(TaggedBlockID.BLEND_INTERIOR_ELEMENTS)
@register(TaggedBlockID.KNOCKOUT_SETTING)
@register(TaggedBlockID.BLEND_FILL_OPACITY)
@register(TaggedBlockID.LAYER_MASK_AS_GLOBAL_MASK)
@register(TaggedBlockID.TRANSPARENCY_SHAPES_LAYER)
@register(TaggedBlockID.VECTOR_MASK_AS_GLOBAL_MASK)
@attr.s(repr=False)
class Byte(ValueElement):
    """
    Byte structure.

    .. py:attribute:: value
    """
    value = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(read_fmt('B3x', fp)[0])

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'B3x', self.value)

    def __int__(self):
        return self.value

    def __index__(self):
        return self.value


@register(TaggedBlockID.FOREIGN_EFFECT_ID)
@register(TaggedBlockID.LAYER_NAME_SOURCE_SETTING)
@attr.s(repr=False)
class Bytes(ValueElement):
    """
    Bytes structure.

    .. py:attribute:: value
    """
    value = attr.ib(default=b'\x00\x00\x00\x00', type=bytes)

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(fp.read(4))

    def write(self, fp, **kwargs):
        return write_bytes(fp, self.value)

    def __bytes__(self):
        return self.value


@register(TaggedBlockID.UNICODE_LAYER_NAME)
@attr.s(repr=False)
class String(ValueElement):
    """
    String structure.

    .. py:attribute:: value
    """
    value = attr.ib(default='', type=str)

    @classmethod
    def read(cls, fp, padding=4):
        return cls(read_unicode_string(fp, padding))

    def write(self, fp, padding=4):
        return write_unicode_string(fp, self.value, padding)

    def __str__(self):
        return self.value


@register(TaggedBlockID.INVERT)
@attr.s()
class Empty(BaseElement):
    """Empty structure."""
    @classmethod
    def read(cls, fp, **kwargs):
        return cls()

    def write(self, fp, **kwargs):
        return 0


@register(TaggedBlockID.ANIMATION_EFFECTS)
@register(TaggedBlockID.ARTBOARD_DATA1)
@register(TaggedBlockID.ARTBOARD_DATA2)
@register(TaggedBlockID.ARTBOARD_DATA3)
@register(TaggedBlockID.BLACK_AND_WHITE)
@register(TaggedBlockID.CONTENT_GENERATOR_EXTRA_DATA)
@register(TaggedBlockID.EXPORT_SETTING1)
@register(TaggedBlockID.EXPORT_SETTING2)
@register(TaggedBlockID.GRADIENT_FILL_SETTING)
@register(TaggedBlockID.PATTERN_FILL_SETTING)
@register(TaggedBlockID.PIXEL_SOURCE_DATA1)
@register(TaggedBlockID.SOLID_COLOR_SHEET_SETTING)
@register(TaggedBlockID.UNICODE_PATH_NAME)
@register(TaggedBlockID.VIBRANCE)
@attr.s
class DescriptorBlock(BaseElement):
    """
    Integer structure.

    .. py:attribute:: version
    .. py:attribute:: data
    """
    version = attr.ib(default=1, type=int)
    data = attr.ib(default=None, type=Descriptor)

    @classmethod
    def read(cls, fp, **kwargs):
        version = read_fmt('I', fp)[0]
        data = Descriptor.read(fp)
        return cls(version, data)

    def write(self, fp, padding=4):
        written = write_fmt(fp, 'I', self.version)
        written += self.data.write(fp)
        written += write_padding(fp, written, padding)
        return written


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


@attr.s
class Color(BaseElement):
    id = attr.ib(default=ColorSpaceID.RGB, converter=ColorSpaceID,
                 validator=in_(ColorSpaceID))
    values = attr.ib(factory=list)

    @classmethod
    def read(cls, fp, **kwargs):
        id = ColorSpaceID(read_fmt('H', fp)[0])
        if id == ColorSpaceID.LAB:
            values = read_fmt('4h', fp)
        else:
            values = read_fmt('4H', fp)
        return cls(id, values)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'H', self.id.value)
        if self.id == ColorSpaceID.LAB:
            written += write_fmt(fp, '4h', *self.values)
        else:
            written += write_fmt(fp, '4H', *self.values)
        return written


@register(TaggedBlockID.FILTER_MASK)
@attr.s
class FilterMask(BaseElement):
    """
    FilterMask structure.

    .. py:attribute:: color
    .. py:attribute:: opacity
    """
    color = attr.ib(default=None)
    opacity = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp, **kwargs):
        color = Color.read(fp)
        opacity = read_fmt('H', fp)[0]
        return cls(color, opacity)

    def write(self, fp, **kwargs):
        written = self.color.write(fp)
        written += write_fmt(fp, 'H', self.opacity)
        return written


@register(TaggedBlockID.FILTER_EFFECTS1)
@register(TaggedBlockID.FILTER_EFFECTS2)
@register(TaggedBlockID.FILTER_EFFECTS3)
@attr.s(repr=False)
class FilterEffects(ListElement):
    """
    FilterEffects structure.

    .. py:attribute:: version
    .. py:attribute:: items
    """
    version = attr.ib(default=1, type=int)
    items = attr.ib(factory=list)

    @classmethod
    def read(cls, fp, **kwargs):
        version = read_fmt('I', fp)[0]
        assert version in (1, 2, 3), 'Invalid version %d' % (version)
        with io.BytesIO(read_length_block(fp, fmt='Q')) as f:
            items = []
            while is_readable(f):
                items.append(FilterEffect.read(f))
        return cls(version, items)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'I', self.version)
        def writer(f):
            return sum(item.write(f) for item in self)
        written += write_length_block(fp, writer, fmt='Q')
        return written


@attr.s
class FilterEffect(BaseElement):
    """
    FilterEffect structure.

    .. py:attribute:: uuid
    .. py:attribute:: version
    .. py:attribute:: rectangle
    .. py:attribute:: depth
    .. py:attribute:: max_channels
    .. py:attribute:: channels
    .. py:attribute:: extra_data
    """
    uuid = attr.ib(default=None)
    version = attr.ib(default=None)
    rectangle = attr.ib(default=None)
    depth = attr.ib(default=None)
    max_channels = attr.ib(default=None)
    channels = attr.ib(default=None)
    extra_data = attr.ib(default=None)

    @classmethod
    def read(cls, fp, **kwargs):
        uuid = read_pascal_string(fp, encoding='ascii', padding=1)
        version = read_fmt('I', fp)[0]
        assert version == 1, 'Invalid version %d' % (version)
        data = read_length_block(fp, fmt='Q')
        with io.BytesIO(data) as f:
            return cls(uuid, version, *cls._read_body(f))

    @classmethod
    def _read_body(cls, fp):
        rectangle = read_fmt('4i', fp)
        depth, max_channels = read_fmt('2I', fp)
        channels = []
        for _ in range(max_channels + 2):
            channels.append(FilterEffectChannel.read(fp))

        # Documentation is incorrect here.
        extra_data = None
        if is_readable(fp):
            item_present = read_fmt('B', fp)[0]
            extra_rectangle = read_fmt('4i', fp)
            with io.BytesIO(read_length_block(fp, fmt='Q')) as f:
                extra_compression = read_fmt('H', f)[0]
                extra_data = (
                    extra_rectangle, extra_compression, f.read()
                )

        return rectangle, depth, max_channels, channels, extra_data

    def write(self, fp, **kwargs):
        written = write_pascal_string(fp, self.uuid, encoding='ascii',
                                      padding=1)
        written += write_fmt(fp, 'I', self.version)
        def writer(f):
            return self._write_body(f)
        written += write_length_block(fp, writer, fmt='Q')
        return written

    def _write_body(self, fp):
        written = write_fmt(fp, '4i', *self.rectangle)
        written += write_fmt(fp, '2I', self.depth, self.max_channels)
        for channel in self.channels:
            written += channel.write(fp)

        def extra_writer(f):
            length = write_fmt(f, 'H', self.extra_data[1])
            length += write_bytes(f, self.extra_data[2])
            return length

        if self.extra_data is not None:
            written += write_fmt(fp, 'B', 1)
            written += write_fmt(fp, '4i', *self.extra_data[0])
            written += write_length_block(fp, extra_writer, fmt='Q')

        return written


@attr.s
class FilterEffectChannel(BaseElement):
    """
    FilterEffectChannel structure.

    .. py:attribute:: is_written
    .. py:attribute:: compression
    .. py:attribute:: data
    """
    is_written = attr.ib(default=0)
    compression = attr.ib(default=None)
    data = attr.ib(default=b'')

    @classmethod
    def read(cls, fp, **kwargs):
        is_written = read_fmt('I', fp)[0]
        if is_written == 0:
            return cls(is_written=is_written)
        data = read_length_block(fp, fmt='Q')
        if len(data) == 0:
            return cls(is_written=is_written)
        with io.BytesIO(data) as f:
            compression = read_fmt('H', f)[0]
            data = f.read()
        return cls(is_written, compression, data)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'I', self.is_written)
        if self.is_written == 0:
            return written

        def writer(f):
            if self.compression is None:
                return 0
            length = write_fmt(f, 'H', self.compression)
            length += write_bytes(f, self.data)
            return length

        written += write_length_block(fp, writer, fmt='Q')
        return written


@register(TaggedBlockID.METADATA_SETTING)
@attr.s(repr=False)
class MetadataSettings(ListElement):
    """
    MetadataSettings structure.
    """
    items = attr.ib(factory=list)

    @classmethod
    def read(cls, fp, **kwargs):
        count = read_fmt('I', fp)[0]
        items = []
        for _ in range(count):
            items.append(MetadataSetting.read(fp))
        return cls(items)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'I', len(self.items))
        for item in self:
            written += item.write(fp)
        return written


@attr.s
class MetadataSetting(BaseElement):
    """
    MetadataSetting structure.
    """
    signature = attr.ib(default=b'8BIM', type=bytes, repr=False,
                        validator=in_((b'8BIM',)))
    key = attr.ib(default=b'', type=bytes)
    copy_on_sheet = attr.ib(default=False, type=bool)
    data = attr.ib(default=b'', type=bytes)

    @classmethod
    def read(cls, fp, **kwargs):
        signature = fp.read(4)
        assert signature == b'8BIM', 'Invalid signature %r' % signature
        key, copy_on_sheet = read_fmt("4s?3x", fp)
        data = read_length_block(fp)
        try:
            with io.BytesIO(data) as f:
                data = DescriptorBlock.read(f, padding=4)
        except (ValueError, AssertionError):
            logger.warning('Failed to read metadata item %r' % (
                trimmed_repr(data))
            )
        return cls(signature, key, copy_on_sheet, data)

    def write(self, fp, **kwargs):
        written = write_bytes(fp, self.signature)
        written += write_fmt(fp, '4s?3x', self.key, self.copy_on_sheet)
        def writer(f):
            if hasattr(self.data, 'write'):
                return self.data.write(f, padding=4)
            return write_bytes(f, self.data)
        written += write_length_block(fp, writer)
        return written


@register(TaggedBlockID.PATTERNS1)
@register(TaggedBlockID.PATTERNS2)
@register(TaggedBlockID.PATTERNS3)
@attr.s(repr=False)
class Patterns(ListElement):
    """
    Patterns structure.
    """
    items = attr.ib(factory=list)

    @classmethod
    def read(cls, fp, **kwargs):
        items = []
        while is_readable(fp, 4):
            data = read_length_block(fp, padding=4)
            with io.BytesIO(data) as f:
                items.append(Pattern.read(f))
        return cls(items)

    def write(self, fp, **kwargs):
        written = 0
        for item in self:
            written += write_length_block(fp, lambda f: item.write(f),
                                          padding=4)
        return written


@attr.s
class Pattern(BaseElement):
    """
    Pattern structure.

    .. py:attribute:: version
    .. py:attribute:: image_mode
    .. py:attribute:: point
    .. py:attribute:: name
    .. py:attribute:: pattern_id
    .. py:attribute:: color_table
    .. py:attribute:: data
    """
    version = attr.ib(default=1, type=int)
    image_mode = attr.ib(default=ColorMode, converter=ColorMode,
                         validator=in_(ColorMode))
    point = attr.ib(default=None)
    name = attr.ib(default='', type=str)
    pattern_id = attr.ib(default='', type=str)
    color_table = attr.ib(default=None)
    data = attr.ib(default=None)

    @classmethod
    def read(cls, fp, **kwargs):
        version = read_fmt('I', fp)[0]
        assert version == 1, 'Invalid version %d' % (version)
        image_mode = ColorMode(read_fmt('I', fp)[0])
        point = read_fmt('2h', fp)
        name = read_unicode_string(fp)
        pattern_id = read_pascal_string(fp, encoding='ascii', padding=1)
        color_table = None
        if image_mode == ColorMode.INDEXED:
            color_table = [read_fmt("3B", fp) for i in range(256)]
            read_fmt('4x', fp)

        data = VirtualMemoryArrayList.read(fp)
        return cls(version, image_mode, point, name, pattern_id, color_table,
                   data)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, '2I', self.version, self.image_mode.value)
        written += write_fmt(fp, '2h', *self.point)
        written += write_unicode_string(fp, self.name)
        written += write_pascal_string(fp, self.pattern_id, encoding='ascii',
                                       padding=1)
        if self.color_table:
            for row in self.color_table:
                written += write_fmt(fp, '3B', *row)
            written += write_fmt(fp, '4x')
        written += self.data.write(fp)
        return written


@attr.s
class VirtualMemoryArrayList(BaseElement):
    """
    VirtualMemoryArrayList structure.

    .. py:attribute:: version
    .. py:attribute:: rectangle
    .. py:attribute:: channels
    """
    version = attr.ib(default=3, type=int)
    rectangle = attr.ib(default=None)
    channels = attr.ib(default=None)

    @classmethod
    def read(cls, fp, **kwargs):
        version = read_fmt('I', fp)[0]
        assert version == 3, 'Invalid version %d' % (version)

        data = read_length_block(fp)
        with io.BytesIO(data) as f:
            rectangle = read_fmt('4I', f)
            num_channels = read_fmt('I', f)[0]
            channels = []
            for _ in range(num_channels + 2):
                channels.append(VirtualMemoryArray.read(f))

        return cls(version, rectangle, channels)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'I', self.version)
        return written + write_length_block(fp, lambda f: self._write_body(f))

    def _write_body(self, fp):
        written = write_fmt(fp, '4I', *self.rectangle)
        written += write_fmt(fp, 'I', len(self.channels) - 2)
        for channel in self.channels:
            written += channel.write(fp)
        return written


@attr.s
class VirtualMemoryArray(BaseElement):
    """
    VirtualMemoryArrayList structure.

    .. py:attribute:: is_written
    .. py:attribute:: depth
    .. py:attribute:: rectangle
    .. py:attribute:: pixel_depth
    .. py:attribute:: compression
    .. py:attribute:: data
    """
    is_written = attr.ib(default=0)
    depth = attr.ib(default=None)
    rectangle = attr.ib(default=None)
    pixel_depth = attr.ib(default=None)
    compression = attr.ib(default=None)
    data = attr.ib(default=b'')

    @classmethod
    def read(cls, fp, **kwargs):
        is_written = read_fmt('I', fp)[0]
        if is_written == 0:
            return cls(is_written=is_written)
        length = read_fmt('I', fp)[0]
        if length == 0:
            return cls(is_written=is_written)
        depth = read_fmt('I', fp)[0]
        rectangle = read_fmt('4I', fp)
        pixel_depth, compression = read_fmt('HB', fp)
        data = fp.read(length - 23)
        return cls(
            is_written, depth, rectangle, pixel_depth, compression, data
        )

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'I', self.is_written)
        if self.is_written == 0:
            return written
        if self.depth is None:
            written += write_fmt(fp, 'I', 0)
            return written

        return written + write_length_block(fp, lambda f: self._write_body(f))

    def _write_body(self, fp):
        written = write_fmt(fp, 'I', self.depth)
        written += write_fmt(fp, '4I', *self.rectangle)
        written += write_fmt(fp, 'HB', self.pixel_depth, self.compression)
        written += write_bytes(fp, self.data)
        return written


@register(TaggedBlockID.PROTECTED_SETTING)
@attr.s
class ProtectedSetting(BaseElement):
    """
    ProtectedSetting structure.
    """
    transparency = attr.ib(default=False, type=bool)
    composite = attr.ib(default=False, type=bool)
    position = attr.ib(default=False, type=bool)
    bit4 = attr.ib(default=False, type=bool, repr=False)
    bit5 = attr.ib(default=False, type=bool, repr=False)
    bit6 = attr.ib(default=False, type=bool, repr=False)
    bit7 = attr.ib(default=False, type=bool, repr=False)
    bit8 = attr.ib(default=False, type=bool, repr=False)

    @classmethod
    def read(cls, fp, **kwargs):
        flag = read_fmt('I', fp)[0]
        return cls(
            bool(flag & 1), bool(flag & 2), bool(flag & 4), bool(flag & 8),
            bool(flag & 16), bool(flag & 32), bool(flag & 64),
            bool(flag & 128)
        )

    def write(self, fp, **kwargs):
        flag = (
            (self.transparency * 1) |
            (self.composite * 2) |
            (self.position * 4) |
            (self.bit4 * 8) |
            (self.bit5 * 16) |
            (self.bit6 * 32) |
            (self.bit7 * 64) |
            (self.bit8 * 128)
        )
        return write_fmt(fp, 'I', flag)


@register(TaggedBlockID.REFERENCE_POINT)
@attr.s(repr=False)
class ReferencePoint(ValueElement):
    """
    ReferencePoint structure.

    .. py:attribute:: value
    """
    value = attr.ib(default=None, converter=list)

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(read_fmt('2d', fp))

    def write(self, fp, **kwargs):
        return write_fmt(fp, '2d', *self.value)


@register(TaggedBlockID.SECTION_DIVIDER_SETTING)
@register(TaggedBlockID.NESTED_SECTION_DIVIDER_SETTING)
@attr.s
class SectionDividerSetting(BaseElement):
    """
    SectionDividerSetting structure.

    .. py:attribute:: kind
    .. py:attribute:: key
    .. py:attribute:: sub_type
    """
    kind = attr.ib(default=SectionDivider.OTHER, converter=SectionDivider,
                   validator=in_(SectionDivider))
    signature = attr.ib(default=None, repr=False)
    key = attr.ib(default=None)
    sub_type = attr.ib(default=None)

    @classmethod
    def read(cls, fp, **kwargs):
        kind = SectionDivider(read_fmt('I', fp)[0])
        signature, key = None, None
        if is_readable(fp, 8):
            signature = fp.read(4)
            assert signature == b'8BIM', 'Invalid signature %r' % signature
            key = BlendMode(fp.read(4))
        sub_type = None
        if is_readable(fp, 4):
            sub_type = read_fmt('I', fp)[0]
        return cls(kind, signature=signature, key=key, sub_type=sub_type)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'I', self.kind.value)
        if self.signature and self.key:
            written += write_bytes(fp, self.signature)
            written += write_bytes(fp, self.key.value)
            if self.sub_type is not None:
                written += write_fmt(fp, 'I', self.sub_type)
        return written


@register(TaggedBlockID.SHEET_COLOR_SETTING)
@attr.s(repr=False)
class SheetColorSetting(ValueElement):
    """
    SheetColorSetting structure.

    .. py:attribute:: value
    """
    value = attr.ib(default=None, converter=list)

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(read_fmt('4H', fp))

    def write(self, fp, **kwargs):
        return write_fmt(fp, '4H', *self.value)


@register(TaggedBlockID.TYPE_TOOL_OBJECT_SETTING)
@attr.s
class TypeToolObjectSetting(BaseElement):
    """
    TypeToolObjectSetting structure.

    .. py:attribute:: version
    .. py:attribute:: xx
    .. py:attribute:: xy
    .. py:attribute:: yx
    .. py:attribute:: yy
    .. py:attribute:: tx
    .. py:attribute:: ty
    .. py:attribute:: text_version
    .. py:attribute:: text_data_version
    .. py:attribute:: text_data
    .. py:attribute:: warp_version
    .. py:attribute:: warp_data_version
    .. py:attribute:: warp_data
    .. py:attribute:: left
    .. py:attribute:: top
    .. py:attribute:: right
    .. py:attribute:: bottom
    """
    version = attr.ib(default=1, type=int)
    xx = attr.ib(default=0, type=int)
    xy = attr.ib(default=0, type=int)
    yx = attr.ib(default=0, type=int)
    yy = attr.ib(default=0, type=int)
    tx = attr.ib(default=0, type=int)
    ty = attr.ib(default=0, type=int)
    text_version = attr.ib(default=1, type=int, validator=in_((50,)))
    text_data_version = attr.ib(default=16, type=int, validator=in_((16,)))
    text_data = attr.ib(default=None, type=Descriptor)
    warp_version = attr.ib(default=1, type=int, validator=in_((1,)))
    warp_data_version = attr.ib(default=16, type=int, validator=in_((16,)))
    warp_data = attr.ib(default=None, type=Descriptor)
    left = attr.ib(default=0, type=int)
    top = attr.ib(default=0, type=int)
    right = attr.ib(default=0, type=int)
    bottom = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp, **kwargs):
        version, xx, xy, yx, yy, tx, ty = read_fmt('H6d', fp)
        text_version, text_data_version = read_fmt('HI', fp)
        text_data = Descriptor.read(fp)
        warp_version, warp_data_version = read_fmt('HI', fp)
        warp_data = Descriptor.read(fp)
        left, top, right, bottom = read_fmt("4i", fp)
        return cls(
            version, xx, xy, yx, yy, tx, ty, text_version, text_data_version,
            text_data, warp_version, warp_data_version, warp_data, left, top,
            right, bottom
        )

    def write(self, fp, padding=4):
        written = write_fmt(fp, 'H6dHI', self.version, self.xx, self.xy,
            self.yx, self.yy, self.tx, self.ty, self.text_version,
            self.text_data_version
        )
        written += self.text_data.write(fp)
        written += write_fmt(
            fp, 'HI', self.warp_version, self.warp_data_version
        )
        written += self.warp_data.write(fp)
        written += write_fmt(
            fp, '4i', self.left, self.top, self.right, self.bottom
        )
        written += write_padding(fp, written, padding)
        return written


@register(TaggedBlockID.USER_MASK)
@attr.s
class UserMask(BaseElement):
    """
    UserMask structure.

    .. py:attribute:: color
    .. py:attribute:: opacity
    .. py:attribute:: flag
    """
    color = attr.ib(default=None)
    opacity = attr.ib(default=0, type=int)
    flag = attr.ib(default=128, type=int)

    @classmethod
    def read(cls, fp, **kwargs):
        color = Color.read(fp)
        opacity, flag = read_fmt('HBx', fp)
        return cls(color, opacity, flag)

    def write(self, fp, **kwargs):
        written = self.color.write(fp)
        written += write_fmt(fp, 'HBx', self.opacity, self.flag)
        return written


@register(TaggedBlockID.VECTOR_MASK_SETTING1)
@register(TaggedBlockID.VECTOR_MASK_SETTING2)
@attr.s
class VectorMaskSetting(BaseElement):
    """
    VectorMaskSetting structure.

    .. py:attribute:: version
    .. py:attribute:: invert
    .. py:attribute:: not_link
    .. py:attribute:: disable
    .. py:attribute:: path
    """
    version = attr.ib(default=3, type=int)
    flags = attr.ib(default=0, type=int, repr=False)
    path = attr.ib(default=None)

    @classmethod
    def read(cls, fp, **kwargs):
        version, flags = read_fmt('2I', fp)
        assert version == 3, 'Unknown vector mask version %d' % version
        path = fp.read()
        return cls(version, flags, path)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, '2I', self.version, self.flags)
        written += write_bytes(fp, self.path)
        return written

    @property
    def invert(self):
        return self.flags & 1

    @property
    def not_link(self):
        return self.flags & 2

    @property
    def disable(self):
        return self.flags & 4


@register(TaggedBlockID.OBJECT_BASED_EFFECTS_LAYER_INFO)
@register(TaggedBlockID.OBJECT_BASED_EFFECTS_LAYER_INFO_V0)
@register(TaggedBlockID.OBJECT_BASED_EFFECTS_LAYER_INFO_V1)
@register(TaggedBlockID.VECTOR_ORIGINATION_DATA)
@attr.s
class VersionedDescriptorBlock(BaseElement):
    """
    VersionedDescriptorBlock structure.

    .. py:attribute:: version
    .. py:attribute:: data_version
    .. py:attribute:: data
    """
    version = attr.ib(default=1, type=int)
    data_version = attr.ib(default=16, type=int, validator=in_((16,)))
    data = attr.ib(default=None, type=Descriptor)

    @classmethod
    def read(cls, fp, **kwargs):
        version, data_version = read_fmt('2I', fp)
        data = Descriptor.read(fp)
        return cls(version, data_version, data)

    def write(self, fp, padding=4):
        written = write_fmt(fp, '2I', self.version, self.data_version)
        written += self.data.write(fp)
        written += write_padding(fp, written, padding)
        return written
