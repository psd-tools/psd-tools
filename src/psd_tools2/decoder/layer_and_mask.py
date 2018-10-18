from __future__ import absolute_import, unicode_literals
import attr
import io
import logging
import warnings
import zlib

from psd_tools2.decoder.base import BaseElement, ListElement
from psd_tools2.constants import BlendMode, Compression, ChannelID
from psd_tools2.validators import in_, range_
from psd_tools2.utils import (
    read_fmt, write_fmt, read_pascal_string, read_be_array, write_be_array,
    pad, write_pascal_string, read_length_block, write_length_block
)

import psd_tools.compression  # TODO: Migrate compression module.

logger = logging.getLogger(__name__)


@attr.s
class LayerAndMaskInformation(BaseElement):
    """
    Layer and mask information section.

    .. py:attribute:: length
    .. py:attribute:: layer_info
    .. py:attribute:: global_layer_mask_info
    .. py:attribute:: tagged_blocks
    """
    layer_info = attr.ib(default=None)
    global_layer_mask_info = attr.ib(default=None)
    tagged_blocks = attr.ib(default=None)

    @classmethod
    def read(cls, fp, depth=8, encoding='utf-8', version=1):
        """Read the element from a file-like object.

        :param fp: file-like object
        :param encoding: encoding of the string
        :param version: psd file version
        :rtype: LayerAndMaskInformation
        """
        data = read_length_block(fp, fmt=('I', 'Q')[version - 1])
        length = len(data)
        if len(data) == 0:
            return cls()

        layer_info = None
        global_layer_mask_info = None
        tagged_blocks = None

        with io.BytesIO(data) as f:
            layer_info = LayerInfo.read(f, depth, encoding, version)

            if length > f.tell():
                global_layer_mask_info = GlobalLayerMaskInfo.read(f)

            remaining_length = length - f.tell()
            if remaining_length:
                logger.debug('reading tagged blocks, pos=%d' % (f.tell()))
                # For some reason, global tagged blocks aligns 4 byte
                tagged_blocks = TaggedBlocks.read(f, remaining_length,
                                                  version, 4)

            remaining_length = length - f.tell()
            if remaining_length > 0:
                f.seek(remaining_length, 1)
                logger.debug('skipping %s bytes' % remaining_length)

        return cls(layer_info, global_layer_mask_info, tagged_blocks)

    def write(self, fp, depth=8, encoding='utf-8', version=1):
        """Write the element to a file-like object.
        """
        writer = lambda f: self._write_body(f, depth, encoding, version)
        return write_length_block(fp, writer, fmt=('I', 'Q')[version - 1])

    def _write_body(self, fp, depth, encoding, version):
        written = 0
        if self.layer_info:
            written += self.layer_info.write(fp, depth, encoding, version)
        if self.global_layer_mask_info:
            written += self.global_layer_mask_info.write(fp)
        if self.tagged_blocks:
            written += self.tagged_blocks.write(fp)
        written += write_padding(fp, written, 2)
        return written



