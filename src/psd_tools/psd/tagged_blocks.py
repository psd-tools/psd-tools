"""
Tagged block data structure.

.. todo:: Support the following tagged blocks: ``TaggedBlockID.PATTERN_DATA``,
    ``TaggedBlockID.TYPE_TOOL_INFO``, ``TaggedBlockID.LAYER``,
    ``TaggedBlockID.ALPHA``

"""
from __future__ import absolute_import, unicode_literals
import attr
import io
import logging
from warnings import warn

from psd_tools.constants import (
    BlendMode, SectionDivider, TaggedBlockID, PlacedLayerType, SheetColorType
)
import psd_tools.psd.layer_and_mask
from psd_tools.psd.adjustments import ADJUSTMENT_TYPES
from psd_tools.psd.base import (
    BaseElement, ByteElement, DictElement, EmptyElement, IntegerElement,
    ListElement, StringElement, ValueElement,
)
from psd_tools.psd.color import Color
from psd_tools.psd.descriptor import DescriptorBlock, DescriptorBlock2
from psd_tools.psd.effects_layer import EffectsLayer
from psd_tools.psd.engine_data import EngineData, EngineData2
from psd_tools.psd.filter_effects import FilterEffects
from psd_tools.psd.linked_layer import LinkedLayers
from psd_tools.psd.patterns import Patterns
from psd_tools.psd.vector import (
    VectorMaskSetting, VectorStrokeContentSetting
)
from psd_tools.validators import in_
from psd_tools.utils import (
    read_fmt, write_fmt, read_length_block, write_length_block, is_readable,
    write_bytes, read_unicode_string, write_unicode_string, write_padding,
    read_pascal_string, write_pascal_string, trimmed_repr, new_registry
)

logger = logging.getLogger(__name__)


TYPES, register = new_registry()

TYPES.update(ADJUSTMENT_TYPES)
TYPES.update({
    TaggedBlockID.ANIMATION_EFFECTS: DescriptorBlock,
    TaggedBlockID.ARTBOARD_DATA1: DescriptorBlock,
    TaggedBlockID.ARTBOARD_DATA2: DescriptorBlock,
    TaggedBlockID.ARTBOARD_DATA3: DescriptorBlock,
    TaggedBlockID.BLEND_CLIPPING_ELEMENTS: ByteElement,
    TaggedBlockID.BLEND_FILL_OPACITY: ByteElement,
    TaggedBlockID.BLEND_INTERIOR_ELEMENTS: ByteElement,
    TaggedBlockID.COMPUTER_INFO: DescriptorBlock,
    TaggedBlockID.CONTENT_GENERATOR_EXTRA_DATA: DescriptorBlock,
    TaggedBlockID.EFFECTS_LAYER: EffectsLayer,
    TaggedBlockID.EXPORT_SETTING1: DescriptorBlock,
    TaggedBlockID.EXPORT_SETTING2: DescriptorBlock,
    TaggedBlockID.FILTER_EFFECTS1: FilterEffects,
    TaggedBlockID.FILTER_EFFECTS2: FilterEffects,
    TaggedBlockID.FILTER_EFFECTS3: FilterEffects,
    TaggedBlockID.KNOCKOUT_SETTING: ByteElement,
    TaggedBlockID.LINKED_LAYER1: LinkedLayers,
    TaggedBlockID.LINKED_LAYER2: LinkedLayers,
    TaggedBlockID.LINKED_LAYER3: LinkedLayers,
    TaggedBlockID.LINKED_LAYER_EXTERNAL: LinkedLayers,
    TaggedBlockID.LAYER_ID: IntegerElement,
    TaggedBlockID.LAYER_MASK_AS_GLOBAL_MASK: ByteElement,
    TaggedBlockID.UNICODE_LAYER_NAME: StringElement,
    TaggedBlockID.LAYER_VERSION: IntegerElement,
    TaggedBlockID.OBJECT_BASED_EFFECTS_LAYER_INFO: DescriptorBlock2,
    TaggedBlockID.OBJECT_BASED_EFFECTS_LAYER_INFO_V0: DescriptorBlock2,
    TaggedBlockID.OBJECT_BASED_EFFECTS_LAYER_INFO_V1: DescriptorBlock2,
    TaggedBlockID.PATTERNS1: Patterns,
    TaggedBlockID.PATTERNS2: Patterns,
    TaggedBlockID.PATTERNS3: Patterns,
    TaggedBlockID.PIXEL_SOURCE_DATA1: DescriptorBlock,
    TaggedBlockID.SAVING_MERGED_TRANSPARENCY: EmptyElement,
    TaggedBlockID.SAVING_MERGED_TRANSPARENCY16: EmptyElement,
    TaggedBlockID.SAVING_MERGED_TRANSPARENCY32: EmptyElement,
    TaggedBlockID.TEXT_ENGINE_DATA: EngineData2,
    TaggedBlockID.TRANSPARENCY_SHAPES_LAYER: ByteElement,
    TaggedBlockID.UNICODE_PATH_NAME: DescriptorBlock,
    TaggedBlockID.USING_ALIGNED_RENDERING: IntegerElement,
    TaggedBlockID.VECTOR_MASK_AS_GLOBAL_MASK: ByteElement,
    TaggedBlockID.VECTOR_MASK_SETTING1: VectorMaskSetting,
    TaggedBlockID.VECTOR_MASK_SETTING2: VectorMaskSetting,
    TaggedBlockID.VECTOR_ORIGINATION_DATA: DescriptorBlock2,
    TaggedBlockID.VECTOR_STROKE_DATA: DescriptorBlock,
    TaggedBlockID.VECTOR_STROKE_CONTENT_DATA: VectorStrokeContentSetting,
})


