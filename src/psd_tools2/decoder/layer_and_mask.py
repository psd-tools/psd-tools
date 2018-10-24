"""
Layer and mask data structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import io
import logging
# import zlib

from psd_tools2.decoder.base import BaseElement, ListElement
from psd_tools2.decoder.tagged_blocks import TaggedBlocks
from psd_tools2.validators import in_, range_
from psd_tools2.constants import (
    BlendMode, Clipping, Compression, ChannelID, GlobalLayerMaskKind
)
from psd_tools2.utils import (
    read_fmt, write_fmt, read_pascal_string, write_pascal_string,
    read_length_block, write_length_block, is_readable, write_padding,
    write_bytes
)

# import psd_tools.compression  # TODO: Migrate compression module.

logger = logging.getLogger(__name__)


@attr.s
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
        """Read the element from a file-like object.

        :param fp: file-like object
        :param encoding: encoding of the string
        :param version: psd file version
        :rtype: LayerAndMaskInformation
        """
        data = read_length_block(fp, fmt=('I', 'Q')[version - 1])
        logger.debug('reading layer and mask info, len=%d' % (len(data)))
        if len(data) == 0:
            return cls()
        with io.BytesIO(data) as f:
            return cls._read_body(f, encoding, version)

    @classmethod
    def _read_body(cls, fp, encoding, version):
        layer_info = LayerInfo.read(fp, encoding, version)
        global_layer_mask_info = None
        if is_readable(fp):
            global_layer_mask_info = GlobalLayerMaskInfo.read(fp)

        tagged_blocks = None
        if is_readable(fp):
            # For some reason, global tagged blocks aligns 4 byte
            tagged_blocks = TaggedBlocks.read(fp, version=version, padding=4)

        return cls(layer_info, global_layer_mask_info, tagged_blocks)

    def write(self, fp, encoding='macroman', version=1, padding=4):
        """Write the element to a file-like object.

        :param fp: file-like object
        :param encoding: encoding of the string
        :param version: psd file version
        """
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
            written += self.tagged_blocks.write(fp, version=version,
                                                padding=4)
        return written


@attr.s
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

        Channel image data. Contains one or more image data records.
        See :py:class:`.ChannelImageData`.
    """
    layer_count = attr.ib(default=0, type=int)
    layer_records = attr.ib(default=None)
    channel_image_data = attr.ib(default=None)

    @classmethod
    def read(cls, fp, encoding='macroman', version=1):
        """Read the element from a file-like object.

        :param fp: file-like object
        :param encoding: encoding of the string
        :param version: psd file version
        :rtype: :py:class:`.LayerInfo`
        """
        data = read_length_block(fp, fmt=('I', 'Q')[version - 1])
        logger.debug('reading layer info, len=%d' % (len(data)))
        if len(data) == 0:
            return LayerInfo()

        with io.BytesIO(data) as f:
            return cls._read_body(f, encoding, version)

    @classmethod
    def _read_body(cls, fp, encoding, version):
        start_pos = fp.tell()
        layer_count = read_fmt('h', fp)[0]
        layer_records = LayerRecords.read(fp, layer_count, encoding, version)
        logger.debug('  read layer records, len=%d' % (fp.tell() - start_pos))
        channel_image_data = ChannelImageData.read(fp, layer_records)
        return cls(layer_count, layer_records, channel_image_data)

    def write(self, fp, encoding='macroman', version=1, padding=4):
        """Write the element to a file-like object.

        :param fp: file-like object
        :rtype: int
        """
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
        logger.debug('  wrote layer records, len=%d' % (
            fp.tell() - start_pos
        ))
        if self.channel_image_data:
            written += self.channel_image_data.write(fp)
        # Seems the padding size here is different between Photoshop and GIMP.
        written += write_padding(fp, written, padding)
        return written

    def _update_channel_length(self):
        if not self.layer_records or not self.channel_image_data:
            return

        for layer, lengths in zip(self.layer_records,
                                  self.channel_image_data._lengths):
            for channel_info, length in zip(layer.channel_info, lengths):
                channel_info.length = length


