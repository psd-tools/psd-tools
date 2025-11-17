"""
Tagged block data structure.

.. todo:: Support the following tagged blocks: ``Tag.PATTERN_DATA``,
    ``Tag.TYPE_TOOL_INFO``, ``Tag.LAYER``,
    ``Tag.ALPHA``

"""

import io
import logging
from typing import Any, BinaryIO, Optional, TypeVar

from attrs import define, field

from psd_tools.constants import (
    BlendMode,
    PlacedLayerType,
    SectionDivider,
    SheetColorType,
    Tag,
)
from psd_tools.psd.adjustments import ADJUSTMENT_TYPES
from psd_tools.psd.base import (
    BaseElement,
    ByteElement,
    DictElement,
    EmptyElement,
    IntegerElement,
    ListElement,
    StringElement,
    ValueElement,
)
from psd_tools.psd.color import Color
from psd_tools.psd.descriptor import DescriptorBlock, DescriptorBlock2
from psd_tools.psd.effects_layer import EffectsLayer
from psd_tools.psd.engine_data import EngineData, EngineData2
from psd_tools.psd.filter_effects import FilterEffects
from psd_tools.psd.linked_layer import LinkedLayers
from psd_tools.psd.patterns import Patterns
from psd_tools.psd.vector import VectorMaskSetting, VectorStrokeContentSetting
from psd_tools.psd.bin_utils import (
    is_readable,
    read_fmt,
    read_length_block,
    read_pascal_string,
    trimmed_repr,
    write_bytes,
    write_fmt,
    write_length_block,
    write_padding,
    write_pascal_string,
)
from psd_tools.registry import new_registry
from psd_tools.validators import in_

logger = logging.getLogger(__name__)

T_TaggedBlocks = TypeVar("T_TaggedBlocks", bound="TaggedBlocks")
T_TaggedBlock = TypeVar("T_TaggedBlock", bound="TaggedBlock")

TYPES, register = new_registry()

TYPES.update(ADJUSTMENT_TYPES)
TYPES.update(
    {
        Tag.ANIMATION_EFFECTS: DescriptorBlock,
        Tag.ARTBOARD_DATA1: DescriptorBlock,
        Tag.ARTBOARD_DATA2: DescriptorBlock,
        Tag.ARTBOARD_DATA3: DescriptorBlock,
        Tag.BLEND_CLIPPING_ELEMENTS: ByteElement,
        Tag.BLEND_FILL_OPACITY: ByteElement,
        Tag.BLEND_INTERIOR_ELEMENTS: ByteElement,
        Tag.COMPOSITOR_INFO: DescriptorBlock,
        Tag.CONTENT_GENERATOR_EXTRA_DATA: DescriptorBlock,
        Tag.EFFECTS_LAYER: EffectsLayer,
        Tag.EXPORT_SETTING1: DescriptorBlock,
        Tag.EXPORT_SETTING2: DescriptorBlock,
        Tag.FILTER_EFFECTS1: FilterEffects,
        Tag.FILTER_EFFECTS2: FilterEffects,
        Tag.FILTER_EFFECTS3: FilterEffects,
        Tag.FRAMED_GROUP: DescriptorBlock,
        Tag.KNOCKOUT_SETTING: ByteElement,
        Tag.LINKED_LAYER1: LinkedLayers,
        Tag.LINKED_LAYER2: LinkedLayers,
        Tag.LINKED_LAYER3: LinkedLayers,
        Tag.LINKED_LAYER_EXTERNAL: LinkedLayers,
        Tag.LAYER_ID: IntegerElement,
        Tag.LAYER_MASK_AS_GLOBAL_MASK: ByteElement,
        Tag.UNICODE_LAYER_NAME: StringElement,
        Tag.LAYER_VERSION: IntegerElement,
        Tag.OBJECT_BASED_EFFECTS_LAYER_INFO: DescriptorBlock2,
        Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V0: DescriptorBlock2,
        Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V1: DescriptorBlock2,
        Tag.PATTERNS1: Patterns,
        Tag.PATTERNS2: Patterns,
        Tag.PATTERNS3: Patterns,
        Tag.PATT: EmptyElement,
        Tag.PIXEL_SOURCE_DATA1: DescriptorBlock,
        Tag.SAVING_MERGED_TRANSPARENCY: EmptyElement,
        Tag.SAVING_MERGED_TRANSPARENCY16: EmptyElement,
        Tag.SAVING_MERGED_TRANSPARENCY32: EmptyElement,
        Tag.TEXT_ENGINE_DATA: EngineData2,
        Tag.TRANSPARENCY_SHAPES_LAYER: ByteElement,
        Tag.UNICODE_PATH_NAME: DescriptorBlock,
        Tag.USING_ALIGNED_RENDERING: IntegerElement,
        Tag.VECTOR_MASK_AS_GLOBAL_MASK: ByteElement,
        Tag.VECTOR_MASK_SETTING1: VectorMaskSetting,
        Tag.VECTOR_MASK_SETTING2: VectorMaskSetting,
        Tag.VECTOR_ORIGINATION_DATA: DescriptorBlock2,
        Tag.VECTOR_ORIGINATION_UNKNOWN: IntegerElement,
        Tag.VECTOR_STROKE_DATA: DescriptorBlock,
        Tag.VECTOR_STROKE_CONTENT_DATA: VectorStrokeContentSetting,
        # Unknown tags.
        # Tag.CAI: DescriptorBlock2,
        Tag.GENI: DescriptorBlock,
        Tag.OCIO: DescriptorBlock,
    }
)