@attr.s(repr=False, slots=True)
class TaggedBlocks(DictElement):
    """
    Dict of tagged block items.

    See :py:class:`~psd_tools.constants.TaggedBlockID` for available keys.

    Example::

        from psd_tools.constants import TaggedBlockID

        # Iterate over fields
        for key in tagged_blocks:
            print(key)

        # Get a field
        value = tagged_blocks.get_data(TaggedBlockID.TYPE_TOOL_OBJECT_SETTING)
    """
    enum = TaggedBlockID

    def get_data(self, key, default=None):
        """
        Get data from the tagged blocks.

        Shortcut for the following::

            if key in tagged_blocks:
                value = tagged_blocks[key].data
        """
        if key in self:
            value = self[key].data
            if isinstance(value, ValueElement):
                return value.value
            else:
                return value
        return default

    def set_data(self, key, *args, **kwargs):
        """
        Set data for the given key.

        Shortut for the following::

            key = getattr(TaggedBlockID, key)
            kls = TYPES.get(key)
            self[key] = TaggedBlocks(key=key, data=kls(value))

        """
        key = self._key_converter(key)
        kls = TYPES.get(key)
        self[key] = TaggedBlock(key=key, data=kls(*args, **kwargs))

    @classmethod
    def read(cls, fp, version=1, padding=1, end_pos=None):
        items = []
        while is_readable(fp, 8):  # len(signature) + len(key) = 8
            if end_pos is not None and fp.tell() >= end_pos:
                break
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


