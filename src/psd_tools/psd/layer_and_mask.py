"""
Layer and mask data structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import io
import logging

from psd_tools.psd.base import BaseElement, ListElement
from psd_tools.psd.tagged_blocks import TaggedBlocks, register
from psd_tools.compression import compress, decompress
from psd_tools.validators import in_, range_
from psd_tools.constants import (
    BlendMode, Clipping, Compression, ChannelID, GlobalLayerMaskKind, Tag
)
from psd_tools.utils import (
    read_fmt, write_fmt, read_pascal_string, write_pascal_string,
    read_length_block, write_length_block, is_readable, write_padding,
    write_bytes
)

logger = logging.getLogger(__name__)


@attr.s(repr=False, slots=True)
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
    layer_info = attr.ib(default=None)
    global_layer_mask_info = attr.ib(default=None)
    tagged_blocks = attr.ib(default=None)

    @classmethod
    def read(cls, fp, encoding='macroman', version=1):
        start_pos = fp.tell()
        length = read_fmt(('I', 'Q')[version - 1], fp)[0]
        end_pos = fp.tell() + length
        logger.debug(
            'reading layer and mask info, len=%d, offset=%d' %
            (length, start_pos)
        )
        if length == 0:
            self = cls()
        else:
            self = cls._read_body(fp, end_pos, encoding, version)
        assert fp.tell() <= end_pos
        fp.seek(end_pos, 0)
        return self

    @classmethod
    def _read_body(cls, fp, end_pos, encoding, version):
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

    def write(self, fp, encoding='macroman', version=1, padding=4):
        def writer(f):
            written = self._write_body(f, encoding, version, padding)
            logger.debug('writing layer and mask info, len=%d' % (written))
            return written

        fmt = ('I', 'Q')[version - 1]
        return write_length_block(fp, writer, fmt=fmt)

    def _write_body(self, fp, encoding, version, padding):
        written = 0
        if self.layer_info:
            written += self.layer_info.write(fp, encoding, version, padding)
        if self.global_layer_mask_info:
            written += self.global_layer_mask_info.write(fp)
        if self.tagged_blocks:
            written += self.tagged_blocks.write(fp, version=version, padding=4)
        return written


@attr.s(repr=False, slots=True)
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
    layer_count = attr.ib(default=0, type=int)
    layer_records = attr.ib(default=None)
    channel_image_data = attr.ib(default=None)

    @classmethod
    def read(cls, fp, encoding='macroman', version=1):
        length = read_fmt(('I', 'Q')[version - 1], fp)[0]
        logger.debug('reading layer info, len=%d' % length)
        end_pos = fp.tell() + length
        if length == 0:
            self = LayerInfo()
        else:
            self = cls._read_body(fp, encoding, version)
        assert fp.tell() <= end_pos
        fp.seek(end_pos, 0)
        return self

    @classmethod
    def _read_body(cls, fp, encoding, version):
        start_pos = fp.tell()
        layer_count = read_fmt('h', fp)[0]
        layer_records = LayerRecords.read(fp, layer_count, encoding, version)
        logger.debug('  read layer records, len=%d' % (fp.tell() - start_pos))
        channel_image_data = ChannelImageData.read(fp, layer_records)
        return cls(layer_count, layer_records, channel_image_data)

    def write(self, fp, encoding='macroman', version=1, padding=4):
        def writer(f):
            written = self._write_body(f, encoding, version, padding)
            logger.debug('writing layer info, len=%d' % (written))
            return written

        fmt = ('I', 'Q')[version - 1]
        if self.layer_count == 0:
            return write_fmt(fp, fmt, 0)
        return write_length_block(fp, writer, fmt=fmt)

    def _write_body(self, fp, encoding, version, padding):
        start_pos = fp.tell()
        written = write_fmt(fp, 'h', self.layer_count)
        if self.layer_records:
            self._update_channel_length()
            written += self.layer_records.write(fp, encoding, version)
        logger.debug('  wrote layer records, len=%d' % (fp.tell() - start_pos))
        if self.channel_image_data:
            written += self.channel_image_data.write(fp)
        # Seems the padding size here is different between Photoshop and GIMP.
        written += write_padding(fp, written, padding)
        return written

    def _update_channel_length(self):
        if not self.layer_records or not self.channel_image_data:
            return

        for layer, lengths in zip(
            self.layer_records, self.channel_image_data._lengths
        ):
            for channel_info, length in zip(layer.channel_info, lengths):
                channel_info.length = length


@register(Tag.LAYER_16)
@register(Tag.LAYER_32)
@attr.s(repr=False)
class LayerInfoBlock(LayerInfo):
    """
    """

    @classmethod
    def read(cls, fp, encoding='macroman', version=1, **kwargs):
        return cls._read_body(fp, encoding, version)

    def write(self, fp, encoding='macroman', version=1, padding=4, **kwargs):
        return self._write_body(fp, encoding, version, padding)


@attr.s(repr=False, slots=True)
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
    id = attr.ib(
        default=ChannelID.CHANNEL_0,
        converter=ChannelID,
        validator=in_(ChannelID)
    )
    length = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp, version=1):
        return cls(*read_fmt(('hI', 'hQ')[version - 1], fp))

    def write(self, fp, version=1):
        return write_fmt(fp, ('hI', 'hQ')[version - 1], *attr.astuple(self))


@attr.s(repr=False, slots=True)
class LayerFlags(BaseElement):
    """
    Layer flags.

    Note there are undocumented flags. Maybe photoshop version.

    .. py:attribute:: transparency_protected
    .. py:attribute:: visible
    .. py:attribute:: pixel_data_irrelevant
    """
    transparency_protected = attr.ib(default=False, type=bool)
    visible = attr.ib(default=True, type=bool)
    obsolete = attr.ib(default=False, type=bool, repr=False)
    photoshop_v5_later = attr.ib(default=True, type=bool, repr=False)
    pixel_data_irrelevant = attr.ib(default=False, type=bool)
    undocumented_1 = attr.ib(default=False, type=bool, repr=False)
    undocumented_2 = attr.ib(default=False, type=bool, repr=False)
    undocumented_3 = attr.ib(default=False, type=bool, repr=False)

    @classmethod
    def read(cls, fp):
        flags = read_fmt('B', fp)[0]
        return cls(
            bool(flags & 1),
            not bool(flags & 2),  # why "not"?
            bool(flags & 4),
            bool(flags & 8),
            bool(flags & 16),
            bool(flags & 32),
            bool(flags & 64),
            bool(flags & 128)
        )

    def write(self, fp):
        flags = ((self.transparency_protected * 1) | ((not self.visible) * 2) |
                 (self.obsolete * 4) | (self.photoshop_v5_later * 8) |
                 (self.pixel_data_irrelevant * 16) |
                 (self.undocumented_1 * 32)
                 | (self.undocumented_2 * 64) | (self.undocumented_3 * 128))
        return write_fmt(fp, 'B', flags)


@attr.s(repr=False, slots=True)
class LayerBlendingRanges(BaseElement):
    """
    Layer blending ranges.

    All ranges contain 2 black values followed by 2 white values.

    .. py:attribute:: composite_ranges

        List of composite gray blend source and destination ranges.

    .. py:attribute:: channel_ranges

        List of channel source and destination ranges.
    """
    composite_ranges = attr.ib(factory=lambda: [(0, 65535), (0, 65535)], )
    channel_ranges = attr.ib(
        factory=lambda: [
            [(0, 65535), (0, 65535)],
            [(0, 65535), (0, 65535)],
            [(0, 65535), (0, 65535)],
            [(0, 65535), (0, 65535)],
        ],
    )

    @classmethod
    def read(cls, fp):
        data = read_length_block(fp)
        if len(data) == 0:
            return cls(None, None)

        with io.BytesIO(data) as f:
            return cls._read_body(f)

    @classmethod
    def _read_body(cls, fp):
        def read_channel_range(f):
            values = read_fmt("4H", f)
            return [values[0:2], values[2:4]]

        composite_ranges = read_channel_range(fp)
        channel_ranges = []
        while is_readable(fp, 8):
            channel_ranges.append(read_channel_range(fp))
        return cls(composite_ranges, channel_ranges)

    def write(self, fp):
        return write_length_block(fp, lambda f: self._write_body(f))

    def _write_body(self, fp):
        written = 0
        if self.composite_ranges is not None:
            for x in self.composite_ranges:
                written += write_fmt(fp, '2H', *x)
        if self.channel_ranges is not None:
            for channel in self.channel_ranges:
                for x in channel:
                    written += write_fmt(fp, '2H', *x)
        return written


class LayerRecords(ListElement):
    """
    List of layer records. See :py:class:`.LayerRecord`.
    """

    @classmethod
    def read(cls, fp, layer_count, encoding='macroman', version=1):
        items = []
        for idx in range(abs(layer_count)):
            items.append(LayerRecord.read(fp, encoding, version))
        return cls(items)


@attr.s(repr=False, slots=True)
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
    top = attr.ib(default=0, type=int)
    left = attr.ib(default=0, type=int)
    bottom = attr.ib(default=0, type=int)
    right = attr.ib(default=0, type=int)
    channel_info = attr.ib(factory=list)
    signature = attr.ib(
        default=b'8BIM', repr=False, type=bytes, validator=in_((b'8BIM', ))
    )
    blend_mode = attr.ib(
        default=BlendMode.NORMAL,
        converter=BlendMode,
        validator=in_(BlendMode)
    )
    opacity = attr.ib(default=255, type=int, validator=range_(0, 255))
    clipping = attr.ib(
        default=Clipping.BASE, converter=Clipping, validator=in_(Clipping)
    )
    flags = attr.ib(factory=LayerFlags)
    mask_data = attr.ib(default=None)
    blending_ranges = attr.ib(factory=LayerBlendingRanges)
    name = attr.ib(default='', type=str)
    tagged_blocks = attr.ib(factory=TaggedBlocks)

    @classmethod
    def read(cls, fp, encoding='macroman', version=1):
        start_pos = fp.tell()
        top, left, bottom, right, num_channels = read_fmt('4iH', fp)
        channel_info = [
            ChannelInfo.read(fp, version) for i in range(num_channels)
        ]
        signature, blend_mode, opacity, clipping = read_fmt('4s4sBB', fp)
        flags = LayerFlags.read(fp)

        data = read_length_block(fp, fmt='xI')
        logger.debug('  read layer record, len=%d' % (fp.tell() - start_pos))
        with io.BytesIO(data) as f:
            self = cls(
                top, left, bottom, right, channel_info, signature,
                blend_mode, opacity, clipping, flags,
                *cls._read_extra(f, encoding, version)
            )

        # with io.BytesIO() as f:
        #     self._write_extra(f, encoding, version)
        #     assert data == f.getvalue()

        return self

    @classmethod
    def _read_extra(cls, fp, encoding, version):
        mask_data = MaskData.read(fp)
        blending_ranges = LayerBlendingRanges.read(fp)
        name = read_pascal_string(fp, encoding, padding=4)
        tagged_blocks = TaggedBlocks.read(fp, version=version, padding=1)
        return mask_data, blending_ranges, name, tagged_blocks

    def write(self, fp, encoding='macroman', version=1):
        start_pos = fp.tell()
        written = write_fmt(
            fp, '4iH', self.top, self.left, self.bottom, self.right,
            len(self.channel_info)
        )
        written += sum(c.write(fp, version) for c in self.channel_info)
        written += write_fmt(
            fp, '4s4sBB', self.signature, self.blend_mode.value, self.opacity,
            self.clipping.value
        )
        written += self.flags.write(fp)

        def writer(f):
            written = self._write_extra(f, encoding, version)
            logger.debug(
                '  wrote layer record, len=%d' % (fp.tell() - start_pos)
            )
            return written

        written += write_length_block(fp, writer, fmt='xI')
        return written

    def _write_extra(self, fp, encoding, version):
        written = 0
        if self.mask_data:
            written += self.mask_data.write(fp)
        else:
            written += write_fmt(fp, 'I', 0)

        written += self.blending_ranges.write(fp)
        written += write_pascal_string(fp, self.name, encoding, padding=4)
        written += self.tagged_blocks.write(fp, version, padding=1)
        written += write_padding(fp, written, 2)
        return written

    @property
    def width(self):
        """Width of the layer."""
        return max(self.right - self.left, 0)

    @property
    def height(self):
        """Height of the layer."""
        return max(self.bottom - self.top, 0)

    @property
    def channel_sizes(self):
        """List of channel sizes: [(width, height)].
        """
        sizes = []
        for channel in self.channel_info:
            if channel.id == ChannelID.USER_LAYER_MASK:
                sizes.append((self.mask_data.width, self.mask_data.height))
            elif channel.id == ChannelID.REAL_USER_LAYER_MASK:
                sizes.append(
                    (self.mask_data.real_width, self.mask_data.real_height)
                )
            else:
                sizes.append((self.width, self.height))
        return sizes


@attr.s(repr=False, slots=True)
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
    pos_relative_to_layer = attr.ib(default=False, type=bool)
    mask_disabled = attr.ib(default=False, type=bool)
    invert_mask = attr.ib(default=False, type=bool)
    user_mask_from_render = attr.ib(default=False, type=bool)
    parameters_applied = attr.ib(default=False, type=bool)
    undocumented_1 = attr.ib(default=False, type=bool, repr=False)
    undocumented_2 = attr.ib(default=False, type=bool, repr=False)
    undocumented_3 = attr.ib(default=False, type=bool, repr=False)

    @classmethod
    def read(cls, fp):
        flags = read_fmt('B', fp)[0]
        return cls(
            bool(flags & 1), bool(flags & 2), bool(flags & 4), bool(flags & 8),
            bool(flags & 16), bool(flags & 32), bool(flags & 64),
            bool(flags & 128)
        )

    def write(self, fp):
        flags = ((self.pos_relative_to_layer * 1) | (self.mask_disabled * 2) |
                 (self.invert_mask * 4) | (self.user_mask_from_render * 8) |
                 (self.parameters_applied * 16) | (self.undocumented_1 * 32) |
                 (self.undocumented_2 * 64) | (self.undocumented_3 * 128))
        return write_fmt(fp, 'B', flags)


@attr.s(repr=False, slots=True)
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
    top = attr.ib(default=0, type=int)
    left = attr.ib(default=0, type=int)
    bottom = attr.ib(default=0, type=int)
    right = attr.ib(default=0, type=int)
    background_color = attr.ib(default=0, type=int)
    flags = attr.ib(factory=MaskFlags)
    parameters = attr.ib(default=None)
    real_flags = attr.ib(default=None)
    real_background_color = attr.ib(default=None)
    real_top = attr.ib(default=None)
    real_left = attr.ib(default=None)
    real_bottom = attr.ib(default=None)
    real_right = attr.ib(default=None)

    @classmethod
    def read(cls, fp):
        data = read_length_block(fp)
        if len(data) == 0:
            return None

        with io.BytesIO(data) as f:
            return cls._read_body(f, len(data))

    @classmethod
    def _read_body(cls, fp, length):
        top, left, bottom, right, background_color = read_fmt('4iB', fp)
        flags = MaskFlags.read(fp)

        # Order is based on tests. The specification is messed up here...

        # if length == 20:
        #     read_fmt('2x', fp)
        #     return cls(top, left, bottom, right, background_color, flags)

        real_flags, real_background_color = None, None
        real_top, real_left, real_bottom, real_right = None, None, None, None
        if length >= 36:
            real_flags = MaskFlags.read(fp)
            real_background_color = read_fmt('B', fp)[0]
            real_top, real_left, real_bottom, real_right = read_fmt('4i', fp)

        parameters = None
        if flags.parameters_applied:
            parameters = MaskParameters.read(fp)

        # logger.debug('    skipping %d' % (len(fp.read())))
        return cls(
            top, left, bottom, right, background_color, flags, parameters,
            real_flags, real_background_color, real_top, real_left,
            real_bottom, real_right
        )

    def write(self, fp):
        return write_length_block(fp, lambda f: self._write_body(f))

    def _write_body(self, fp):
        written = write_fmt(
            fp, '4iB', self.top, self.left, self.bottom, self.right,
            self.background_color
        )
        written += self.flags.write(fp)

        # if self.real_flags is None and self.parameters is None:
        #     written += write_fmt(fp, '2x')
        #     assert written == 20

        if self.real_flags:
            written += self.real_flags.write(fp)
            written += write_fmt(
                fp, 'B4i', self.real_background_color, self.real_top,
                self.real_left, self.real_bottom, self.real_right
            )

        if self.flags.parameters_applied and self.parameters:
            written += self.parameters.write(fp)

        written += write_padding(fp, written, 4)
        return written

    @property
    def width(self):
        """Width of the mask."""
        return max(self.right - self.left, 0)

    @property
    def height(self):
        """Height of the mask."""
        return max(self.bottom - self.top, 0)

    @property
    def real_width(self):
        """Width of real user mask."""
        return max(self.real_right - self.real_left, 0)

    @property
    def real_height(self):
        """Height of real user mask."""
        return max(self.real_bottom - self.real_top, 0)


@attr.s(repr=False, slots=True)
class MaskParameters(BaseElement):
    """
    Mask parameters.

    .. py:attribute:: user_mask_density
    .. py:attribute:: user_mask_feather
    .. py:attribute:: vector_mask_density
    .. py:attribute:: vector_mask_feather
    """
    user_mask_density = attr.ib(default=None)
    user_mask_feather = attr.ib(default=None)
    vector_mask_density = attr.ib(default=None)
    vector_mask_feather = attr.ib(default=None)

    @classmethod
    def read(cls, fp):
        parameters = read_fmt('B', fp)[0]
        return cls(
            read_fmt('B', fp)[0] if bool(parameters & 1) else None,
            read_fmt('d', fp)[0] if bool(parameters & 2) else None,
            read_fmt('B', fp)[0] if bool(parameters & 4) else None,
            read_fmt('d', fp)[0] if bool(parameters & 8) else None
        )

    def write(self, fp):
        written = 0
        written += write_fmt(
            fp, 'B', ((1 if self.user_mask_density is not None else 0) |
                      (2 if self.user_mask_feather is not None else 0) |
                      (4 if self.vector_mask_density is not None else 0) |
                      (8 if self.vector_mask_feather is not None else 0))
        )
        if self.user_mask_density is not None:
            written += write_fmt(fp, 'B', self.user_mask_density)
        if self.user_mask_feather is not None:
            written += write_fmt(fp, 'd', self.user_mask_feather)
        if self.vector_mask_density is not None:
            written += write_fmt(fp, 'B', self.vector_mask_density)
        if self.vector_mask_feather is not None:
            written += write_fmt(fp, 'd', self.vector_mask_feather)
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
    def read(cls, fp, layer_records=None):
        start_pos = fp.tell()
        items = []
        for idx, layer in enumerate(layer_records):
            items.append(ChannelDataList.read(fp, layer.channel_info))
        logger.debug(
            '  read channel image data, len=%d' % (fp.tell() - start_pos)
        )
        return cls(items)

    def write(self, fp, **kwargs):
        start_pos = fp.tell()
        written = sum(item.write(fp) for item in self)
        logger.debug(
            '  wrote channel image data, len=%d' % (fp.tell() - start_pos)
        )
        return written

    @property
    def _lengths(self):
        """List of layer channel lengths.
        """
        return [item._lengths for item in self]


class ChannelDataList(ListElement):
    """
    List of channel image data, corresponding to each color or alpha.

    See :py:class:`.ChannelData`.
    """

    @classmethod
    def read(cls, fp, channel_info, **kwargs):
        items = []
        for c in channel_info:
            items.append(ChannelData.read(fp, c.length - 2, **kwargs))
        return cls(items)

    @property
    def _lengths(self):
        """List of channel lengths."""
        return [item._length for item in self]


@attr.s(repr=False, slots=True)
class ChannelData(BaseElement):
    """
    Channel data.

    .. py:attribute:: compression

        Compression type. See :py:class:`~psd_tools.constants.Compression`.

    .. py:attribute:: data

        Data.
    """
    compression = attr.ib(
        default=Compression.RAW,
        converter=Compression,
        validator=in_(Compression)
    )
    data = attr.ib(default=b'', type=bytes)

    @classmethod
    def read(cls, fp, length=0, **kwargs):
        compression = Compression(read_fmt('H', fp)[0])
        data = fp.read(length)
        return cls(compression, data)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'H', self.compression.value)
        written += write_bytes(fp, self.data)
        # written += write_padding(fp, written, 2)  # Seems no padding here.
        return written

    def get_data(self, width, height, depth, version=1):
        """Get decompressed channel data.

        :param width: width.
        :param height: height.
        :param depth: bit depth of the pixel.
        :param version: psd file version.
        :rtype: bytes
        """
        return decompress(
            self.data, self.compression, width, height, depth, version
        )

    def set_data(self, data, width, height, depth, version=1):
        """Set raw channel data and compress to store.

        :param data: raw data bytes to write.
        :param compression: compression type,
            see :py:class:`~psd_tools.constants.Compression`.
        :param width: width.
        :param height: height.
        :param depth: bit depth of the pixel.
        :param version: psd file version.
        """
        self.data = compress(
            data, self.compression, width, height, depth, version
        )
        return len(self.data)

    @property
    def _length(self):
        """Length of channel data block.
        """
        return 2 + len(self.data)


@attr.s(repr=False, slots=True)
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
    overlay_color = attr.ib(default=None)
    opacity = attr.ib(default=0, type=int)
    kind = attr.ib(
        default=GlobalLayerMaskKind.PER_LAYER,
        converter=GlobalLayerMaskKind,
        validator=in_(GlobalLayerMaskKind)
    )

    @classmethod
    def read(cls, fp):
        pos = fp.tell()
        data = read_length_block(fp)  # fmt?
        logger.debug('reading global layer mask info, len=%d' % (len(data)))
        if len(data) == 0:
            return cls(overlay_color=None)
        elif len(data) < 13:
            logger.warning(
                'global layer mask info is broken, expected 13 bytes but found'
                ' only %d' % (len(data))
            )
            fp.seek(pos)
            return cls(overlay_color=None)

        with io.BytesIO(data) as f:
            return cls._read_body(f)

    @classmethod
    def _read_body(cls, fp):
        overlay_color = list(read_fmt('5H', fp))
        opacity, kind = read_fmt('HB', fp)
        return cls(overlay_color, opacity, kind)

    def write(self, fp):
        return write_length_block(fp, lambda f: self._write_body(f))

    def _write_body(self, fp):
        written = 0
        if self.overlay_color is not None:
            written = write_fmt(fp, '5H', *self.overlay_color)
            written += write_fmt(fp, 'HB', self.opacity, self.kind.value)
            written += write_padding(fp, written, 4)
        logger.debug('writing global layer mask info, len=%d' % (written))
        return written
