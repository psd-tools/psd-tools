"""
Layer and mask data structures.

This module implements the low-level binary structures for PSD layers and masks,
corresponding to the "Layer and Mask Information" section of PSD files. This is
one of the most complex parts of the PSD format.

Key classes:

- :py:class:`LayerAndMaskInformation`: Top-level container for all layer data
- :py:class:`LayerInfo`: Contains layer records and channel image data
- :py:class:`LayerRecords`: List of individual layer records
- :py:class:`LayerRecord`: Single layer metadata (name, bounds, blend mode, etc.)
- :py:class:`ChannelInfo`: Channel metadata within a layer record
- :py:class:`ChannelImageData`: Compressed pixel data for all channels
- :py:class:`ChannelData`: Single channel's compressed pixel data
- :py:class:`MaskData`: Layer mask parameters
- :py:class:`GlobalLayerMaskInfo`: Document-wide mask settings
- :py:class:`TaggedBlocks`: Extended layer metadata (see :py:mod:`psd_tools.psd.tagged_blocks`)

The layer structure in PSD files is stored as a flat list with implicit hierarchy.
Group boundaries are marked by special layers with ``SectionDivider`` tagged blocks:

- ``BOUNDING_SECTION_DIVIDER``: Marks the start of a group (the layer that opens the group)
- ``OPEN_FOLDER`` or ``CLOSED_FOLDER``: Marks the end of a group (the closing divider layer)
  - ``OPEN_FOLDER``: Group was open in Photoshop UI
  - ``CLOSED_FOLDER``: Group was closed in Photoshop UI

The high-level API (:py:mod:`psd_tools.api`) reconstructs this into a proper
tree structure with parent-child relationships.

Each layer record contains:

1. **Metadata**: Rectangle bounds, blend mode, opacity, flags
2. **Channel info**: List of channels (R, G, B, A, masks, etc.) with byte offsets
3. **Blend ranges**: Advanced blending parameters
4. **Layer name**: Pascal string (legacy, inaccurate for Unicode names)
5. **Tagged blocks**: Extended metadata in key-value format

The channel image data section follows all layer records and contains the actual
compressed pixel data for each channel, referenced by the channel info structures.

Example of reading layer metadata::

    from psd_tools.psd import PSD

    with open('file.psd', 'rb') as f:
        psd = PSD.read(f)

    layer_info = psd.layer_and_mask_information.layer_info
    for record in layer_info.layer_records:
        print(f"Layer: {record.name}")
        print(f"  Bounds: {record.top}, {record.left}, {record.bottom}, {record.right}")
        print(f"  Blend mode: {record.blend_mode}")
        print(f"  Channels: {len(record.channel_info)}")

For most use cases, prefer the high-level :py:class:`~psd_tools.api.layers.Layer`
API which provides easier access to this data.
"""

import io
import logging
from typing import Any, BinaryIO, Optional, TypeVar

from attrs import define, field, astuple

from psd_tools.compression import compress, decompress
from psd_tools.constants import (
    BlendMode,
    ChannelID,
    Clipping,
    Compression,
    GlobalLayerMaskKind,
    Tag,
)
from psd_tools.psd.base import BaseElement, ListElement
from psd_tools.psd.tagged_blocks import TaggedBlocks, register
from psd_tools.psd.bin_utils import (
    is_readable,
    read_fmt,
    read_length_block,
    read_pascal_string,
    write_bytes,
    write_fmt,
    write_length_block,
    write_padding,
    write_pascal_string,
)
from psd_tools.validators import in_, range_

logger = logging.getLogger(__name__)

T_LayerAndMaskInformation = TypeVar(
    "T_LayerAndMaskInformation", bound="LayerAndMaskInformation"
)
T_LayerInfo = TypeVar("T_LayerInfo", bound="LayerInfo")
T_ChannelInfo = TypeVar("T_ChannelInfo", bound="ChannelInfo")
T_LayerFlags = TypeVar("T_LayerFlags", bound="LayerFlags")
T_LayerBlendingRanges = TypeVar("T_LayerBlendingRanges", bound="LayerBlendingRanges")
T_LayerRecords = TypeVar("T_LayerRecords", bound="LayerRecords")
T_LayerRecord = TypeVar("T_LayerRecord", bound="LayerRecord")
T_MaskFlags = TypeVar("T_MaskFlags", bound="MaskFlags")
T_MaskData = TypeVar("T_MaskData", bound="MaskData")
T_MaskParameters = TypeVar("T_MaskParameters", bound="MaskParameters")
T_ChannelImageData = TypeVar("T_ChannelImageData", bound="ChannelImageData")
T_ChannelDataList = TypeVar("T_ChannelDataList", bound="ChannelDataList")
T_ChannelData = TypeVar("T_ChannelData", bound="ChannelData")
T_GlobalLayerMaskInfo = TypeVar("T_GlobalLayerMaskInfo", bound="GlobalLayerMaskInfo")