@define(repr=False)
class TaggedBlocks(DictElement):
    """
    Dict of tagged block items.

    See :py:class:`~psd_tools.constants.Tag` for available keys.

    Example::

        from psd_tools.constants import Tag

        # Iterate over fields
        for key in tagged_blocks:
            print(key)

        # Get a field
        value = tagged_blocks.get_data(Tag.TYPE_TOOL_OBJECT_SETTING)
    """

    def get_data(self, key: Any, default: Any = None) -> Any:
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

    def set_data(self, key: Any, *args: Any, **kwargs: Any) -> None:
        """
        Set data for the given key.

        Shortut for the following::

            key = getattr(Tag, key)
            kls = TYPES.get(key)
            self[key] = TaggedBlocks(key=key, data=kls(value))

        """
        key = self._key_converter(key)
        kls = TYPES.get(key)
        if kls is not None:
            self[key] = TaggedBlock(key=key, data=kls(*args, **kwargs))

    @classmethod
    def read(
        cls: type[T_TaggedBlocks],
        fp: BinaryIO,
        version: int = 1,
        padding: int = 1,
        end_pos: Optional[int] = None,
        **kwargs: Any,
    ) -> T_TaggedBlocks:
        items = []
        while is_readable(fp, 8):  # len(signature) + len(key) = 8
            if end_pos is not None and fp.tell() >= end_pos:
                break
            block = TaggedBlock.read(fp, version, padding)
            if block is None:
                break
            items.append((block.key, block))
        return cls(items)  # type: ignore[arg-type]

    @classmethod
    def _key_converter(cls, key: Any) -> Any:
        return getattr(key, "value", key)

    def _repr_pretty_(self, p: Any, cycle: bool) -> None:
        if cycle:
            return

        with p.group(2, "{", "}"):
            p.breakable("")
            for idx, key in enumerate(self._items):
                if idx:
                    p.text(",")
                    p.breakable()
                value = self._items[key]
                try:
                    p.text(Tag(key).name)
                except ValueError:
                    p.pretty(key)
                p.text(": ")
                if isinstance(value.data, bytes):
                    p.text(trimmed_repr(value.data))
                else:
                    p.pretty(value.data)
            p.breakable("")