@attr.s
class ChannelInfo(BaseElement):
    """
    Channel information.

    .. py:attribute:: id

        Channel ID: 0 = red, 1 = green, etc.;-1 = transparency mask;
        -2 = user supplied layer mask, -3 real user supplied layer mask (when
        both a user mask and a vector mask are present).
        See :py:class:`.ChannelID`.

    .. py:attribute:: length

        Length of the corresponding channel data.
    """
    id = attr.ib(type=int)
    length = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp, version=1):
        """Read the element from a file-like object.

        :param fp: file-like object
        :param version: psd file version
        :rtype: :py:class:`.ChannelInfo`
        """
        return cls(*read_fmt(('hI', 'hQ')[version - 1], fp))

    def write(self, fp, version=1):
        """Write the element to a file-like object.

        :param fp: file-like object
        :param version: psd file version
        """
        return write_fmt(fp, ('hI', 'hQ')[version - 1], *attr.astuple(self))


@attr.s
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
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: :py:class:`.LayerFlags`
        """
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
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        flags = (
            (self.transparency_protected * 1) |
            ((not self.visible) * 2) |
            (self.obsolete * 4) |
            (self.photoshop_v5_later * 8) |
            (self.pixel_data_irrelevant * 16) |
            (self.undocumented_1 * 32) |
            (self.undocumented_2 * 64) |
            (self.undocumented_3 * 128)
        )
        return write_fmt(fp, 'B', flags)


@attr.s
class LayerBlendingRanges(BaseElement):
    """
    Layer blending ranges.

    All ranges contain 2 black values followed by 2 white values.

    .. py:attribute:: composite_ranges

        List of composite gray blend source and destination ranges.

    .. py:attribute:: channel_ranges

        List of channel source and destination ranges.
    """
    composite_ranges = attr.ib(default=None)
    channel_ranges = attr.ib(factory=list)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: :py:class:`.LayerBlendingRanges`
        """
        data = read_length_block(fp)
        if len(data) == 0:
            return cls()

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
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        return write_length_block(fp, lambda f: self._write_body(f))

    def _write_body(self, fp):
        written = 0
        if self.composite_ranges:
            for x in self.composite_ranges:
                written += write_fmt(fp, '2H', *x)
        for channel in self.channel_ranges:
            for x in channel:
                written += write_fmt(fp, '2H', *x)
        return written