@define(repr=False)
class LayerAndMaskInformation(BaseElement):
    """
    Layer and mask information section.

    .. py:attribute:: layer_info

        See :py:class:`.LayerInfo`.

    .. py:attribute:: global_layer_mask_info

        See :py:class:`.GlobalLayerMaskInfo`.

    .. py:attribute:: tagged_blocks

        See :py:class:`.TaggedBlocks`.
    """

    layer_info: Optional["LayerInfo"] = None
    global_layer_mask_info: Optional["GlobalLayerMaskInfo"] = None
    tagged_blocks: Optional["TaggedBlocks"] = None

    @classmethod
    def read(
        cls: type[T_LayerAndMaskInformation],
        fp: BinaryIO,
        encoding: str = "macroman",
        version: int = 1,
        **kwargs: Any,
    ) -> T_LayerAndMaskInformation:
        start_pos = fp.tell()
        length = read_fmt(("I", "Q")[version - 1], fp)[0]
        end_pos = fp.tell() + length
        logger.debug(
            "reading layer and mask info, len=%d, offset=%d" % (length, start_pos)
        )
        if length == 0:
            self = cls()
        else:
            self = cls._read_body(fp, end_pos, encoding, version)
        if fp.tell() > end_pos:
            logger.warning(
                "LayerAndMaskInformation is broken: current fp=%d, expected=%d"
                % (fp.tell(), end_pos)
            )
        fp.seek(end_pos, 0)
        return self

    @classmethod
    def _read_body(
        cls: type[T_LayerAndMaskInformation],
        fp: BinaryIO,
        end_pos: int,
        encoding: str,
        version: int,
    ) -> T_LayerAndMaskInformation:
        layer_info = LayerInfo.read(fp, encoding, version)

        global_layer_mask_info = None
        if is_readable(fp, 17) and fp.tell() < end_pos:
            global_layer_mask_info = GlobalLayerMaskInfo.read(fp)

        tagged_blocks = None
        if is_readable(fp):
            # For some reason, global tagged blocks aligns 4 byte
            tagged_blocks = TaggedBlocks.read(
                fp, version=version, padding=4, end_pos=end_pos
            )

        return cls(layer_info, global_layer_mask_info, tagged_blocks)

    def write(
        self,
        fp: BinaryIO,
        encoding: str = "macroman",
        version: int = 1,
        padding: int = 4,
        **kwargs: Any,
    ) -> int:
        def writer(f: BinaryIO) -> int:
            written = self._write_body(f, encoding, version, padding)
            logger.debug("writing layer and mask info, len=%d" % (written))
            return written

        fmt = ("I", "Q")[version - 1]
        return write_length_block(fp, writer, fmt=fmt)

    def _write_body(
        self, fp: BinaryIO, encoding: str, version: int, padding: int
    ) -> int:
        written = 0
        if self.layer_info:
            written += self.layer_info.write(fp, encoding, version, padding)
        if self.global_layer_mask_info:
            written += self.global_layer_mask_info.write(fp)
        if self.tagged_blocks:
            written += self.tagged_blocks.write(fp, version=version, padding=4)
        return written