@attr.s
class LayerInfo(BaseElement):
    """
    Layer information.

    .. py:attribute:: layer_count
    .. py:attribute:: layer_records
    .. py:attribute:: channel_image_data
    """
    layer_count = attr.ib(default=0, type=int)
    layer_records = attr.ib(default=None)
    channel_image_data = attr.ib(default=None)

    @classmethod
    def read(cls, fp, depth=8, encoding='utf-8', version=1, **kwargs):
        """Read the element from a file-like object.

        :param fp: file-like object
        :param encoding: encoding of the string
        :param version: psd file version
        :rtype: LayerInfo
        """
        data = read_length_block(fp, fmt=('I', 'Q')[version - 1])
        if len(data) == 0:
            return LayerInfo()

        with io.BytesIO(data) as f:
            cls._read_body(f, depth, encoding, version, **kwargs)


    @classmethod
    def _read_body(cls, fp, depth, encoding, version, **kwargs):
        layer_count = read_fmt('h', fp)[0]
        layer_records = LayerRecords.read(fp, layer_count, encoding, version)
        channel_image_data = LayerImageData.read(fp, layer_records, depth,
                                                 version)
        return cls(layer_count, layer_records, channel_image_data)

    def write(self, fp, depth=8, encoding='utf-8', version=1):
        """Write the element to a file-like object.
        """
        length_fmt = ('I', 'Q')[version - 1]
        if self.layer_count == 0:
            return write_fmt(fp, length_fmt, 0)

        writer = lambda f: self.write_body(f, depth, encoding, version)
        written = write_length_block(fp, writer, fmt=length_fmt)

    def _write_body(self, fp, depth, encoding, version):
        written = write_fmt(fp, 'h', self.layer_count)
        if self.layer_records:
            written += self.layer_records.write(fp, encoding, version)
        if self.channel_image_data:
            written += self.channel_image_data.write(fp, self.layer_records)
        return written


