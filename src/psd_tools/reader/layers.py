# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, division, print_function
import logging
import warnings
import zlib

from psd_tools.utils import (read_fmt, read_pascal_string,
                             read_be_array, trimmed_repr, pad, synchronize)
from psd_tools.exceptions import Error
from psd_tools.constants import (Compression, Clipping, BlendMode,
                                 ChannelID, TaggedBlock)
from psd_tools import compression
from psd_tools.debug import pretty_namedtuple

logger = logging.getLogger(__name__)

_LayerRecord = pretty_namedtuple('LayerRecord', [
    'top', 'left', 'bottom', 'right',
    'num_channels', 'channels',
    'blend_mode', 'opacity', 'clipping', 'flags',
    'mask_data', 'blending_ranges', 'name',
    'tagged_blocks'
])

class LayerRecord(_LayerRecord):

    def width(self):
        return self.right - self.left

    def height(self):
        return self.bottom - self.top


Layers = pretty_namedtuple('Layers', 'length, layer_count, layer_records, channel_image_data')
LayerFlags = pretty_namedtuple('LayerFlags', 'transparency_protected visible')
LayerAndMaskData = pretty_namedtuple('LayerAndMaskData', 'layers global_mask_info tagged_blocks')
_ChannelInfo = pretty_namedtuple('ChannelInfo', 'id length')
_MaskData = pretty_namedtuple('MaskData', 'top left bottom right default_color flags real_flags real_background')
LayerBlendingRanges = pretty_namedtuple('LayerBlendingRanges', 'composite_ranges channel_ranges')
_ChannelData = pretty_namedtuple('ChannelData', 'compression data')
_Block = pretty_namedtuple('Block', 'key data')
GlobalMaskInfo = pretty_namedtuple('GlobalMaskInfo', 'overlay color_components opacity kind')


class ChannelInfo(_ChannelInfo):
    def __repr__(self):
        return "ChannelInfo(id=%s %s, length=%s)" % (
            self.id, ChannelID.name_of(self.id), self.length
        )


class MaskData(_MaskData):

    def width(self):
        return self.right - self.left

    def height(self):
        return self.bottom - self.top


class ChannelData(_ChannelData):
    def __repr__(self):
        return "ChannelData(compression=%r %s, len(data)=%r)" % (
            self.compression, Compression.name_of(self.compression),
            len(self.data) if self.data is not None else None
        )

    def _repr_pretty_(self, p, cycle):
        if cycle:
            p.text('ChannelData(...)')
        else:
            p.text(repr(self))


class Block(_Block):
    """
    Layer tagged block with extra info.
    """
    def __repr__(self):
        return "Block(%s %s, %s)" % (self.key, TaggedBlock.name_of(self.key),
                                     trimmed_repr(self.data))

    def _repr_pretty_(self, p, cycle):
        if cycle:
            p.text('Block(...)')
        else:
            with p.group(1, 'Block(', ')'):
                p.breakable()
                p.text("%s %s," % (self.key, TaggedBlock.name_of(self.key)))
                p.breakable()
                if isinstance(self.data, bytes):
                    p.text(trimmed_repr(self.data))
                else:
                    p.pretty(self.data)


def read(fp, encoding, depth):
    """
    Reads layers and masks information.
    """
    logger.debug('reading layers and masks information...')
    length = read_fmt("I", fp)[0]
    start_position = fp.tell()

    logger.debug('length=%d, start_position=%d', length, start_position)

    layers = _read_layers(fp, encoding, depth)

    # XXX: are tagged blocks really after the layers?
    # XXX: does global mask reading really work?
    global_mask_info = _read_global_mask_info(fp)

    consumed_bytes = fp.tell() - start_position
    synchronize(fp) # hack hack hack
    tagged_blocks = _read_layer_tagged_blocks(fp, length - consumed_bytes)

    consumed_bytes = fp.tell() - start_position
    fp.seek(length-consumed_bytes, 1)

    return LayerAndMaskData(layers, global_mask_info, tagged_blocks)