@define(repr=False)
class LayerInfo(BaseElement):
    """
    High-level organization of the layer information.

    .. py:attribute:: layer_count

        Layer count. If it is a negative number, its absolute value is the
        number of layers and the first alpha channel contains the transparency
        data for the merged result.

    .. py:attribute:: layer_records

        Information about each layer. See :py:class:`.LayerRecords`.

    .. py:attribute:: channel_image_data

        Channel image data. See :py:class:`.ChannelImageData`.
    """

    layer_count: int = 0
    layer_records: "LayerRecords" = field(factory=lambda: LayerRecords())
    channel_image_data: "ChannelImageData" = field(factory=lambda: ChannelImageData())

    @classmethod
    def read(
        cls: type[T_LayerInfo],
        fp: BinaryIO,
        encoding: str = "macroman",
        version: int = 1,
        **kwargs: Any,
    ) -> T_LayerInfo:
        length = read_fmt(("I", "Q")[version - 1], fp)[0]
        logger.debug("reading layer info, len=%d" % length)
        end_pos = fp.tell() + length
        if length == 0:
            self = LayerInfo()
        else:
            self = cls._read_body(fp, encoding, version)
        assert fp.tell() <= end_pos
        fp.seek(end_pos, 0)
        return self  # type: ignore[return-value]

    @classmethod
    def _read_body(
        cls: type[T_LayerInfo], fp: BinaryIO, encoding: str, version: int
    ) -> T_LayerInfo:
        start_pos = fp.tell()
        layer_count = read_fmt("h", fp)[0]
        layer_records = LayerRecords.read(fp, layer_count, encoding, version)
        logger.debug("  read layer records, len=%d" % (fp.tell() - start_pos))
        channel_image_data = ChannelImageData.read(fp, layer_records)
        return cls(
            layer_count=layer_count,
            layer_records=layer_records,
            channel_image_data=channel_image_data,
        )

    def write(
        self,
        fp: BinaryIO,
        encoding: str = "macroman",
        version: int = 1,
        padding: int = 4,
        **kwargs: Any,
    ) -> int:
        def writer(f: BinaryIO) -> int:
            written = self._write_body(f, encoding, version, padding)
            logger.debug("writing layer info, len=%d" % (written))
            return written

        fmt = ("I", "Q")[version - 1]
        if self.layer_count == 0:
            return write_fmt(fp, fmt, 0)
        return write_length_block(fp, writer, fmt=fmt)

    def _write_body(
        self, fp: BinaryIO, encoding: str, version: int, padding: int
    ) -> int:
        start_pos = fp.tell()
        written = write_fmt(fp, "h", self.layer_count)
        if self.layer_records:
            self._update_channel_length()
            written += self.layer_records.write(fp, encoding, version)
        logger.debug("  wrote layer records, len=%d" % (fp.tell() - start_pos))
        if self.channel_image_data:
            written += self.channel_image_data.write(fp)
        # Seems the padding size here is different between Photoshop and GIMP.
        written += write_padding(fp, written, padding)
        return written

    def _update_channel_length(self) -> None:
        if not self.layer_records or not self.channel_image_data:
            return

        for layer, lengths in zip(self.layer_records, self.channel_image_data._lengths):
            for channel_info, length in zip(layer.channel_info, lengths):
                channel_info.length = length


@register(Tag.LAYER_16)
@register(Tag.LAYER_32)
@define(repr=False)
class LayerInfoBlock(LayerInfo):
    """ """

    @classmethod
    def read(
        cls: type[T_LayerInfo],
        fp: BinaryIO,
        encoding: str = "macroman",
        version: int = 1,
        **kwargs: Any,
    ) -> T_LayerInfo:
        return cls._read_body(fp, encoding, version)

    def write(
        self,
        fp: BinaryIO,
        encoding: str = "macroman",
        version: int = 1,
        padding: int = 4,
        **kwargs: Any,
    ) -> int:
        return self._write_body(fp, encoding, version, padding)


@define(repr=False)
class ChannelInfo(BaseElement):
    """
    Channel information.

    .. py:attribute:: id

        Channel ID: 0 = red, 1 = green, etc.; -1 = transparency mask; -2 =
        user supplied layer mask, -3 real user supplied layer mask (when both
        a user mask and a vector mask are present). See
        :py:class:`~psd_tools.constants.ChannelID`.

    .. py:attribute:: length

        Length of the corresponding channel data.
    """

    id: ChannelID = field(
        default=ChannelID.CHANNEL_0, converter=ChannelID, validator=in_(ChannelID)
    )
    length: int = 0

    @classmethod
    def read(
        cls: type[T_ChannelInfo], fp: BinaryIO, version: int = 1, **kwargs: Any
    ) -> T_ChannelInfo:
        values = read_fmt(("hI", "hQ")[version - 1], fp)
        return cls(id=values[0], length=values[1])

    def write(self, fp: BinaryIO, version: int = 1, **kwargs: Any) -> int:
        return write_fmt(fp, ("hI", "hQ")[version - 1], *astuple(self))


@define(repr=False)
class LayerFlags(BaseElement):
    """
    Layer flags.

    Note there are undocumented flags. Maybe photoshop version.

    .. py:attribute:: transparency_protected
    .. py:attribute:: visible
    .. py:attribute:: pixel_data_irrelevant
    """

    transparency_protected: bool = False
    visible: bool = True
    obsolete: bool = field(default=False, repr=False)
    photoshop_v5_later: bool = field(default=True, repr=False)
    pixel_data_irrelevant: bool = False
    undocumented_1: bool = field(default=False, repr=False)
    undocumented_2: bool = field(default=False, repr=False)
    undocumented_3: bool = field(default=False, repr=False)

    @classmethod
    def read(cls: type[T_LayerFlags], fp: BinaryIO, **kwargs: Any) -> T_LayerFlags:
        flags = read_fmt("B", fp)[0]
        return cls(
            bool(flags & 1),
            not bool(flags & 2),  # why "not"?
            bool(flags & 4),
            bool(flags & 8),
            bool(flags & 16),
            bool(flags & 32),
            bool(flags & 64),
            bool(flags & 128),
        )

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        flags = (
            (self.transparency_protected * 1)
            | ((not self.visible) * 2)
            | (self.obsolete * 4)
            | (self.photoshop_v5_later * 8)
            | (self.pixel_data_irrelevant * 16)
            | (self.undocumented_1 * 32)
            | (self.undocumented_2 * 64)
            | (self.undocumented_3 * 128)
        )
        return write_fmt(fp, "B", flags)