@define(repr=False)
class TaggedBlock(BaseElement):
    """
    Layer tagged block with extra info.

    .. py:attribute:: key

        4-character code. See :py:class:`~psd_tools.constants.Tag`

    .. py:attribute:: data

        Data.
    """

    _SIGNATURES = (b"8BIM", b"8B64")
    _BIG_KEYS = {
        Tag.USER_MASK,
        Tag.LAYER_16,
        Tag.LAYER_32,
        Tag.LAYER,
        Tag.SAVING_MERGED_TRANSPARENCY16,
        Tag.SAVING_MERGED_TRANSPARENCY32,
        Tag.SAVING_MERGED_TRANSPARENCY,
        Tag.SAVING_MERGED_TRANSPARENCY16,
        Tag.ALPHA,
        Tag.FILTER_MASK,
        Tag.LINKED_LAYER2,
        Tag.LINKED_LAYER3,
        Tag.LINKED_LAYER_EXTERNAL,
        Tag.FILTER_EFFECTS1,
        Tag.FILTER_EFFECTS2,
        Tag.FILTER_EFFECTS3,
        Tag.PIXEL_SOURCE_DATA2,
        Tag.UNICODE_PATH_NAME,
        Tag.EXPORT_SETTING1,
        Tag.EXPORT_SETTING2,
        Tag.COMPOSITOR_INFO,
        Tag.ARTBOARD_DATA2,
    }

    signature: bytes = field(default=b"8BIM", repr=False, validator=in_(_SIGNATURES))
    key: bytes = b""
    data: bytes = field(default=b"", repr=True)

    @classmethod
    def read(
        cls: type[T_TaggedBlock],
        fp: BinaryIO,
        version: int = 1,
        padding: int = 1,
        **kwargs: Any,
    ) -> T_TaggedBlock:  # type: ignore[return]
        signature = read_fmt("4s", fp)[0]
        if signature not in cls._SIGNATURES:
            logger.warning("Invalid signature (%r)" % (signature))
            fp.seek(-4, 1)
            return None  # type: ignore[return-value]

        key = read_fmt("4s", fp)[0]
        try:
            key = Tag(key)
        except ValueError:
            message = "Unknown key: %r" % (key)
            logger.warning(message)

        fmt = cls._length_format(key, version)
        raw_data = read_length_block(fp, fmt=fmt, padding=padding)
        kls = TYPES.get(key)
        if kls:
            try:
                data = kls.frombytes(raw_data, version=version)
            except (OSError, ValueError) as e:
                # Fallback to raw data.
                message = "Failed to read tagged block %r: %s" % (key, e)
                logger.error(message)
                data = raw_data
        else:
            message = "Unknown tagged block: %r, %s" % (key, trimmed_repr(raw_data))
            logger.info(message)
            data = raw_data
        return cls(signature, key, data)

    def write(
        self, fp: BinaryIO, version: int = 1, padding: int = 1, **kwargs: Any
    ) -> int:
        key = self.key if isinstance(self.key, bytes) else self.key.value
        written = write_fmt(fp, "4s4s", self.signature, key)

        def writer(f: BinaryIO) -> int:
            if hasattr(self.data, "write"):
                # It seems padding size applies at the block level here.
                inner_padding = 1 if padding == 4 else 4
                return self.data.write(f, padding=inner_padding, version=version)
            return write_bytes(f, self.data)

        fmt = self._length_format(self.key, version)
        written += write_length_block(fp, writer, fmt=fmt, padding=padding)
        return written

    @classmethod
    def _length_format(cls, key: Any, version: int) -> str:
        return ("I", "Q")[int(version == 2 and key in cls._BIG_KEYS)]