def _read_layers(fp, encoding, depth, length=None):
    """
    Reads info about layers.
    """
    logger.debug('reading layers...')

    if length is None:
        length = read_fmt("I", fp)[0]
    layer_count = read_fmt("h", fp)[0]

    logger.debug('layer_count=%d, length=%d', layer_count, length)

    layer_records = []
    for idx in range(abs(layer_count)):
        logger.debug('reading layer record %d, pos=%d', idx, fp.tell())
        layer = _read_layer_record(fp, encoding)
        layer_records.append(layer)

    channel_image_data = []
    for idx, layer in enumerate(layer_records):
        logger.debug('reading layer channel data %d, pos=%d', idx, fp.tell())
        data = _read_channel_image_data(fp, layer, depth)
        channel_image_data.append(data)

    return Layers(length, layer_count, layer_records, channel_image_data)


def _read_layer_record(fp, encoding):
    """
    Reads single layer record.
    """
    top, left, bottom, right, num_channels = read_fmt("4i H", fp)
    logger.debug('  top=%d, left=%d, bottom=%d, right=%d, num_channels=%d',
                 top, left, bottom, right, num_channels)

    channel_info = []
    for channel_num in range(num_channels):
        info = ChannelInfo(*read_fmt("hI", fp))
        channel_info.append(info)

    sig = fp.read(4)
    if sig != b'8BIM':
        raise Error("Error parsing layer: invalid signature (%r)" % sig)

    blend_mode = fp.read(4)
    if not BlendMode.is_known(blend_mode):
        warnings.warn("Unknown blend mode (%s)" % blend_mode)

    opacity, clipping, flags, extra_length = read_fmt("BBBxI", fp)
    logger.debug('  extra_length=%s', extra_length)

    flags = LayerFlags(bool(flags & 1), not bool(flags & 2)) # why not?

    if not Clipping.is_known(clipping):
        warnings.warn("Unknown clipping: %s" % clipping)

    start = fp.tell()
    mask_data = _read_layer_mask_data(fp)
    blending_ranges = _read_layer_blending_ranges(fp)

    name = read_pascal_string(fp, encoding, 4)

    remaining_length = extra_length - (fp.tell()-start)
    tagged_blocks = _read_layer_tagged_blocks(fp, remaining_length)

    remaining_length = extra_length - (fp.tell()-start)
    if remaining_length:
        logger.debug('  skipping %s bytes', remaining_length)
        fp.seek(remaining_length, 1) # skip the reminder

    return LayerRecord(
        top, left, bottom, right,
        num_channels, channel_info,
        blend_mode, opacity, clipping, flags,
        mask_data, blending_ranges, name,
        tagged_blocks
    )


def _read_layer_tagged_blocks(fp, remaining_length):
    """
    Reads a section of tagged blocks with additional layer information.
    """
    blocks = []
    start_pos = fp.tell()
    read_bytes = 0
    while read_bytes < remaining_length:
        block = _read_additional_layer_info_block(fp)
        read_bytes = fp.tell() - start_pos
        if block is None:
            break
        blocks.append(block)

    return blocks


def _read_additional_layer_info_block(fp):
    """
    Reads a tagged block with additional layer information.
    """
    sig = fp.read(4)
    if sig not in [b'8BIM', b'8B64']:
        fp.seek(-4, 1)
        #warnings.warn("not a block: %r" % sig)
        return

    key = fp.read(4)
    length = pad(read_fmt("I", fp)[0], 4)

    data = fp.read(length)
    return Block(key, data)


def _read_layer_mask_data(fp):
    """ Reads layer mask or adjustment layer data. """
    size = read_fmt("I", fp)[0]
    if size not in [0, 20, 36]:
        warnings.warn("Invalid layer data size: %d" % size)
        fp.seek(size, 1)
        return

    if not size:
        return

    top, left, bottom, right, default_color, flags = read_fmt("4i 2B", fp)
    if size == 20:
        fp.seek(2, 1)
        real_flags, real_background = None, None
    else:
        real_flags, real_background = read_fmt("2B", fp)

        # XXX: is it correct to prefer data at the end?
        top, left, bottom, right = read_fmt("4i", fp)

    return MaskData(top, left, bottom, right, default_color, flags, real_flags, real_background)