@define(repr=False)
class LayerBlendingRanges(BaseElement):
    """
    Layer blending ranges.

    All ranges contain 2 black values followed by 2 white values.

    .. py:attribute:: composite_ranges

        List of composite gray blend source and destination ranges.

    .. py:attribute:: channel_ranges

        List of channel source and destination ranges.
    """

    composite_ranges: list[tuple[int, int]] = field(
        factory=lambda: [(0, 65535), (0, 65535)]
    )
    channel_ranges: list[list[tuple[int, int]]] = field(
        factory=lambda: [
            [(0, 65535), (0, 65535)],
            [(0, 65535), (0, 65535)],
            [(0, 65535), (0, 65535)],
            [(0, 65535), (0, 65535)],
        ]
    )

    @classmethod
    def read(
        cls: type[T_LayerBlendingRanges], fp: BinaryIO, **kwargs: Any
    ) -> T_LayerBlendingRanges:
        data = read_length_block(fp)
        if len(data) == 0:
            return cls(None, None)  # type: ignore[arg-type]

        with io.BytesIO(data) as f:
            return cls._read_body(f)

    @classmethod
    def _read_body(
        cls: type[T_LayerBlendingRanges], fp: BinaryIO
    ) -> T_LayerBlendingRanges:
        def read_channel_range(f: BinaryIO) -> list[tuple[int, int]]:
            values = read_fmt("4H", f)
            return [values[0:2], values[2:4]]  # type: ignore[return-value]

        composite_ranges = read_channel_range(fp)
        channel_ranges = []
        while is_readable(fp, 8):
            channel_ranges.append(read_channel_range(fp))
        return cls(composite_ranges, channel_ranges)  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_length_block(fp, lambda f: self._write_body(f))

    def _write_body(self, fp: BinaryIO) -> int:
        written = 0
        if self.composite_ranges is not None:
            for x in self.composite_ranges:
                written += write_fmt(fp, "2H", *x)
        if self.channel_ranges is not None:
            for channel in self.channel_ranges:
                for x in channel:
                    written += write_fmt(fp, "2H", *x)
        return written


class LayerRecords(ListElement):
    """
    List of layer records. See :py:class:`.LayerRecord`.
    """

    @classmethod
    def read(  # type: ignore[override]
        cls: type[T_LayerRecords],
        fp: BinaryIO,
        layer_count: int,
        encoding: str = "macroman",
        version: int = 1,
        **kwargs: Any,
    ) -> T_LayerRecords:  # type: ignore[override]
        items = []
        for _ in range(abs(layer_count)):
            items.append(LayerRecord.read(fp, encoding, version))
        return cls(items)  # type: ignore[arg-type]