@attr.s
class ChannelInfo(BaseElement):
    """
    Channel information.

    .. py:attribute:: id
    .. py:attribute:: length
    """
    id = attr.ib(type=int)
    length = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp, version=1):
        """Read the element from a file-like object.

        :param fp: file-like object
        :param version: psd file version
        :rtype: ChannelInfo
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

    .. py:attribute:: transparency_protected
    .. py:attribute:: visible
    .. py:attribute:: pixel_data_irrelevant
    """
    transparency_protected = attr.ib(default=False, type=bool)
    visible = attr.ib(default=True, type=bool)
    pixel_data_irrelevant = attr.ib(default=False, type=bool)

    @classmethod
    def read(cls, fp):
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: LayerFlags
        """
        flags = read_fmt('B', fp)[0]
        return cls(
            bool(flags & 1),
            not bool(flags & 2),  # why "not"?
            bool(flags & 16) if bool(flags & 8) else None
        )

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        photoshop_v5_later = self.pixel_data_irrelevant is not None
        flags = (
            (self.transparency_protected * 1) |
            ((not self.visible) * 2) |
            (photoshop_v5_later * 8) |
            ((photoshop_v5_later & bool(self.pixel_data_irrelevant)) * 16)
        )
        return write_fmt(fp, 'B', flags)


@attr.s
class LayerBlendingRanges(BaseElement):
    """
    Layer blending ranges.

    .. py:attribute:: composite_ranges
    .. py:attribute:: channel_ranges
    """
    composite_ranges = attr.ib(default=None)
    channel_ranges = attr.ib(factory=list)

    @classmethod
    def read(cls, fp):
        def read_channel_range():
            src_start, src_end, dest_start, dest_end = read_fmt("4H", fp)
            return (src_start, src_end), (dest_start, dest_end)

        logger.debug('  reading blending ranges, pos=%d' % fp.tell())
        self = cls()
        length = read_fmt("I", fp)[0]
        if length:
            self.composite_ranges = read_channel_range()
            for x in range(length // 8 - 1):
                self.channel_ranges.append(read_channel_range())

        attr.validate(self)
        return self

    def write(self, fp):
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
class TaggedBlocks(ListElement):
    """
    List of tagged blocks.

    .. py:attribute:: items
    """
    items = attr.ib(factory=list)

    @classmethod
    def read(cls, fp, length=None, version=1, padding=1):
        def is_readable(f):
            if len(f.read(1)):
                f.seek(-1, 1)
                return True
            else:
                return False

        items = []
        start_pos = fp.tell()
        while is_readable(fp):
            block = TaggedBlock.read(fp, version, padding)
            if block is None:
                break
            if length is not None and fp.tell() - start_pos > length:
                logger.warning('Invalid position %d, expected %d' % (
                    fp.tell(), start_pos + length
                ))
                fp.seek(start_pos + length)
                break
            items.append(block)
        return cls(items)

    def write(self, fp, version=1, padding=1):
        written = 0
        for item in self:
            written += item.write(fp, version, padding)
        return written


@attr.s
class TaggedBlock(BaseElement):
    """
    Layer tagged block with extra info.

    .. py:attribute:: key
    .. py:attribute:: data
    """
    BIG_KEYS = set((
        b'LMsk', b'Lr16', b'Lr32', b'Layr', b'Mt16', b'Mt32', b'Mtrn',
        b'Alph', b'FMsk', b'lnk2', b'FEid', b'FXid', b'PxSD',
        b'lnkE', b'pths',  # Undocumented.
    ))

    signature = attr.ib(default=b'8BIM', repr=False,
                        validator=in_((b'8BIM', b'8B64')))
    key = attr.ib(default=b'', type=bytes)
    data = attr.ib(default=b'')

    @classmethod
    def read(cls, fp, version=1, padding=1):
        signature, key = read_fmt('4s4s', fp)
        print(signature, key)
        try:
            self = cls(signature, key)
        except ValueError:
            logger.warning('Failed to read block (%s, %s)' % (signature, key))
            return None

        data = read_length_block(
            fp,
            fmt=self._length_format(self.key, version),
            padding=padding
        )
        # length = read_fmt(cls._length_format(key, version), fp)[0]
        # if padding > 0:
        #     length = pad(length, padding)

        # TODO: Parse data here.
        self.data = data
        return self

    def write(self, fp, version=1, padding=1):
        written = write_fmt(fp, '4s4s', self.signature, self.key)
        written += write_length_block(
            fp,
            lambda f: f.write(self.data),  # TODO: Serialize data here.
            fmt=self._length_format(self.key, version),
            padding=padding
        )
        return written

    @classmethod
    def _length_format(cls, key, version):
        return ('I', 'Q')[int(version == 2 and key in cls.BIG_KEYS)]


@attr.s(repr=False)
class LayerRecords(ListElement):
    """
    List of layer records.

    .. py:attribute:: items
    """
    items = attr.ib(factory=list)

    @classmethod
    def read(cls, fp, layer_count, *args, **kwargs):
        items = []
        for idx in range(abs(layer_count)):
            items.append(LayerRecord.read(fp, *args, **kwargs))
        return cls(items)


@attr.s
class LayerRecord(BaseElement):
    """
    Layer record.

    .. py:attribute:: top
    .. py:attribute:: left
    .. py:attribute:: bottom
    .. py:attribute:: right
    .. py:attribute:: channels
    .. py:attribute:: signature
    .. py:attribute:: blend_mode
    .. py:attribute:: opacity
    .. py:attribute:: clipping
    .. py:attribute:: flags
    .. py:attribute:: mask_data
    .. py:attribute:: blending_ranges
    .. py:attribute:: name
    .. py:attribute:: tagged_blocks
    """
    top = attr.ib(default=0, type=int)
    left = attr.ib(default=0, type=int)
    bottom = attr.ib(default=0, type=int)
    right = attr.ib(default=0, type=int)
    channels = attr.ib(factory=list)
    signature = attr.ib(default=b'8BIM', repr=False, type=bytes,
                        validator=in_((b'8BIM',)))
    blend_mode = attr.ib(default=BlendMode.NORMAL, converter=BlendMode,
                         validator=in_(BlendMode))
    opacity = attr.ib(default=255, type=int, validator=range_(0, 255))
    clipping = attr.ib(default=0, type=int)
    flags = attr.ib(factory=LayerFlags)
    mask_data = attr.ib(default=None)
    blending_ranges = attr.ib(factory=LayerBlendingRanges)
    name = attr.ib(default='', type=str)
    tagged_blocks = attr.ib(factory=TaggedBlocks)

    @classmethod
    def read(cls, fp, encoding='utf-8', version=1):
        """Read the element from a file-like object.

        :param fp: file-like object
        :param encoding: encoding of the string
        :param version: psd file version
        :rtype: LayerAndMaskInformation
        """
        top, left, bottom, right, num_channels = read_fmt('4iH', fp)
        channels = [
            ChannelInfo.read(fp, version) for i in range(num_channels)
        ]
        signature, blend_mode, opacity, clipping = read_fmt('4s4sBB', fp)
        flags = LayerFlags.read(fp)

        data = read_length_block(fp, fmt='xI')
        with io.BytesIO(data) as f:
            return cls(
                top, left, bottom, right, channels, signature, blend_mode,
                opacity, clipping, flags,
                *cls._read_extra(f, len(data), encoding, version)
            )

    @classmethod
    def _read_extra(cls, fp, length, encoding, version):
        mask_data = MaskData.read(fp)
        blending_ranges = LayerBlendingRanges.read(fp)
        name = read_pascal_string(fp, encoding, 4)
        tagged_blocks = TaggedBlocks.read(fp, length - fp.tell(), version, 1)
        return mask_data, blending_ranges, name, tagged_blocks

    def write(self, fp, encoding='utf-8', version=1):
        """Write the element to a file-like object.
        """
        written = write_fmt(fp, '4iH', self.top, self.left, self.bottom,
                            self.right, len(self.channels))
        written += sum(c.write(fp, version) for c in self.channels)
        written += write_fmt(
            fp, '4s4sBB', self.signature, self.blend_mode.value, self.opacity,
            self.clipping
        )
        written += self.flags.write(fp)
        writer = lambda f: self._write_extra(f, encoding, version)
        written += write_length_block(fp, writer, fmt='xI', padding=2)
        return written

    def _write_extra(self, fp, encoding, version):
        written = 0
        if self.mask_data:
            written += self.mask_data.write(fp)
        else:
            written += write_fmt(fp, 'I', 0)

        written += self.blending_ranges.write(fp)
        written += write_pascal_string(fp, self.name, encoding, 4)
        written += self.tagged_blocks.write(fp, version)
        return written

    @property
    def width(self):
        return max(self.right - self.left, 0)

    @property
    def height(self):
        return max(self.bottom - self.top, 0)


@attr.s
class MaskData(BaseElement):
    """
    Mask data.

    .. py:attribute:: top
    .. py:attribute:: left
    .. py:attribute:: bottom
    .. py:attribute:: right
    .. py:attribute:: background_color
    .. py:attribute:: flags
    .. py:attribute:: parameters
    .. py:attribute:: real_flags
    .. py:attribute:: real_background_color
    .. py:attribute:: real_top
    .. py:attribute:: real_left
    .. py:attribute:: real_bottom
    .. py:attribute:: real_right
    """
    top = attr.ib(default=0, type=int)
    left = attr.ib(default=0, type=int)
    bottom = attr.ib(default=0, type=int)
    right = attr.ib(default=0, type=int)
    background_color = attr.ib(default=0, type=int)
    flags = attr.ib(default=None)
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
        :rtype: MaskData or None
        """
        length = read_fmt("I", fp)[0]
        if not length:
            return None
        start_pos = fp.tell()

        self = cls()
        self.top, self.left, self.bottom, self.right = read_fmt("4i", fp)
        self.background_color = read_fmt("B", fp)[0]
        self.flags = MaskFlags.read(fp)

        # Order is based on tests. The specification is messed up here...
        if length >= 36:
            self.real_flags = MaskFlags.read(fp)
            self.real_background_color = read_fmt("B", fp)[0]
            self.real_top, self.real_left = read_fmt("2i", fp)
            self.real_bottom, self.real_right = read_fmt("2i", fp)

        if self.flags.parameters_applied:
            self.parameters = MaskParameters.read(fp)

        padding_size = length - (fp.tell() - start_pos)
        if padding_size > 0:
            fp.seek(padding_size, 1)

        attr.validate(self)
        return self

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        start_pos = fp.tell()
        fp.seek(4, 1)
        written = write_fmt(fp, '4iB', self.top, self.left, self.bottom,
                            self.right, self.background_color)
        written += self.flags.write(fp)
        if self.real_flags:
            written += self.real_flags.write(fp)
            written += write_fmt(fp, 'B4i', self.real_background_color,
                                 self.real_top, self.real_left,
                                 self.real_bottom, self.real_right)

        if self.flags.parameters_applied and self.parameters:
            written += self.parameters.write(fp)

        length = pad(written, 2)  # Correct?
        written += write_fmt(fp, '%dx' % length - (fp.tell() - start_pos))

        end_pos = fp.tell()
        fp.seek(start_pos)
        written += write_fmt(fp, 'I', length)
        fp.seek(end_pos)
        return written

    @property
    def width(self):
        return max(self.right - self.left, 0)

    @property
    def height(self):
        return max(self.bottom - self.top, 0)

    @property
    def real_width(self):
        return max(self.real_right - self.real_left, 0)

    @property
    def real_height(self):
        return max(self.real_bottom - self.real_top, 0)