@attr.s(repr=False)
class LayerRecords(ListElement):
    """
    List of layer records. See :py:class:`.LayerRecord`.

    .. py:attribute:: items
    """
    items = attr.ib(factory=list)

    @classmethod
    def read(cls, fp, layer_count, encoding='macroman', version=1):
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: :py:class:`.LayerRecords`
        """
        items = []
        for idx in range(abs(layer_count)):
            items.append(LayerRecord.read(fp, encoding, version))
        return cls(items)


@attr.s
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

        Blend mode key. See :py:class:`.BlendMode`.

    .. py:attribute:: opacity

        Opacity, 0 = transparent, 255 = opaque.

    .. py:attribute:: clipping

        Clipping, 0 = base, 1 = non-base. See :py:class:`.Clipping`.

    .. py:attribute:: flags

        See :py:class:`.LayerFlags`.

    .. py:attribute:: mask_data

        :py:class:`.MaskData` or None.

    .. py:attribute:: blending_ranges

        See :py:class:`.LayerBlendingRanges`.

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
    signature = attr.ib(default=b'8BIM', repr=False, type=bytes,
                        validator=in_((b'8BIM',)))
    blend_mode = attr.ib(default=BlendMode.NORMAL, converter=BlendMode,
                         validator=in_(BlendMode))
    opacity = attr.ib(default=255, type=int, validator=range_(0, 255))
    clipping = attr.ib(default=Clipping.BASE, converter=Clipping,
                       validator=in_(Clipping))
    flags = attr.ib(factory=LayerFlags)
    mask_data = attr.ib(default=None)
    blending_ranges = attr.ib(factory=LayerBlendingRanges)
    name = attr.ib(default='', type=str)
    tagged_blocks = attr.ib(factory=TaggedBlocks)

    @classmethod
    def read(cls, fp, encoding='macroman', version=1):
        """Read the element from a file-like object.

        :param fp: file-like object
        :param encoding: encoding of the string
        :param version: psd file version
        :rtype: :py:class:`.LayerRecord`
        """
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
            return cls(
                top, left, bottom, right, channel_info, signature, blend_mode,
                opacity, clipping, flags,
                *cls._read_extra(f, encoding, version)
            )

    @classmethod
    def _read_extra(cls, fp, encoding, version):
        mask_data = MaskData.read(fp)
        blending_ranges = LayerBlendingRanges.read(fp)
        name = read_pascal_string(fp, encoding, padding=4)
        tagged_blocks = TaggedBlocks.read(fp, version, padding=1)
        return mask_data, blending_ranges, name, tagged_blocks

    def write(self, fp, encoding='macroman', version=1):
        """Write the element to a file-like object.

        :param fp: file-like object
        :param encoding: encoding of the string
        :param version: psd file version
        """
        start_pos = fp.tell()
        written = write_fmt(fp, '4iH', self.top, self.left, self.bottom,
                            self.right, len(self.channel_info))
        written += sum(c.write(fp, version) for c in self.channel_info)
        written += write_fmt(
            fp, '4s4sBB', self.signature, self.blend_mode.value, self.opacity,
            self.clipping.value
        )
        written += self.flags.write(fp)

        def writer(f):
            written = self._write_extra(f, encoding, version)
            logger.debug('  wrote layer record, len=%d' % (
                fp.tell() - start_pos
            ))
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
        return [
            {
                ChannelID.USER_LAYER_MASK: (
                    self.mask_data.width, self.mask_data.height
                ),
                ChannelID.REAL_USER_LAYER_MASK: (
                    self.mask_data.real_width, self.mask_data.real_height
                )
            }.get(channel.id, (self.width, self.height))
            for channel in self.channel_info
        ]


@attr.s
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
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: :py:class:`.MaskFlags`
        """
        flags = read_fmt('B', fp)[0]
        return cls(
            bool(flags & 1), bool(flags & 2), bool(flags & 4),
            bool(flags & 8), bool(flags & 16), bool(flags & 32),
            bool(flags & 64), bool(flags & 128)
        )

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        flags = (
            (self.pos_relative_to_layer * 1) |
            (self.mask_disabled * 2) |
            (self.invert_mask * 4) |
            (self.user_mask_from_render * 8) |
            (self.parameters_applied * 16) |
            (self.undocumented_1 * 32) |
            (self.undocumented_2 * 64) |
            (self.undocumented_3 * 128)
        )
        return write_fmt(fp, 'B', flags)