@define(repr=False)
class LayerRecord(BaseElement):
    """
    Layer record.

    .. py:attribute:: top

        Top position.

    .. py:attribute:: left

        Left position.

    .. py:attribute:: bottom

        Bottom position.

    .. py:attribute:: right

        Right position.

    .. py:attribute:: channel_info

        List of :py:class:`.ChannelInfo`.

    .. py:attribute:: signature

        Blend mode signature ``b'8BIM'``.

    .. py:attribute:: blend_mode

        Blend mode key. See :py:class:`~psd_tools.constants.BlendMode`.

    .. py:attribute:: opacity

        Opacity, 0 = transparent, 255 = opaque.

    .. py:attribute:: clipping

        Clipping, 0 = base, 1 = non-base. See
        :py:class:`~psd_tools.constants.Clipping`.

    .. py:attribute:: flags

        See :py:class:`.LayerFlags`.

    .. py:attribute:: mask_data

        :py:class:`.MaskData` or None.

    .. py:attribute:: blending_ranges

        See :py:class:`~psd_tools.constants.LayerBlendingRanges`.

    .. py:attribute:: name

        Layer name.

    .. py:attribute:: tagged_blocks

        See :py:class:`.TaggedBlocks`.
    """

    top: int = 0
    left: int = 0
    bottom: int = 0
    right: int = 0
    channel_info: list[ChannelInfo] = field(factory=list)
    signature: bytes = field(default=b"8BIM", repr=False, validator=in_((b"8BIM",)))
    blend_mode: BlendMode = field(
        default=BlendMode.NORMAL, converter=BlendMode, validator=in_(BlendMode)
    )
    opacity: int = field(default=255, validator=range_(0, 255))
    clipping: Clipping = field(
        default=Clipping.BASE, converter=Clipping, validator=in_(Clipping)
    )
    flags: LayerFlags = field(factory=LayerFlags)
    mask_data: object = None
    blending_ranges: LayerBlendingRanges = field(factory=LayerBlendingRanges)
    name: str = ""
    tagged_blocks: TaggedBlocks = field(factory=TaggedBlocks)

    @classmethod
    def read(
        cls: type[T_LayerRecord],
        fp: BinaryIO,
        encoding: str = "macroman",
        version: int = 1,
        **kwargs: Any,
    ) -> T_LayerRecord:
        start_pos = fp.tell()
        top, left, bottom, right, num_channels = read_fmt("4iH", fp)
        channel_info = [ChannelInfo.read(fp, version) for i in range(num_channels)]
        signature, blend_mode, opacity, clipping = read_fmt("4s4sBB", fp)
        flags = LayerFlags.read(fp)

        data = read_length_block(fp, fmt="xI")
        logger.debug("  read layer record, len=%d" % (fp.tell() - start_pos))
        with io.BytesIO(data) as f:
            mask_data, blending_ranges, name, tagged_blocks = cls._read_extra(
                f, encoding, version
            )
            self = cls(
                top=top,
                left=left,
                bottom=bottom,
                right=right,
                channel_info=channel_info,
                signature=signature,
                blend_mode=blend_mode,
                opacity=opacity,
                clipping=clipping,
                flags=flags,
                mask_data=mask_data,
                blending_ranges=blending_ranges,
                name=name,
                tagged_blocks=tagged_blocks,
            )

        # with io.BytesIO() as f:
        #     self._write_extra(f, encoding, version)
        #     assert data == f.getvalue()

        return self

    @classmethod
    def _read_extra(
        cls, fp: BinaryIO, encoding: str, version: int
    ) -> tuple[Optional["MaskData"], LayerBlendingRanges, str, TaggedBlocks]:
        mask_data = MaskData.read(fp)
        blending_ranges = LayerBlendingRanges.read(fp)
        name = read_pascal_string(fp, encoding, padding=4)
        tagged_blocks = TaggedBlocks.read(fp, version=version, padding=1)
        return mask_data, blending_ranges, name, tagged_blocks

    def write(
        self, fp: BinaryIO, encoding: str = "macroman", version: int = 1, **kwargs: Any
    ) -> int:
        start_pos = fp.tell()
        written = write_fmt(
            fp,
            "4iH",
            self.top,
            self.left,
            self.bottom,
            self.right,
            len(self.channel_info),
        )
        written += sum(c.write(fp, version) for c in self.channel_info)
        written += write_fmt(
            fp,
            "4s4sBB",
            self.signature,
            self.blend_mode.value,
            self.opacity,
            self.clipping.value,
        )
        written += self.flags.write(fp)

        def writer(f: BinaryIO) -> int:
            written = self._write_extra(f, encoding, version)
            logger.debug("  wrote layer record, len=%d" % (fp.tell() - start_pos))
            return written

        written += write_length_block(fp, writer, fmt="xI")
        return written

    def _write_extra(self, fp: BinaryIO, encoding: str, version: int) -> int:
        written = 0
        if self.mask_data and hasattr(self.mask_data, "write"):
            written += self.mask_data.write(fp)  # type: ignore[attr-defined]
        else:
            written += write_fmt(fp, "I", 0)

        written += self.blending_ranges.write(fp)
        written += write_pascal_string(fp, self.name, encoding, padding=4)
        written += self.tagged_blocks.write(fp, version, padding=1)
        written += write_padding(fp, written, 2)
        return written

    @property
    def width(self) -> int:
        """Width of the layer."""
        return max(self.right - self.left, 0)

    @property
    def height(self) -> int:
        """Height of the layer."""
        return max(self.bottom - self.top, 0)

    @property
    def channel_sizes(self) -> list[tuple[int, int]]:
        """List of channel sizes: [(width, height)]."""
        sizes = []
        for channel in self.channel_info:
            if channel.id == ChannelID.USER_LAYER_MASK:
                sizes.append((self.mask_data.width, self.mask_data.height))  # type: ignore[attr-defined]
            elif channel.id == ChannelID.REAL_USER_LAYER_MASK:
                sizes.append((self.mask_data.real_width, self.mask_data.real_height))  # type: ignore[attr-defined]
            else:
                sizes.append((self.width, self.height))
        return sizes


