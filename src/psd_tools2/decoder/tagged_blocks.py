"""
Tagged block data structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import io
import logging
from collections import OrderedDict

from psd_tools2.constants import (
    BlendMode, SectionDivider, TaggedBlockID, PlacedLayerType
)
from psd_tools2.decoder.base import (
    BaseElement, ValueElement, IntegerElement, ListElement, DictElement,
)
from psd_tools2.decoder.color import Color
from psd_tools2.decoder.descriptor import Descriptor
from psd_tools2.decoder.effects_layer import EffectsLayer
from psd_tools2.decoder.filter_effects import FilterEffects
from psd_tools2.decoder.engine_data import EngineData, EngineData2
from psd_tools2.decoder.patterns import Patterns
from psd_tools2.decoder.vector import (
    VectorMaskSetting, VectorStrokeContentSetting
)
from psd_tools2.validators import in_
from psd_tools2.utils import (
    read_fmt, write_fmt, read_length_block, write_length_block, is_readable,
    write_bytes, read_unicode_string, write_unicode_string, write_padding,
    read_pascal_string, write_pascal_string, trimmed_repr, new_registry
)

logger = logging.getLogger(__name__)


TYPES, register = new_registry()

TYPES.update({
    TaggedBlockID.FILTER_EFFECTS1: FilterEffects,
    TaggedBlockID.FILTER_EFFECTS2: FilterEffects,
    TaggedBlockID.FILTER_EFFECTS3: FilterEffects,
    TaggedBlockID.EFFECTS_LAYER: EffectsLayer,
    TaggedBlockID.PATTERNS1: Patterns,
    TaggedBlockID.PATTERNS2: Patterns,
    TaggedBlockID.PATTERNS3: Patterns,
    TaggedBlockID.TEXT_ENGINE_DATA: EngineData2,
    TaggedBlockID.VECTOR_MASK_SETTING1: VectorMaskSetting,
    TaggedBlockID.VECTOR_MASK_SETTING2: VectorMaskSetting,
    TaggedBlockID.VECTOR_STROKE_CONTENT_DATA: VectorStrokeContentSetting,
})


@attr.s(repr=False)
class TaggedBlocks(DictElement):
    """
    Dict of tagged blocks.
    """
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


@register(TaggedBlockID.LAYER_ID)  # Documentation is incorrect.
@register(TaggedBlockID.LAYER_VERSION)
@register(TaggedBlockID.USING_ALIGNED_RENDERING)
class Integer(IntegerElement):
    """
    Integer structure.
    """
    @classmethod
    def read(cls, fp, **kwargs):
        return cls(read_fmt('I', fp)[0])

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'I', self.value)


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


@register(TaggedBlockID.BLEND_CLIPPING_ELEMENTS)
@register(TaggedBlockID.BLEND_INTERIOR_ELEMENTS)
@register(TaggedBlockID.KNOCKOUT_SETTING)
@register(TaggedBlockID.BLEND_FILL_OPACITY)
@register(TaggedBlockID.LAYER_MASK_AS_GLOBAL_MASK)
@register(TaggedBlockID.TRANSPARENCY_SHAPES_LAYER)
@register(TaggedBlockID.VECTOR_MASK_AS_GLOBAL_MASK)
class Byte(IntegerElement):
    """
    Byte structure.
    """
    @classmethod
    def read(cls, fp, **kwargs):
        return cls(read_fmt('B3x', fp)[0])

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'B3x', self.value)


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


@register(TaggedBlockID.SAVING_MERGED_TRANSPARENCY)
@register(TaggedBlockID.SAVING_MERGED_TRANSPARENCY16)
@register(TaggedBlockID.SAVING_MERGED_TRANSPARENCY32)
@register(TaggedBlockID.INVERT)
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
@register(TaggedBlockID.VECTOR_STROKE_DATA)
@register(TaggedBlockID.VIBRANCE)
@attr.s(repr=False)
class DescriptorBlock(Descriptor):
    """
    Dict-like Descriptor-based structure. See
    :py:class:`~psd_tools2.decoder.descriptor.Descriptor`.

    .. py:attribute:: version
    """
    version = attr.ib(default=1, type=int)

    @classmethod
    def read(cls, fp, **kwargs):
        version = read_fmt('I', fp)[0]
        return cls(version=version, **cls._read_body(fp))

    def write(self, fp, padding=4):
        written = write_fmt(fp, 'I', self.version)
        written += self._write_body(fp)
        written += write_padding(fp, written, padding)
        return written


@register(TaggedBlockID.OBJECT_BASED_EFFECTS_LAYER_INFO)
@register(TaggedBlockID.OBJECT_BASED_EFFECTS_LAYER_INFO_V0)
@register(TaggedBlockID.OBJECT_BASED_EFFECTS_LAYER_INFO_V1)
@register(TaggedBlockID.VECTOR_ORIGINATION_DATA)
@attr.s(repr=False)
class DescriptorBlock2(Descriptor):
    """
    Dict-like Descriptor-based structure. See
    :py:class:`~psd_tools2.decoder.descriptor.Descriptor`.

    .. py:attribute:: version
    .. py:attribute:: data_version
    """
    version = attr.ib(default=1, type=int)
    data_version = attr.ib(default=16, type=int, validator=in_((16,)))

    @classmethod
    def read(cls, fp, **kwargs):
        version, data_version = read_fmt('2I', fp)
        return cls(version=version, data_version=data_version,
                   **cls._read_body(fp))

    def write(self, fp, padding=4):
        written = write_fmt(fp, '2I', self.version, self.data_version)
        written += self._write_body(fp)
        written += write_padding(fp, written, padding)
        return written


@register(TaggedBlockID.CHANNEL_BLENDING_RESTRICTIONS_SETTING)
@attr.s(repr=False)
class ChannelBlendingRestrictionsSetting(ListElement):
    """
    ChannelBlendingRestrictionsSetting structure.

    List of restricted channel numbers (int).
    """
    @classmethod
    def read(cls, fp, **kwargs):
        items = []
        while is_readable(fp, 4):
            items.append(read_fmt('I', fp)[0])
        return cls(items)

    def write(self, fp, **kwargs):
        return write_fmt(fp, '%dI' % len(self), *self._items)


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


@register(TaggedBlockID.METADATA_SETTING)
class MetadataSettings(ListElement):
    """
    MetadataSettings structure.
    """
    @classmethod
    def read(cls, fp, **kwargs):
        count = read_fmt('I', fp)[0]
        items = []
        for _ in range(count):
            items.append(MetadataSetting.read(fp))
        return cls(items)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'I', len(self))
        written += sum(item.write(fp) for item in self)
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
        signature = read_fmt('4s', fp)[0]
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
        written = write_fmt(fp, '4s4s?3x', self.signature, self.key,
                            self.copy_on_sheet)
        def writer(f):
            if hasattr(self.data, 'write'):
                return self.data.write(f, padding=4)
            return write_bytes(f, self.data)
        written += write_length_block(fp, writer)
        return written


@register(TaggedBlockID.PLACED_LAYER1)
@register(TaggedBlockID.PLACED_LAYER2)
@attr.s
class PlacedLayerData(BaseElement):
    """
    PlacedLayerData structure.
    """
    kind = attr.ib(default=b'plcL', type=bytes)
    version = attr.ib(default=3, type=int, validator=in_((3,)))
    uuid = attr.ib(default='', type=bytes)
    page = attr.ib(default=0, type=int)
    total_pages = attr.ib(default=0, type=int)
    anti_alias = attr.ib(default=0, type=int)
    layer_type = attr.ib(default=PlacedLayerType.UNKNOWN,
                         converter=PlacedLayerType,
                         validator=in_(PlacedLayerType))
    transform = attr.ib(default=(0.,) * 8, type=tuple)
    warp = attr.ib(default=None)

    @classmethod
    def read(cls, fp, **kwargs):
        kind, version = read_fmt('4sI', fp)
        uuid = read_pascal_string(fp, 'macroman', padding=1)
        page, total_pages, anti_alias, layer_type = read_fmt('4I', fp)
        transform = read_fmt('8d', fp)
        warp = DescriptorBlock2.read(fp, padding=1)
        return cls(kind, version, uuid, page, total_pages, anti_alias,
                   layer_type, transform, warp)

    def write(self, fp, padding=4):
        written = write_fmt(fp, '4sI', self.kind, self.version)
        written += write_pascal_string(fp, self.uuid, 'macroman', padding=1)
        written += write_fmt(fp, '4I', self.page, self.total_pages,
                             self.anti_alias, self.layer_type.value)
        written += write_fmt(fp, '8d', *self.transform)
        written += self.warp.write(fp, padding=1)
        written += write_padding(fp, written, padding)
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
    value = attr.ib(factory=list, converter=list)

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
            signature = read_fmt('4s', fp)[0]
            assert signature == b'8BIM', 'Invalid signature %r' % signature
            key = BlendMode(read_fmt('4s', fp)[0])
        sub_type = None
        if is_readable(fp, 4):
            sub_type = read_fmt('I', fp)[0]
        return cls(kind, signature=signature, key=key, sub_type=sub_type)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'I', self.kind.value)
        if self.signature and self.key:
            written += write_fmt(fp, '4s4s', self.signature, self.key.value)
            if self.sub_type is not None:
                written += write_fmt(fp, 'I', self.sub_type)
        return written


@register(TaggedBlockID.SELECTIVE_COLOR)
@attr.s
class SelectiveColor(BaseElement):
    """
    SelectiveColor structure.

    .. py:attribute:: value
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