@attr.s
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
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: :py:class:`.MaskData` or None
        """
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
        return cls(top, left, bottom, right, background_color, flags,
                   parameters, real_flags, real_background_color, real_top,
                   real_left, real_bottom, real_right)

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        return write_length_block(fp, lambda f: self._write_body(f))

    def _write_body(self, fp):
        written = write_fmt(fp, '4iB', self.top, self.left, self.bottom,
                            self.right, self.background_color)
        written += self.flags.write(fp)

        # if self.real_flags is None and self.parameters is None:
        #     written += write_fmt(fp, '2x')
        #     assert written == 20

        if self.real_flags:
            written += self.real_flags.write(fp)
            written += write_fmt(fp, 'B4i', self.real_background_color,
                                 self.real_top, self.real_left,
                                 self.real_bottom, self.real_right)

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


@attr.s
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
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: :py:class:`.MaskParameters`
        """
        parameters = read_fmt('B', fp)[0]
        return cls(
            read_fmt('B', fp)[0] if bool(parameters & 1) else None,
            read_fmt('d', fp)[0] if bool(parameters & 2) else None,
            read_fmt('B', fp)[0] if bool(parameters & 4) else None,
            read_fmt('d', fp)[0] if bool(parameters & 8) else None
        )

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        written = 0
        written += write_fmt(fp, 'B', (
            (1 if self.user_mask_density is not None else 0) |
            (2 if self.user_mask_feather is not None else 0) |
            (4 if self.vector_mask_density is not None else 0) |
            (8 if self.vector_mask_feather is not None else 0)
        ))
        if self.user_mask_density is not None:
            written += write_fmt(fp, 'B', self.user_mask_density)
        if self.user_mask_feather is not None:
            written += write_fmt(fp, 'd', self.user_mask_feather)
        if self.vector_mask_density is not None:
            written += write_fmt(fp, 'B', self.vector_mask_density)
        if self.vector_mask_feather is not None:
            written += write_fmt(fp, 'd', self.vector_mask_feather)
        return written