@register(Tag.ANNOTATIONS)
@define(repr=False)
class Annotations(ListElement):
    """
    List of Annotation, see :py:class: `.Annotation`.

    .. py:attribute:: major_version
    .. py:attribute:: minor_version
    """

    major_version: int = 2
    minor_version: int = 1

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "Annotations":
        major_version, minor_version, count = read_fmt("2HI", fp)
        items = []
        for _ in range(count):
            length = read_fmt("I", fp)[0] - 4
            if length > 0:
                with io.BytesIO(fp.read(length)) as f:
                    items.append(Annotation.read(f))
        return cls(
            major_version=major_version,
            minor_version=minor_version,
            items=items,  # type: ignore[arg-type]
        )

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(
            fp, "2HI", self.major_version, self.minor_version, len(self)
        )
        for item in self:
            data = item.tobytes()
            written += write_fmt(fp, "I", len(data) + 4)
            written += write_bytes(fp, data)
        written += write_padding(fp, written, 4)
        return written


@define(repr=False)
class Annotation(BaseElement):
    """
    Annotation structure.

    .. py:attribute:: kind
    .. py:attribute:: is_open
    """

    kind: bytes = field(default=b"txtA", validator=in_((b"txtA", b"sndM")))
    is_open: int = 0
    flags: int = 0
    optional_blocks: int = 1
    icon_location: list[int] = field(factory=lambda: [0, 0, 0, 0], converter=list)
    popup_location: list[int] = field(factory=lambda: [0, 0, 0, 0], converter=list)
    color: Color = field(factory=Color)
    author: str = ""
    name: str = ""
    mod_date: str = ""
    marker: bytes = field(default=b"txtC", validator=in_((b"txtC", b"sndM")))
    data: bytes = b""

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "Annotation":
        kind, is_open, flags, optional_blocks = read_fmt("4s2BH", fp)
        icon_location = read_fmt("4i", fp)
        popup_location = read_fmt("4i", fp)
        color = Color.read(fp)
        author = read_pascal_string(fp, "macroman", padding=2)
        name = read_pascal_string(fp, "macroman", padding=2)
        mod_date = read_pascal_string(fp, "macroman", padding=2)
        length, marker = read_fmt("I4s", fp)
        data = read_length_block(fp)
        return cls(
            kind,
            is_open,
            flags,
            optional_blocks,
            icon_location,
            popup_location,
            color,
            author,
            name,
            mod_date,
            marker,
            data,
        )

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(
            fp, "4s2BH", self.kind, self.is_open, self.flags, self.optional_blocks
        )
        written += write_fmt(fp, "4i", *self.icon_location)
        written += write_fmt(fp, "4i", *self.popup_location)
        written += self.color.write(fp)
        written += write_pascal_string(fp, self.author, "macroman", padding=2)
        written += write_pascal_string(fp, self.name, "macroman", padding=2)
        written += write_pascal_string(fp, self.mod_date, "macroman", padding=2)
        written += write_fmt(fp, "I4s", len(self.data) + 12, self.marker)
        written += write_length_block(fp, lambda f: write_bytes(f, self.data))
        return written


@register(Tag.FOREIGN_EFFECT_ID)
@register(Tag.LAYER_NAME_SOURCE_SETTING)
@define(repr=False, eq=False, order=False)
class Bytes(ValueElement):
    """
    Bytes structure.

    .. py:attribute:: value
    """

    value: bytes = b"\x00\x00\x00\x00"

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "Bytes":
        return cls(fp.read(4))

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_bytes(fp, self.value)


@register(Tag.CHANNEL_BLENDING_RESTRICTIONS_SETTING)
@define(repr=False)
class ChannelBlendingRestrictionsSetting(ListElement):
    """
    ChannelBlendingRestrictionsSetting structure.

    List of restricted channel numbers (int).
    """

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "ChannelBlendingRestrictionsSetting":
        items = []
        while is_readable(fp, 4):
            items.append(read_fmt("I", fp)[0])
        return cls(items)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "%dI" % len(self), *self._items)