@define(repr=False)
class MaskFlags(BaseElement):
    """
    Mask flags.

    .. py:attribute:: pos_relative_to_layer

        Position relative to layer.

    .. py:attribute:: mask_disabled

        Layer mask disabled.

    .. py:attribute:: invert_mask

        Invert layer mask when blending (Obsolete).

    .. py:attribute:: user_mask_from_render

        The user mask actually came from rendering other data.

    .. py:attribute:: parameters_applied

        The user and/or vector masks have parameters applied to them.
    """

    pos_relative_to_layer: bool = False
    mask_disabled: bool = False
    invert_mask: bool = False
    user_mask_from_render: bool = False
    parameters_applied: bool = False
    undocumented_1: bool = field(default=False, repr=False)
    undocumented_2: bool = field(default=False, repr=False)
    undocumented_3: bool = field(default=False, repr=False)

    @classmethod
    def read(cls: type[T_MaskFlags], fp: BinaryIO, **kwargs: Any) -> T_MaskFlags:
        flags = read_fmt("B", fp)[0]
        return cls(
            bool(flags & 1),
            bool(flags & 2),
            bool(flags & 4),
            bool(flags & 8),
            bool(flags & 16),
            bool(flags & 32),
            bool(flags & 64),
            bool(flags & 128),
        )

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        flags = (
            (self.pos_relative_to_layer * 1)
            | (self.mask_disabled * 2)
            | (self.invert_mask * 4)
            | (self.user_mask_from_render * 8)
            | (self.parameters_applied * 16)
            | (self.undocumented_1 * 32)
            | (self.undocumented_2 * 64)
            | (self.undocumented_3 * 128)
        )
        return write_fmt(fp, "B", flags)


@define(repr=False)
class MaskData(BaseElement):
    """
    Mask data.

    Real user mask is a final composite mask of vector and pixel masks.

    .. py:attribute:: top

        Top position.

    .. py:attribute:: left

        Left position.

    .. py:attribute:: bottom

        Bottom position.

    .. py:attribute:: right

        Right position.

    .. py:attribute:: background_color

        Default color. 0 or 255.

    .. py:attribute:: flags

        See :py:class:`.MaskFlags`.

    .. py:attribute:: parameters

        :py:class:`.MaskParameters` or None.

    .. py:attribute:: real_flags

        Real user mask flags. See :py:class:`.MaskFlags`.

    .. py:attribute:: real_background_color

        Real user mask background. 0 or 255.

    .. py:attribute:: real_top

        Top position of real user mask.

    .. py:attribute:: real_left

        Left position of real user mask.

    .. py:attribute:: real_bottom

        Bottom position of real user mask.

    .. py:attribute:: real_right

        Right position of real user mask.
    """

    top: int = 0
    left: int = 0
    bottom: int = 0
    right: int = 0
    background_color: int = 0
    flags: MaskFlags = field(factory=MaskFlags)
    parameters: object = None
    real_flags: object = None
    real_background_color: Optional[int] = None
    real_top: Optional[int] = None
    real_left: Optional[int] = None
    real_bottom: Optional[int] = None
    real_right: Optional[int] = None

    @classmethod
    def read(cls: type[T_MaskData], fp: BinaryIO, **kwargs: Any) -> T_MaskData:  # type: ignore[return]
        data = read_length_block(fp)
        if len(data) == 0:
            return None  # type: ignore[return-value]

        with io.BytesIO(data) as f:
            return cls._read_body(f, len(data))

    @classmethod
    def _read_body(cls: type[T_MaskData], fp: BinaryIO, length: int) -> T_MaskData:
        top, left, bottom, right, background_color = read_fmt("4iB", fp)
        flags = MaskFlags.read(fp)

        # Order is based on tests. The specification is messed up here...

        # if length == 20:
        #     read_fmt('2x', fp)
        #     return cls(top, left, bottom, right, background_color, flags)

        real_flags, real_background_color = None, None
        real_top, real_left, real_bottom, real_right = None, None, None, None
        if length >= 36:
            real_flags = MaskFlags.read(fp)
            real_background_color = read_fmt("B", fp)[0]
            real_top, real_left, real_bottom, real_right = read_fmt("4i", fp)

        parameters = None
        if flags.parameters_applied:
            parameters = MaskParameters.read(fp)

        # logger.debug('    skipping %d' % (len(fp.read())))
        return cls(
            top=top,
            left=left,
            bottom=bottom,
            right=right,
            background_color=background_color,
            flags=flags,
            parameters=parameters,
            real_flags=real_flags,
            real_background_color=real_background_color,
            real_top=real_top,
            real_left=real_left,
            real_bottom=real_bottom,
            real_right=real_right,
        )

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_length_block(fp, lambda f: self._write_body(f))

    def _write_body(self, fp: BinaryIO) -> int:
        written = write_fmt(
            fp,
            "4iB",
            self.top,
            self.left,
            self.bottom,
            self.right,
            self.background_color,
        )
        written += self.flags.write(fp)

        # if self.real_flags is None and self.parameters is None:
        #     written += write_fmt(fp, '2x')
        #     assert written == 20

        if self.real_flags and hasattr(self.real_flags, "write"):
            written += self.real_flags.write(fp)  # type: ignore[attr-defined]
            written += write_fmt(
                fp,
                "B4i",
                self.real_background_color,
                self.real_top,
                self.real_left,
                self.real_bottom,
                self.real_right,
            )

        if (
            self.flags.parameters_applied
            and self.parameters
            and hasattr(self.parameters, "write")
        ):
            written += self.parameters.write(fp)  # type: ignore[attr-defined]

        written += write_padding(fp, written, 4)
        return written

    @property
    def width(self) -> int:
        """Width of the mask."""
        return max(self.right - self.left, 0)

    @property
    def height(self) -> int:
        """Height of the mask."""
        return max(self.bottom - self.top, 0)

    @property
    def real_width(self) -> int:
        """Width of real user mask."""
        return max((self.real_right or 0) - (self.real_left or 0), 0)

    @property
    def real_height(self) -> int:
        """Height of real user mask."""
        return max((self.real_bottom or 0) - (self.real_top or 0), 0)