@register(TaggedBlockID.SMART_OBJECT_LAYER_DATA1)
@register(TaggedBlockID.SMART_OBJECT_LAYER_DATA2)
@attr.s
class SmartObjectLayerData(BaseElement):
    """
    VersionedDescriptorBlock structure.

    .. py:attribute:: kind
    .. py:attribute:: version
    .. py:attribute:: data
    """
    kind = attr.ib(default=b'soLD', type=bytes, validator=in_((b'soLD',)))
    version = attr.ib(default=5, type=int, validator=in_((4, 5)))
    data = attr.ib(default=None, type=DescriptorBlock)

    @classmethod
    def read(cls, fp, **kwargs):
        kind, version = read_fmt('4sI', fp)
        data = DescriptorBlock.read(fp)
        return cls(kind, version, data)

    def write(self, fp, padding=4):
        written = write_fmt(fp, '4sI', self.kind, self.version)
        written += self.data.write(fp, padding=1)
        written += write_padding(fp, written, padding)
        return written


@register(TaggedBlockID.TYPE_TOOL_OBJECT_SETTING)
@attr.s
class TypeToolObjectSetting(BaseElement):
    """
    TypeToolObjectSetting structure.

    .. py:attribute:: version
    .. py:attribute:: transform

        Tuple of affine transform parameters (xx, xy, yx, yy, tx, ty).

    .. py:attribute:: text_version
    .. py:attribute:: text_data
    .. py:attribute:: warp_version
    .. py:attribute:: warp
    .. py:attribute:: left
    .. py:attribute:: top
    .. py:attribute:: right
    .. py:attribute:: bottom
    """
    version = attr.ib(default=1, type=int)
    transform = attr.ib(default=(0.,) * 6, type=tuple)
    text_version = attr.ib(default=1, type=int, validator=in_((50,)))
    text_data = attr.ib(default=None, type=Descriptor)
    warp_version = attr.ib(default=1, type=int, validator=in_((1,)))
    warp = attr.ib(default=None, type=Descriptor)
    left = attr.ib(default=0, type=int)
    top = attr.ib(default=0, type=int)
    right = attr.ib(default=0, type=int)
    bottom = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp, **kwargs):
        version = read_fmt('H', fp)[0]
        transform = read_fmt('6d', fp)
        text_version = read_fmt('H', fp)[0]
        text_data = DescriptorBlock.read(fp)
        # Engine data.
        if b'EngineData' in text_data:
            try:
                engine_data = text_data[b'EngineData'].value
                engine_data = EngineData.frombytes(engine_data)
                text_data[b'EngineData'].value = engine_data
            except:
                logger.warning('Failed to read engine data')
        warp_version = read_fmt('H', fp)[0]
        warp = DescriptorBlock.read(fp)
        left, top, right, bottom = read_fmt("4i", fp)
        return cls(version, transform, text_version, text_data, warp_version,
                   warp, left, top, right, bottom)

    def write(self, fp, padding=4):
        written = write_fmt(fp, 'H6d', self.version, *self.transform)
        written += write_fmt(fp, 'H', self.text_version)
        written += self.text_data.write(fp, padding=1)
        written += write_fmt(fp, 'H', self.warp_version)
        written += self.warp.write(fp, padding=1)
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