@register(Tag.FILTER_MASK)
@define(repr=False)
class FilterMask(BaseElement):
    """
    FilterMask structure.

    .. py:attribute:: color
    .. py:attribute:: opacity
    """

    color: Color = field(factory=Color)
    opacity: int = 0

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "FilterMask":
        color = Color.read(fp)
        opacity = read_fmt("H", fp)[0]
        return cls(color, opacity)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = self.color.write(fp)
        written += write_fmt(fp, "H", self.opacity)
        return written


@register(Tag.METADATA_SETTING)
class MetadataSettings(ListElement):
    """
    MetadataSettings structure.
    """

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "MetadataSettings":
        count = read_fmt("I", fp)[0]
        items = []
        for _ in range(count):
            items.append(MetadataSetting.read(fp))
        return cls(items)  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "I", len(self))
        written += sum(item.write(fp) for item in self)
        return written


@define(repr=False)
class MetadataSetting(BaseElement):
    """
    MetadataSetting structure.
    """

    _KNOWN_KEYS = {b"cust", b"cmls", b"extn", b"mlst", b"tmln", b"sgrp"}
    _KNOWN_SIGNATURES = (b"8BIM", b"8ELE")
    signature: bytes = field(
        default=b"8BIM", repr=False, validator=in_(_KNOWN_SIGNATURES)
    )
    key: bytes = b""
    copy_on_sheet: bool = False
    data: bytes = b""

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "MetadataSetting":
        signature = read_fmt("4s", fp)[0]
        assert signature in cls._KNOWN_SIGNATURES, "Invalid signature %r" % signature
        key, copy_on_sheet = read_fmt("4s?3x", fp)
        data: Any = read_length_block(fp)
        if key in (b"mdyn", b"sgrp"):
            with io.BytesIO(data) as f:
                data = read_fmt("I", f)[0]
        elif key in cls._KNOWN_KEYS:
            data = DescriptorBlock.frombytes(data, padding=4)
        else:
            message = "Unknown metadata key %r" % (key)
            logger.warning(message)
            data = data
        return cls(signature, key, copy_on_sheet, data)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "4s4s?3x", self.signature, self.key, self.copy_on_sheet)

        def writer(f: BinaryIO) -> int:
            if hasattr(self.data, "write"):
                return self.data.write(f, padding=4)
            elif isinstance(self.data, int):
                return write_fmt(fp, "I", self.data)
            return write_bytes(f, self.data)

        written += write_length_block(fp, writer)
        return written


@register(Tag.PIXEL_SOURCE_DATA2)
@define(repr=False)
class PixelSourceData2(ListElement):
    """
    PixelSourceData2 structure.
    """

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "PixelSourceData2":
        items = []
        while is_readable(fp, 8):
            items.append(read_length_block(fp, fmt="Q"))
        return cls(items)  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, padding: int = 4, **kwargs: Any) -> int:
        written = 0
        for item in self:
            written += write_length_block(
                fp, lambda f, item=item: write_bytes(f, item), fmt="Q"
            )
        written += write_padding(fp, written, padding)
        return written