@define(repr=False)
class MaskParameters(BaseElement):
    """
    Mask parameters.

    .. py:attribute:: user_mask_density
    .. py:attribute:: user_mask_feather
    .. py:attribute:: vector_mask_density
    .. py:attribute:: vector_mask_feather
    """

    user_mask_density: Optional[int] = None
    user_mask_feather: Optional[float] = None
    vector_mask_density: Optional[int] = None
    vector_mask_feather: Optional[float] = None

    @classmethod
    def read(
        cls: type[T_MaskParameters], fp: BinaryIO, **kwargs: Any
    ) -> T_MaskParameters:
        parameters = read_fmt("B", fp)[0]
        return cls(
            read_fmt("B", fp)[0] if bool(parameters & 1) else None,
            read_fmt("d", fp)[0] if bool(parameters & 2) else None,
            read_fmt("B", fp)[0] if bool(parameters & 4) else None,
            read_fmt("d", fp)[0] if bool(parameters & 8) else None,
        )

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = 0
        written += write_fmt(
            fp,
            "B",
            (
                (1 if self.user_mask_density is not None else 0)
                | (2 if self.user_mask_feather is not None else 0)
                | (4 if self.vector_mask_density is not None else 0)
                | (8 if self.vector_mask_feather is not None else 0)
            ),
        )
        if self.user_mask_density is not None:
            written += write_fmt(fp, "B", self.user_mask_density)
        if self.user_mask_feather is not None:
            written += write_fmt(fp, "d", self.user_mask_feather)
        if self.vector_mask_density is not None:
            written += write_fmt(fp, "B", self.vector_mask_density)
        if self.vector_mask_feather is not None:
            written += write_fmt(fp, "d", self.vector_mask_feather)
        return written


class ChannelImageData(ListElement):
    """
    List of channel data list.

    This size of this list corresponds to the size of
    :py:class:`LayerRecords`. Each item corresponds to the channels of each
    layer.

    See :py:class:`.ChannelDataList`.
    """

    @classmethod
    def read(
        cls: type[T_ChannelImageData],
        fp: BinaryIO,
        layer_records: Optional["LayerRecords"] = None,
        **kwargs: Any,
    ) -> T_ChannelImageData:
        start_pos = fp.tell()
        items = []
        if layer_records:
            for layer in layer_records:
                items.append(ChannelDataList.read(fp, layer.channel_info))
        logger.debug("  read channel image data, len=%d" % (fp.tell() - start_pos))
        return cls(items)  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        start_pos = fp.tell()
        written = sum(item.write(fp) for item in self)
        logger.debug("  wrote channel image data, len=%d" % (fp.tell() - start_pos))
        return written

    @property
    def _lengths(self) -> list[list[int]]:
        """List of layer channel lengths."""
        return [item._lengths for item in self]