@attr.s
class MaskFlags(BaseElement):
    """
    Mask flags.

    .. py:attribute:: pos_relative_to_layer
    .. py:attribute:: mask_disabled
    .. py:attribute:: invert_mask
    .. py:attribute:: user_mask_from_render
    .. py:attribute:: parameters_applied
    """
    pos_relative_to_layer = attr.ib(default=False, type=bool)
    mask_disabled = attr.ib(default=False, type=bool)
    invert_mask = attr.ib(default=False, type=bool)
    user_mask_from_render = attr.ib(default=False, type=bool)
    parameters_applied = attr.ib(default=False, type=bool)

    @classmethod
    def read(cls, fp):
        flags = read_fmt('B', fp)[0]
        return cls(
            bool(flags & 1), bool(flags & 2), bool(flags & 4),
            bool(flags & 8), bool(flags & 16)
        )

    def write(self, fp):
        flags = (
            (self.pos_relative_to_layer * 1) |
            (self.mask_disabled * 2) |
            (self.invert_mask * 4) |
            (self.user_mask_from_render * 8) |
            (self.parameters_applied * 16)
        )
        return write_fmt(fp, 'B', flags)


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
        parameters = read_fmt('B', fp)[0]
        return cls(
            read_fmt('B', fp)[0] if bool(parameters & 1) else None,
            read_fmt('d', fp)[0] if bool(parameters & 2) else None,
            read_fmt('B', fp)[0] if bool(parameters & 4) else None,
            read_fmt('d', fp)[0] if bool(parameters & 8) else None
        )

    def write(self, fp):
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
class LayerImageData(ListElement):
    """
    List of channel image data.

    .. py:attribute:: items
    """
    items = attr.ib(factory=list)

    @classmethod
    def read(cls, fp, layer_records, depth, version):
        items = []
        for idx, layer in enumerate(layer_records):
            logger.debug('reading layer channel data %d, pos=%d' % (
                idx, fp.tell()
            ))
            items.append(Channels.read(fp, layer, depth, version))
        return cls(items)

    def write(self, fp, layer_records):
        written = 0
        for item, layer in zip(self, layer_records):
            written += item.write(fp, layer.channel)
        return written