@register(Tag.PLACED_LAYER1)
@register(Tag.PLACED_LAYER2)
@define(repr=False)
class PlacedLayerData(BaseElement):
    """
    PlacedLayerData structure.
    """

    kind: bytes = b"plcL"
    version: int = field(default=3, validator=in_((3,)))
    uuid: bytes = b""
    page: int = 0
    total_pages: int = 0
    anti_alias: int = 0
    layer_type: PlacedLayerType = field(
        default=PlacedLayerType.UNKNOWN,
        converter=PlacedLayerType,
        validator=in_(PlacedLayerType),
    )
    transform: tuple = (0.0,) * 8
    warp: object = None

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "PlacedLayerData":
        kind, version = read_fmt("4sI", fp)
        uuid_str = read_pascal_string(fp, "macroman", padding=1)
        page, total_pages, anti_alias, layer_type = read_fmt("4I", fp)
        transform = read_fmt("8d", fp)
        warp = DescriptorBlock2.read(fp, padding=1)
        return cls(
            kind,
            version,
            uuid_str.encode("macroman") if isinstance(uuid_str, str) else uuid_str,
            page,
            total_pages,
            anti_alias,
            layer_type,
            transform,
            warp,
        )

    def write(self, fp: BinaryIO, padding: int = 4, **kwargs: Any) -> int:
        written = write_fmt(fp, "4sI", self.kind, self.version)
        uuid_str = (
            self.uuid.decode("macroman") if isinstance(self.uuid, bytes) else self.uuid
        )
        written += write_pascal_string(fp, uuid_str, "macroman", padding=1)
        written += write_fmt(
            fp,
            "4I",
            self.page,
            self.total_pages,
            self.anti_alias,
            self.layer_type.value,
        )
        written += write_fmt(fp, "8d", *self.transform)
        written += self.warp.write(fp, padding=1)  # type: ignore[attr-defined]
        written += write_padding(fp, written, padding)
        return written


@register(Tag.PROTECTED_SETTING)
class ProtectedSetting(IntegerElement):
    """
    ProtectedSetting structure.
    """

    @property
    def transparency(self) -> bool:
        return bool(self.value & 0x01)

    @property
    def composite(self) -> bool:
        return bool(self.value & 0x02)

    @property
    def position(self) -> bool:
        return bool(self.value & 0x04)

    @property
    def nesting(self) -> bool:
        return bool(self.value & 0x08)

    @property
    def complete(self) -> bool:
        return self.value == 2147483648

    def lock(self, lock_flags: Any) -> None:
        self.value = int(lock_flags)


@register(Tag.REFERENCE_POINT)
@define(repr=False)
class ReferencePoint(ListElement):
    """
    ReferencePoint structure.
    """

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "ReferencePoint":
        return cls(list(read_fmt("2d", fp)))

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "2d", *self._items)


@register(Tag.SECTION_DIVIDER_SETTING)
@register(Tag.NESTED_SECTION_DIVIDER_SETTING)
@define(repr=False)
class SectionDividerSetting(BaseElement):
    """
    SectionDividerSetting structure.

    .. py:attribute:: kind
    .. py:attribute:: blend_mode
    .. py:attribute:: sub_type
    """

    kind: SectionDivider = field(
        default=SectionDivider.OTHER,
        converter=SectionDivider,
        validator=in_(SectionDivider),
    )
    signature: Optional[bytes] = field(default=None, repr=False)
    blend_mode: Optional[BlendMode] = None
    sub_type: Optional[int] = None

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "SectionDividerSetting":
        kind = SectionDivider(read_fmt("I", fp)[0])
        signature, blend_mode = None, None
        if is_readable(fp, 8):
            signature = read_fmt("4s", fp)[0]
            assert signature == b"8BIM", "Invalid signature %r" % signature
            blend_mode = BlendMode(read_fmt("4s", fp)[0])
        sub_type = None
        if is_readable(fp, 4):
            sub_type = read_fmt("I", fp)[0]
        return cls(kind, signature=signature, blend_mode=blend_mode, sub_type=sub_type)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "I", self.kind.value)
        if self.blend_mode:
            if self.signature is None:
                logger.debug(
                    "Signature is missing in SectionDividerSetting, overriding"
                )
                self.signature = b"8BIM"
            written += write_fmt(fp, "4s4s", self.signature, self.blend_mode.value)
            if self.sub_type is not None:
                written += write_fmt(fp, "I", self.sub_type)
        elif self.sub_type is not None:
            logger.debug(
                "Blend mode is missing in SectionDividerSetting, ignoring sub_type"
            )
        return written