class ChannelDataList(ListElement):
    """
    List of channel image data, corresponding to each color or alpha.

    See :py:class:`.ChannelData`.
    """

    @classmethod
    def read(  # type: ignore[override]
        cls: type[T_ChannelDataList],
        fp: BinaryIO,
        channel_info: list["ChannelInfo"],
        **kwargs: Any,
    ) -> T_ChannelDataList:
        items = []
        for c in channel_info:
            items.append(ChannelData.read(fp, c.length - 2, **kwargs))
        return cls(items)  # type: ignore[arg-type]

    @property
    def _lengths(self) -> list[int]:
        """List of channel lengths."""
        return [item._length for item in self]


@define(repr=False)
class ChannelData(BaseElement):
    """
    Channel data.

    .. py:attribute:: compression

        Compression type. See :py:class:`~psd_tools.constants.Compression`.

    .. py:attribute:: data

        Data.
    """

    compression: Compression = field(
        default=Compression.RAW, converter=Compression, validator=in_(Compression)
    )
    data: bytes = b""

    @classmethod
    def read(
        cls: type[T_ChannelData], fp: BinaryIO, length: int = 0, **kwargs: Any
    ) -> T_ChannelData:
        compression = Compression(read_fmt("H", fp)[0])
        data = fp.read(length)
        return cls(compression=compression, data=data)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "H", self.compression.value)
        written += write_bytes(fp, self.data)
        # written += write_padding(fp, written, 2)  # Seems no padding here.
        return written

    def get_data(self, width: int, height: int, depth: int, version: int = 1) -> bytes:
        """Get decompressed channel data.

        :param width: width.
        :param height: height.
        :param depth: bit depth of the pixel.
        :param version: psd file version.
        :rtype: bytes
        """
        return decompress(self.data, self.compression, width, height, depth, version)

    def set_data(
        self, data: bytes, width: int, height: int, depth: int, version: int = 1
    ) -> int:
        """Set raw channel data and compress to store.

        :param data: raw data bytes to write.
        :param compression: compression type,
            see :py:class:`~psd_tools.constants.Compression`.
        :param width: width.
        :param height: height.
        :param depth: bit depth of the pixel.
        :param version: psd file version.
        """
        self.data = compress(data, self.compression, width, height, depth, version)
        return len(self.data)

    @property
    def _length(self) -> int:
        """Length of channel data block."""
        return 2 + len(self.data)


@define(repr=False)
class GlobalLayerMaskInfo(BaseElement):
    """
    Global mask information.

    .. py:attribute:: overlay_color

        Overlay color space (undocumented) and color components.

    .. py:attribute:: opacity

        Opacity. 0 = transparent, 100 = opaque.

    .. py:attribute:: kind

        Kind.
        0 = Color selected--i.e. inverted;
        1 = Color protected;
        128 = use value stored per layer. This value is preferred. The others
        are for backward compatibility with beta versions.
    """

    overlay_color: Optional[list[int]] = None
    opacity: int = 0
    kind: GlobalLayerMaskKind = field(
        default=GlobalLayerMaskKind.PER_LAYER,
        converter=GlobalLayerMaskKind,
        validator=in_(GlobalLayerMaskKind),
    )

    @classmethod
    def read(
        cls: type[T_GlobalLayerMaskInfo], fp: BinaryIO, **kwargs: Any
    ) -> T_GlobalLayerMaskInfo:
        pos = fp.tell()
        data = read_length_block(fp)  # fmt?
        logger.debug("reading global layer mask info, len=%d" % (len(data)))
        if len(data) == 0:
            return cls(overlay_color=None)
        elif len(data) < 13:
            logger.warning(
                "global layer mask info is broken, expected 13 bytes but found"
                " only %d" % (len(data))
            )
            fp.seek(pos)
            return cls(overlay_color=None)

        with io.BytesIO(data) as f:
            return cls._read_body(f)

    @classmethod
    def _read_body(
        cls: type[T_GlobalLayerMaskInfo], fp: BinaryIO
    ) -> T_GlobalLayerMaskInfo:
        overlay_color = list(read_fmt("5H", fp))
        opacity, kind = read_fmt("HB", fp)
        return cls(overlay_color, opacity, kind)

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_length_block(fp, lambda f: self._write_body(f))

    def _write_body(self, fp: BinaryIO) -> int:
        written = 0
        if self.overlay_color is not None:
            written = write_fmt(fp, "5H", *self.overlay_color)
            written += write_fmt(fp, "HB", self.opacity, self.kind.value)
            written += write_padding(fp, written, 4)
        logger.debug("writing global layer mask info, len=%d" % (written))
        return written