@attr.s(slots=True)
class TaggedBlock(BaseElement):
    """
    Layer tagged block with extra info.

    .. py:attribute:: key

        4-character code. See :py:class:`~psd_tools.constants.TaggedBlockID`

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
        TaggedBlockID.EXPORT_SETTING1,
        TaggedBlockID.EXPORT_SETTING2,
        TaggedBlockID.COMPUTER_INFO,
    }

    signature = attr.ib(default=b'8BIM', repr=False,
                        validator=in_(_SIGNATURES))
    key = attr.ib(default=b'')
    data = attr.ib(default=b'', repr=True)

    @classmethod
    def read(cls, fp, version=1, padding=1):
        signature = read_fmt('4s', fp)[0]
        if signature not in cls._SIGNATURES:
            logger.warning('Invalid signature (%r)' % (signature))
            fp.seek(-4, 1)
            return None

        key = read_fmt('4s', fp)[0]
        try:
            key = TaggedBlockID(key)
        except ValueError:
            message = 'Unknown key: %r' % (key)
            warn(message)
            logger.warning(message)

        fmt = cls._length_format(key, version)
        raw_data = read_length_block(fp, fmt=fmt, padding=padding)
        kls = TYPES.get(key)
        if kls:
            data = kls.frombytes(raw_data, version=version)
            # _raw_data = data.tobytes(version=version,
            #                          padding=1 if padding == 4 else 4)
            # assert raw_data == _raw_data, '%r: %s vs %s' % (
            #     kls, trimmed_repr(raw_data), trimmed_repr(_raw_data)
            # )
        else:
            message = 'Unknown tagged block: %r, %s' % (
                key, trimmed_repr(raw_data)
            )
            warn(message)
            logger.warning(message)
            data = raw_data
        return cls(signature, key, data)

    def write(self, fp, version=1, padding=1):
        key = self.key if isinstance(self.key, bytes) else self.key.value
        written = write_fmt(fp, '4s4s', self.signature, key)

        def writer(f):
            if hasattr(self.data, 'write'):
                # It seems padding size applies at the block level here.
                inner_padding = 1 if padding == 4 else 4
                return self.data.write(f, padding=inner_padding,
                                       version=version)
            return write_bytes(f, self.data)

        fmt = self._length_format(self.key, version)
        written += write_length_block(fp, writer, fmt=fmt, padding=padding)
        return written

    @classmethod
    def _length_format(cls, key, version):
        return ('I', 'Q')[int(version == 2 and key in cls._BIG_KEYS)]


@register(TaggedBlockID.ANNOTATIONS)
@attr.s(repr=False, slots=True)
class Annotations(ListElement):
    """
    List of Annotation, see :py:class: `.Annotation`.

    .. py:attribute:: major_version
    .. py:attribute:: minor_version
    """
    major_version = attr.ib(default=2, type=int)
    minor_version = attr.ib(default=1, type=int)

    @classmethod
    def read(cls, fp, **kwargs):
        major_version, minor_version, count = read_fmt('2HI', fp)
        items = []
        for _ in range(count):
            length = read_fmt('I', fp)[0] - 4
            if length > 0:
                with io.BytesIO(fp.read(length)) as f:
                    items.append(Annotation.read(f))
        return cls(major_version=major_version, minor_version=minor_version,
                   items=items)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, '2HI', self.major_version, self.minor_version,
                            len(self))
        for item in self:
            data = item.tobytes()
            written += write_fmt(fp, 'I', len(data) + 4)
            written += write_bytes(fp, data)
        written += write_padding(fp, written, 4)
        return written


@attr.s(slots=True)
class Annotation(BaseElement):
    """
    Annotation structure.

    .. py:attribute:: kind
    .. py:attribute:: is_open
    """
    kind = attr.ib(default=b'txtA', type=bytes,
                   validator=in_((b'txtA', b'sndM')))
    is_open = attr.ib(default=0, type=int)
    flags = attr.ib(default=0, type=int)
    optional_blocks = attr.ib(default=1, type=int)
    icon_location = attr.ib(factory=lambda: [0, 0, 0, 0], converter=list)
    popup_location = attr.ib(factory=lambda: [0, 0, 0, 0], converter=list)
    color = attr.ib(factory=Color)
    author = attr.ib(default='', type=str)
    name = attr.ib(default='', type=str)
    mod_date = attr.ib(default='', type=str)
    marker = attr.ib(default=b'txtC', type=bytes,
                     validator=in_((b'txtC', b'sndM')))
    data = attr.ib(default=b'', type=bytes)

    @classmethod
    def read(cls, fp, **kwargs):
        kind, is_open, flags, optional_blocks = read_fmt('4s2BH', fp)
        icon_location = read_fmt('4i', fp)
        popup_location = read_fmt('4i', fp)
        color = Color.read(fp)
        author = read_pascal_string(fp, 'macroman', padding=2)
        name = read_pascal_string(fp, 'macroman', padding=2)
        mod_date = read_pascal_string(fp, 'macroman', padding=2)
        length, marker = read_fmt('I4s', fp)
        data = read_length_block(fp)
        return cls(kind, is_open, flags, optional_blocks, icon_location,
                   popup_location, color, author, name, mod_date, marker,
                   data)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, '4s2BH', self.kind, self.is_open, self.flags,
                            self.optional_blocks)
        written += write_fmt(fp, '4i', *self.icon_location)
        written += write_fmt(fp, '4i', *self.popup_location)
        written += self.color.write(fp)
        written += write_pascal_string(fp, self.author, 'macroman', padding=2)
        written += write_pascal_string(fp, self.name, 'macroman', padding=2)
        written += write_pascal_string(fp, self.mod_date, 'macroman',
                                       padding=2)
        written += write_fmt(fp, 'I4s', len(self.data) + 12, self.marker)
        written += write_length_block(fp, lambda f: write_bytes(f, self.data))
        return written


@register(TaggedBlockID.FOREIGN_EFFECT_ID)
@register(TaggedBlockID.LAYER_NAME_SOURCE_SETTING)
@attr.s(repr=False, slots=True, cmp=False)
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


@register(TaggedBlockID.CHANNEL_BLENDING_RESTRICTIONS_SETTING)
@attr.s(repr=False, slots=True)
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


@register(TaggedBlockID.FILTER_MASK)
@attr.s(slots=True)
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


@attr.s(slots=True)
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
        if key == b'mdyn':
            with io.BytesIO(data) as f:
                data = read_fmt('I', f)[0]
        elif key in (b'cust', b'cmls', b'extn', b'mlst'):
            data = DescriptorBlock.frombytes(data, padding=4)
        else:
            message = 'Unknown metadata key %r' % (key)
            logger.warning(message)
            warn(message)
            data = data
        return cls(signature, key, copy_on_sheet, data)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, '4s4s?3x', self.signature, self.key,
                            self.copy_on_sheet)

        def writer(f):
            if hasattr(self.data, 'write'):
                return self.data.write(f, padding=4)
            elif isinstance(self.data, int):
                return write_fmt(fp, 'I', self.data)
            return write_bytes(f, self.data)

        written += write_length_block(fp, writer)
        return written


@register(TaggedBlockID.PIXEL_SOURCE_DATA2)
@attr.s(slots=True)
class PixelSourceData2(ListElement):
    """
    PixelSourceData2 structure.
    """
    @classmethod
    def read(cls, fp, **kwargs):
        items = []
        while is_readable(fp, 8):
            items.append(read_length_block(fp, fmt='Q'))
        return cls(items)

    def write(self, fp, padding=4, **kwargs):
        written = 0
        for item in self:
            written += write_length_block(fp, lambda f: write_bytes(f, item),
                                          fmt='Q')
        written += write_padding(fp, written, padding)
        return written


@register(TaggedBlockID.PLACED_LAYER1)
@register(TaggedBlockID.PLACED_LAYER2)
@attr.s(slots=True)
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

    def write(self, fp, padding=4, **kwargs):
        written = write_fmt(fp, '4sI', self.kind, self.version)
        written += write_pascal_string(fp, self.uuid, 'macroman', padding=1)
        written += write_fmt(fp, '4I', self.page, self.total_pages,
                             self.anti_alias, self.layer_type.value)
        written += write_fmt(fp, '8d', *self.transform)
        written += self.warp.write(fp, padding=1)
        written += write_padding(fp, written, padding)
        return written


@register(TaggedBlockID.PROTECTED_SETTING)
class ProtectedSetting(IntegerElement):
    """
    ProtectedSetting structure.
    """
    @property
    def transparency(self):
        return bool(self.value & 0x01)

    @property
    def composite(self):
        return bool(self.value & 0x02)

    @property
    def position(self):
        return bool(self.value & 0x04)


@register(TaggedBlockID.REFERENCE_POINT)
@attr.s(repr=False, slots=True)
class ReferencePoint(ListElement):
    """
    ReferencePoint structure.
    """
    @classmethod
    def read(cls, fp, **kwargs):
        return cls(list(read_fmt('2d', fp)))

    def write(self, fp, **kwargs):
        return write_fmt(fp, '2d', *self._items)


@register(TaggedBlockID.SECTION_DIVIDER_SETTING)
@register(TaggedBlockID.NESTED_SECTION_DIVIDER_SETTING)
@attr.s(slots=True)
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


@register(TaggedBlockID.SHEET_COLOR_SETTING)
@attr.s(repr=False, slots=True, cmp=False)
class SheetColorSetting(ValueElement):
    """
    SheetColorSetting value.

    This setting represents color label in the layers panel in Photoshop UI.

    .. py:attribute:: value
    """
    value = attr.ib(default=0, converter=SheetColorType, type=SheetColorType)

    @classmethod
    def read(cls, fp, **kwargs):
        return cls(SheetColorType(*read_fmt('H6x', fp)))

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'H6x', self.value.value)


@register(TaggedBlockID.SMART_OBJECT_LAYER_DATA1)
@register(TaggedBlockID.SMART_OBJECT_LAYER_DATA2)
@attr.s(slots=True)
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

    def write(self, fp, padding=4, **kwargs):
        written = write_fmt(fp, '4sI', self.kind, self.version)
        written += self.data.write(fp, padding=1)
        written += write_padding(fp, written, padding)
        return written


@register(TaggedBlockID.TYPE_TOOL_OBJECT_SETTING)
@attr.s(slots=True)
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
    text_data = attr.ib(default=None, type=DescriptorBlock)
    warp_version = attr.ib(default=1, type=int, validator=in_((1,)))
    warp = attr.ib(default=None, type=DescriptorBlock)
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

    def write(self, fp, padding=4, **kwargs):
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
@attr.s(slots=True)
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