def _read_layer_blending_ranges(fp):
    """ Reads layer blending data. """

    def read_channel_range():
        src_start, src_end, dest_start, dest_end = read_fmt("4H", fp)
        return (src_start, src_end), (dest_start, dest_end)

    composite_ranges = None
    channel_ranges = []
    length = read_fmt("I", fp)[0]

    if length:
        composite_ranges = read_channel_range()
        for x in range(length//8 - 1):
            channel_ranges.append(read_channel_range())

    return LayerBlendingRanges(composite_ranges, channel_ranges)


def _read_channel_image_data(fp, layer, depth):
    """
    Reads image data for all channels in a layer.
    """
    channel_data = []

    bytes_per_pixel = depth // 8

    for idx, channel in enumerate(layer.channels):
        logger.debug("  reading %s", channel)
        if channel.id == ChannelID.USER_LAYER_MASK:
            w, h = layer.mask_data.width(), layer.mask_data.height()
        else:
            w, h = layer.width(), layer.height()

        start_pos = fp.tell()
        compress_type = read_fmt("H", fp)[0]

        logger.debug("    start_pos=%s, compress_type=%s",
                     start_pos, Compression.name_of(compress_type))

        data = None

        # read data size
        if compress_type == Compression.RAW:
            data_size = w * h * bytes_per_pixel
            logger.debug('    data size = %sx%sx%s=%s bytes', w, h, bytes_per_pixel, data_size)

        elif compress_type == Compression.PACK_BITS:
            byte_counts = read_be_array("H", h, fp)
            sum_counts = sum(byte_counts)
            data_size = sum_counts * bytes_per_pixel
            logger.debug('    data size = %sx%s=%s bytes', sum_counts, bytes_per_pixel, data_size)

        elif compress_type == Compression.ZIP:
            data_size = channel.length - 2
            logger.debug('    data size = %s-2=%s bytes', channel.length, data_size)

        elif compress_type == Compression.ZIP_WITH_PREDICTION:
            data_size = channel.length - 2
            logger.debug('    data size = %s-2=%s bytes', channel.length, data_size)

        else:
            warnings.warn("Bad compression type %s" % compress_type)
            return []

        # read the data itself
        if data_size > channel.length:
            warnings.warn("Incorrect data size: %s > %s" % (data_size, channel.length))
        else:
            raw_data = fp.read(data_size)
            if compress_type in (Compression.RAW, Compression.PACK_BITS):
                data = raw_data
            elif compress_type == Compression.ZIP:
                data = zlib.decompress(raw_data)
            elif compress_type == Compression.ZIP_WITH_PREDICTION:
                decompressed = zlib.decompress(raw_data)
                data = compression.decode_prediction(decompressed, w, h, bytes_per_pixel)

            if data is None:
                return []

            channel_data.append(ChannelData(compress_type, data))

        remaining_bytes = channel.length - (fp.tell() - start_pos) - 2
        if remaining_bytes > 0:
            fp.seek(remaining_bytes, 1)
            logger.debug('    skipping %s bytes', remaining_bytes)

    return channel_data


def _read_global_mask_info(fp):
    """
    Reads global layer mask info.
    """
    # XXX: Does it really work properly? What is it for?
    start_pos = fp.tell()
    length = read_fmt("H", fp)[0]

    if length:
        overlay_color_space, c1, c2, c3, c4, opacity, kind = read_fmt("H 4H HB", fp)
        filler_length = length - (fp.tell()-start_pos)
        if filler_length > 0:
            fp.seek(filler_length, 1)
        return GlobalMaskInfo(overlay_color_space, (c1, c2, c3, c4), opacity, kind)
    else:
        return None

def read_image_data(fp, header):
    """
    Reads merged image pixel data which is stored at the end of PSD file.
    """
    w, h = header.width, header.height
    compress_type = read_fmt("H", fp)[0]

    bytes_per_pixel = header.depth // 8

    channel_byte_counts = []
    if compress_type == Compression.PACK_BITS:
        for ch in range(header.number_of_channels):
            channel_byte_counts.append(read_be_array("H", h, fp))

    channel_data = []
    for channel_id in range(header.number_of_channels):

        data = None

        if compress_type == Compression.RAW:
            data_size = w * h * bytes_per_pixel
            data = fp.read(data_size)

        elif compress_type == Compression.PACK_BITS:
            byte_counts = channel_byte_counts[channel_id]
            data_size = sum(byte_counts) * bytes_per_pixel
            data = fp.read(data_size)

        # are there any ZIP-encoded composite images in a wild?
        elif compress_type == Compression.ZIP:
            warnings.warn("ZIP compression of composite image is not supported.")

        elif compress_type == Compression.ZIP_WITH_PREDICTION:
            warnings.warn("ZIP_WITH_PREDICTION compression of composite image is not supported.")

        if data is None:
            return []
        channel_data.append(ChannelData(compress_type, data))

    return channel_data