@register(Tag.SHEET_COLOR_SETTING)
@define(repr=False, eq=False, order=False)
class SheetColorSetting(ValueElement):
    """
    SheetColorSetting value.

    This setting represents color label in the layers panel in Photoshop UI.

    .. py:attribute:: value
    """

    value: SheetColorType = field(
        default=SheetColorType.NO_COLOR, converter=SheetColorType
    )

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "SheetColorSetting":
        return cls(SheetColorType(*read_fmt("H6x", fp)))

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "H6x", self.value.value)


@register(Tag.SMART_OBJECT_LAYER_DATA1)
@register(Tag.SMART_OBJECT_LAYER_DATA2)
@define(repr=False)
class SmartObjectLayerData(BaseElement):
    """
    VersionedDescriptorBlock structure.

    .. py:attribute:: kind
    .. py:attribute:: version
    .. py:attribute:: data
    """

    kind: bytes = field(default=b"soLD", validator=in_((b"soLD",)))
    version: int = field(default=5, validator=in_((4, 5)))
    data: DescriptorBlock = field(factory=DescriptorBlock)

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "SmartObjectLayerData":
        kind, version = read_fmt("4sI", fp)
        data = DescriptorBlock.read(fp)
        return cls(kind, version, data)

    def write(self, fp: BinaryIO, padding: int = 4, **kwargs: Any) -> int:
        written = write_fmt(fp, "4sI", self.kind, self.version)
        written += self.data.write(fp, padding=1)
        written += write_padding(fp, written, padding)
        return written


@register(Tag.TYPE_TOOL_OBJECT_SETTING)
@define(repr=False)
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

    version: int = 1
    transform: tuple = (0.0,) * 6
    text_version: int = field(default=1, validator=in_((50,)))
    text_data: DescriptorBlock = field(factory=DescriptorBlock)
    warp_version: int = field(default=1, validator=in_((1,)))
    warp: DescriptorBlock = field(factory=DescriptorBlock)
    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "TypeToolObjectSetting":
        version = read_fmt("H", fp)[0]
        transform = read_fmt("6d", fp)
        text_version = read_fmt("H", fp)[0]
        text_data = DescriptorBlock.read(fp)
        # Engine data.
        if b"EngineData" in text_data:
            try:
                engine_data = text_data[b"EngineData"].value
                engine_data = EngineData.frombytes(engine_data)
                text_data[b"EngineData"].value = engine_data
            except Exception:
                logger.warning("Failed to read engine data")
        warp_version = read_fmt("H", fp)[0]
        warp = DescriptorBlock.read(fp)
        left, top, right, bottom = read_fmt("4i", fp)
        return cls(
            version,
            transform,
            text_version,
            text_data,
            warp_version,
            warp,
            left,
            top,
            right,
            bottom,
        )

    def write(self, fp: BinaryIO, padding: int = 4, **kwargs: Any) -> int:
        written = write_fmt(fp, "H6d", self.version, *self.transform)
        written += write_fmt(fp, "H", self.text_version)
        written += self.text_data.write(fp, padding=1)
        written += write_fmt(fp, "H", self.warp_version)
        written += self.warp.write(fp, padding=1)
        written += write_fmt(fp, "4i", self.left, self.top, self.right, self.bottom)
        written += write_padding(fp, written, padding)
        return written


@register(Tag.USER_MASK)
@define(repr=False)
class UserMask(BaseElement):
    """
    UserMask structure.

    .. py:attribute:: color
    .. py:attribute:: opacity
    .. py:attribute:: flag
    """

    color: Color = field(factory=Color)
    opacity: int = 0
    flag: int = 128

    @classmethod
    def read(cls, fp: BinaryIO, **kwargs: Any) -> "UserMask":
        color = Color.read(fp)
        opacity, flag = read_fmt("HBx", fp)
        return cls(color, opacity, flag)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = self.color.write(fp)
        written += write_fmt(fp, "HBx", self.opacity, self.flag)
        return written