@attr.s(repr=False)
class Channels(ListElement):
    """
    List of channel image data.

    .. py:attribute:: items
    """
    items = attr.ib(factory=list)

    @classmethod
    def read(cls, fp, layer, depth, version):
        items = []
        for channel in layer.channels:
            items.append(Channel.read(fp, layer, channel, depth, version))
        return cls(items)

    def write(self, fp, channels):
        written = 0
        for item, channel in zip(self, channels):
            written += item.write(fp, channel)
        return written


@attr.s
class Channel(BaseElement):
    """
    Channel data.

    .. py:attribute:: compression

        :py:class:`~psd_tools.constants.Compression`

    .. py:attribute:: data
    """
    compression = attr.ib(default=Compression.RAW, converter=Compression,
                          validator=in_(Compression))
    data = attr.ib(default=b'', type=bytes, repr=False)
    byte_counts = attr.ib(default=None, repr=False)  # TODO: Can be removed.

    @classmethod
    def read(cls, fp, layer, channel, depth, version=1):
        bytes_per_pixel = depth // 8

        if channel.id == ChannelID.USER_LAYER_MASK:
            w, h = layer.mask_data.width, layer.mask_data.height
        elif channel.id == ChannelID.REAL_USER_LAYER_MASK:
            w, h = layer.mask_data.real_width, layer.mask_data.real_height
        else:
            w, h = layer.width, layer.height

        start_pos = fp.tell()
        compress_type = Compression(read_fmt('H', fp)[0])
        data = None

        # read data size.
        byte_counts = None
        if compress_type == Compression.RAW:
            data_size = w * h * bytes_per_pixel
        elif compress_type == Compression.PACK_BITS:
            byte_counts = read_be_array(('H', 'I')[version - 1], h, fp)
            data_size = sum(byte_counts)
        elif compress_type in (Compression.ZIP,
                               Compression.ZIP_WITH_PREDICTION):
            data_size = channel.length - 2

        logger.debug('  reading channel id=%d, len=%d, start_pos=%d' % (
            channel.id, data_size, start_pos))

        # read the data itself.
        if data_size > channel.length:
            raise ValueError("Incorrect data size: %s > %s" % (
                data_size, channel.length
            ))
        else:
            raw_data = fp.read(data_size)
            if compress_type in (Compression.RAW, Compression.PACK_BITS):
                data = raw_data
            elif compress_type == Compression.ZIP:
                data = zlib.decompress(raw_data)
            elif compress_type == Compression.ZIP_WITH_PREDICTION:
                decompressed = zlib.decompress(raw_data)
                data = psd_tools.compression.decode_prediction(
                    decompressed, w, h, bytes_per_pixel)

            if data is None:
                raise ValueError("Empty data")

        remaining_length = channel.length - (fp.tell() - start_pos)
        if remaining_length > 0:
            fp.seek(remaining_length, 1)
            logger.debug('skipping %s bytes', remaining_length)

        return cls(compress_type, data, byte_counts)

    def write(self, fp, channel):
        written = write_fmt(fp, 'H', self.compression.value)

        if self.compression == Compression.PACK_BITS:
            written += write_be_array(fp, self.byte_counts)

        if self.compression in (Compression.RAW, Compression.PACK_BITS):
            written += fp.write(self.data)
        elif self.compression == Compression.ZIP:
            written += fp.write(zlib.compress(self.data))
        elif self.compression == Compression.ZIP_WITH_PREDICTION:
            raise NotImplementedError('ZIP with prediction is not supported.')

        # TODO: Should the padding size be determined here?
        padding_size = channel.length - (fp.tell() - start_pos)
        assert padding_size >= 0, 'padding_size = %d' % padding_size
        written += write_fmt(fp, '%dx' % padding_size)

        return written


@attr.s
class GlobalLayerMaskInfo(BaseElement):
    """
    Global mask information.

    .. py:attribute:: overlay_color
    .. py:attribute:: opacity
    .. py:attribute:: kind
    """
    overlay_color = attr.ib(factory=list)
    opacity = attr.ib(default=0, type=int)
    kind = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp):
        length = read_fmt('I', fp)[0]
        logger.debug('reading global layer mask, len=%d, pos=%d' % (
            length, fp.tell()))
        if length == 0:
            return None

        overlay_color = list(read_fmt('5H', fp))
        opacity, kind = read_fmt('HB', fp)
        read_fmt('%dx' % max(length - 13, 0), fp)
        return cls(overlay_color, opacity, kind)

    def write(self, fp):
        written = write_fmt('I', 16)  # 4-byte alignment?
        written += write_fmt(fp, '5H', self.overlay_color)
        written += write_fmt(fp, 'HB3x', self.opacity, self.kind)
        return written