@attr.s(repr=False)
class ChannelImageData(ListElement):
    """
    List of channel image data.

    See :py:class:`.ChannelDataList`.

    .. py:attribute:: items
    """
    items = attr.ib(factory=list)

    @classmethod
    def read(cls, fp, layer_records=None):
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: :py:class:`.ChannelImageData`
        """
        start_pos = fp.tell()
        items = []
        for idx, layer in enumerate(layer_records):
            items.append(ChannelDataList.read(fp, layer.channel_info))
        logger.debug('  read channel image data, len=%d' % (
            fp.tell() - start_pos))
        return cls(items)

    def write(self, fp, **kwargs):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        start_pos = fp.tell()
        written = sum(item.write(fp) for item in self)
        logger.debug('  wrote channel image data, len=%d' % (
            fp.tell() - start_pos))
        return written

    @property
    def _lengths(self):
        """List of layer channel lengths.
        """
        return [item._lengths for item in self]


@attr.s(repr=False)
class ChannelDataList(ListElement):
    """
    List of channel image data.

    See :py:class:`.ChannelData`.

    .. py:attribute:: items
    """
    items = attr.ib(factory=list)

    @classmethod
    def read(cls, fp, channel_info):
        """Read the element from a file-like object.

        :param fp: file-like object
        :param channel_info: :py:class:`.ChannelInfo`
        :rtype: :py:class:`.ChannelDataList`
        """
        items = []
        for c in channel_info:
            data = fp.read(c.length)
            assert len(data) == c.length, '(%d, %d)' % (len(data), c.length)
            # Seems no padding here.
            with io.BytesIO(data) as f:
                items.append(ChannelData.read(f))
        return cls(items)

    @property
    def _lengths(self):
        """List of channel lengths."""
        return [item._length for item in self]


@attr.s
class ChannelData(BaseElement):
    """
    Channel data.

    .. py:attribute:: compression

        Compression type. See :py:class:`~psd_tools2.constants.Compression`.

    .. py:attribute:: data

        Data.
    """
    compression = attr.ib(default=Compression.RAW, converter=Compression,
                          validator=in_(Compression))
    data = attr.ib(default=b'', type=bytes, repr=False)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: :py:class:`.ChannelData`
        """
        compress_type = Compression(read_fmt('H', fp)[0])
        data = fp.read()
        return cls(compress_type, data)

    def write(self, fp, **kwargs):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        written = write_fmt(fp, 'H', self.compression.value)
        written += write_bytes(fp, self.data)
        return written

    @property
    def _length(self):
        """Length of channel data block.
        """
        return 2 + len(self.data)

    # @classmethod
    # def _read(cls, fp, layer, channel, depth, version=1):
    #     bytes_per_pixel = depth // 8

    #     if channel.id == ChannelID.USER_LAYER_MASK:
    #         w, h = layer.mask_data.width, layer.mask_data.height
    #     elif channel.id == ChannelID.REAL_USER_LAYER_MASK:
    #         w, h = layer.mask_data.real_width, layer.mask_data.real_height
    #     else:
    #         w, h = layer.width, layer.height

    #     start_pos = fp.tell()
    #     compress_type = Compression(read_fmt('H', fp)[0])
    #     data = None

    #     # read data size.
    #     byte_counts = None
    #     if compress_type == Compression.RAW:
    #         data_size = w * h * bytes_per_pixel
    #     elif compress_type == Compression.PACK_BITS:
    #         byte_counts = read_be_array(('H', 'I')[version - 1], h, fp)
    #         data_size = sum(byte_counts)
    #     elif compress_type in (Compression.ZIP,
    #                            Compression.ZIP_WITH_PREDICTION):
    #         data_size = channel.length - 2

    #     logger.debug('  reading channel id=%d, len=%d, start_pos=%d' % (
    #         channel.id, data_size, start_pos))

    #     # read the data itself.
    #     if data_size > channel.length:
    #         raise ValueError("Incorrect data size: %s > %s" % (
    #             data_size, channel.length
    #         ))
    #     else:
    #         raw_data = fp.read(data_size)
    #         if compress_type in (Compression.RAW, Compression.PACK_BITS):
    #             data = raw_data
    #         elif compress_type == Compression.ZIP:
    #             data = zlib.decompress(raw_data)
    #         elif compress_type == Compression.ZIP_WITH_PREDICTION:
    #             decompressed = zlib.decompress(raw_data)
    #             data = psd_tools.compression.decode_prediction(
    #                 decompressed, w, h, bytes_per_pixel)

    #         if data is None:
    #             raise ValueError("Empty data")

    #     remaining_length = channel.length - (fp.tell() - start_pos)
    #     if remaining_length > 0:
    #         fp.seek(remaining_length, 1)
    #         logger.debug('skipping %s bytes', remaining_length)

    #     return cls(compress_type, data, byte_counts)

    # def write(self, fp, channel):
    #     written = write_fmt(fp, 'H', self.compression.value)

    #     if self.compression == Compression.PACK_BITS:
    #         written += write_be_array(fp, self.byte_counts)

    #     if self.compression in (Compression.RAW, Compression.PACK_BITS):
    #         written += write_bytes(fp, self.data)
    #     elif self.compression == Compression.ZIP:
    #         written += write_bytes(fp, zlib.compress(self.data))
    #     elif self.compression == Compression.ZIP_WITH_PREDICTION:
    #         raise NotImplementedError('ZIP+prediction is not supported.')

    #     # TODO: Should the padding size be determined here?
    #     padding_size = channel.length - (fp.tell() - start_pos)
    #     assert padding_size >= 0, 'padding_size = %d' % padding_size
    #     written += write_fmt(fp, '%dx' % padding_size)

    #     return written


@attr.s
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
    kind = attr.ib(default=GlobalLayerMaskKind.PER_LAYER,
                   converter=GlobalLayerMaskKind,
                   validator=in_(GlobalLayerMaskKind))

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: :py:class:`.GlobalLayerMaskInfo`
        """
        data = read_length_block(fp)
        logger.debug('reading global layer mask info, len=%d' % (len(data)))
        if len(data) == 0:
            return cls(overlay_color=None)

        with io.BytesIO(data) as f:
            return cls._read_body(f)

    @classmethod
    def _read_body(cls, fp):
        overlay_color = list(read_fmt('5H', fp))
        opacity, kind = read_fmt('HB', fp)
        return cls(overlay_color, opacity, kind)

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        return write_length_block(fp, lambda f: self._write_body(f))

    def _write_body(self, fp):
        written = 0
        if self.overlay_color is not None:
            written = write_fmt(fp, '5H', *self.overlay_color)
            written += write_fmt(fp, 'HB', self.opacity, self.kind.value)
            written += write_padding(fp, written, 4)
        logger.debug('writing global layer mask info, len=%d' % (written))
        return written
