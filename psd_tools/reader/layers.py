# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, division, print_function
import collections
import logging
import warnings
import zlib
import array

from psd_tools.utils import (read_fmt, read_pascal_string,
                             read_be_array, be_array_from_bytes,
                             trimmed_repr, pad, synchronize, debug_view)
from psd_tools.exceptions import Error
from psd_tools.constants import (Compression, Clipping, BlendMode,
                                 ChannelID, TaggedBlock)

logger = logging.getLogger(__name__)

_LayerRecord = collections.namedtuple('LayerRecord', [
    'top', 'left', 'bottom', 'right',
    'num_channels', 'channels',
    'blend_mode', 'opacity', 'cilpping', 'flags',
    'mask_data', 'blending_ranges', 'name',
    'tagged_blocks'
])

class LayerRecord(_LayerRecord):

    def width(self):
        return self.right - self.left

    def height(self):
        return self.bottom - self.top



Layers = collections.namedtuple('Layers', 'length, layer_count, layer_records, channel_image_data')
LayerFlags = collections.namedtuple('LayerFlags', 'transparency_protected visible')
LayerAndMaskData = collections.namedtuple('LayerAndMaskData', 'layers global_mask_info tagged_blocks')
ChannelInfo = collections.namedtuple('ChannelInfo', 'id length')
_MaskData = collections.namedtuple('MaskData', 'top left bottom right default_color flags real_flags real_background')
LayerBlendingRanges = collections.namedtuple('LayerBlendingRanges', 'composite_ranges channel_ranges')
_ChannelData = collections.namedtuple('ChannelData', 'compression data')
_Block = collections.namedtuple('Block', 'key data')
GlobalMaskInfo = collections.namedtuple('GlobalMaskInfo', 'overlay color_components opacity kind')

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

class Block(_Block):
    """
    Layer tagged block with extra info.
    """
    def __repr__(self):
        return "Block(%s %s, %s)" % (self.key, TaggedBlock.name_of(self.key),
                                     trimmed_repr(self.data))


def read(fp, encoding, depth):
    """
    Reads layers and masks information.
    """
    length = read_fmt("I", fp)[0]
    start_position = fp.tell()

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
    if length is None:
        length = read_fmt("I", fp)[0]
    layer_count = read_fmt("h", fp)[0]

    layer_records = []
    for idx in range(abs(layer_count)):
        layer = _read_layer_record(fp, encoding)
        layer_records.append(layer)

    channel_image_data = []
    for layer in layer_records:
        data = _read_channel_image_data(fp, layer, depth)
        channel_image_data.append(data)

    return Layers(length, layer_count, layer_records, channel_image_data)

def _read_layer_record(fp, encoding):
    """
    Reads single layer record.
    """
    top, left, bottom, right, num_channels = read_fmt("4i H", fp)

    channel_info = []
    for channel_num in range(num_channels):
        info = ChannelInfo(*read_fmt("hI", fp))
        channel_info.append(info)

    sig = fp.read(4)
    if sig != b'8BIM':
        raise Error("Error parsing layer: invalid signature (%r)" % sig)

    blend_mode = fp.read(4).decode('ascii')
    if not BlendMode.is_known(blend_mode):
        warnings.warn("Unknown blend mode (%s)" % blend_mode)

    opacity, clipping, flags, extra_length = read_fmt("BBBxI", fp)

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


def _decompress_raw(fp, w, h, bytes_per_pixel):
    data_size = w * h * bytes_per_pixel
    data = fp.read(data_size)
    return ChannelData(Compression.RAW, data)

def _decompress_packbits(fp, byte_counts, h, bytes_per_pixel):
    data = fp.read(sum(byte_counts) * bytes_per_pixel)
    return ChannelData(Compression.PACK_BITS, data)

def _decompress_zip(fp, channel_length):
    compressed_data = fp.read(channel_length)
    decompressed = zlib.decompress(compressed_data)
    return ChannelData(Compression.ZIP, decompressed)

def _decompress_zip_with_prediction(fp, w, h, bytes_per_pixel, channel_length):
    compressed_data = fp.read(channel_length)
    decompressed = zlib.decompress(compressed_data)

    def delta_decode(fmt, mod, data, w, h):
        arr = be_array_from_bytes(fmt, data)
        for y in range(h):
            offset = y*w
            for x in range(w-1):
                pos = offset + x
                next_value = (arr[pos+1] + arr[pos]) % mod
                arr[pos+1] = next_value
        arr.byteswap()
        return arr

    if bytes_per_pixel == 1:
        arr = delta_decode("B", 2**8, decompressed, w, h)

    elif bytes_per_pixel == 2:
        arr = delta_decode("H", 2**16, decompressed, w, h)

    elif bytes_per_pixel == 4:

        # 32bit channels are also encoded using delta encoding,
        # but it make no sense to apply delta compression to bytes.
        # It is possible to apply delta compression to 2-byte or 4-byte
        # words, but it seems it is not the best way either.
        # In PSD, each 4-byte item is split into 4 bytes and these
        # bytes are packed together: "123412341234" becomes "111222333444";
        # delta compression is applied to the packed data.
        #
        # So we have to (a) decompress data from the delta compression
        # and (b) recombine data back to 4-byte values.

        bytes_array = delta_decode("B", 2**8, decompressed, w*4, h)

        # restore 4-byte items.
        # XXX: this is very slow written in Python.
        arr = array.array(str("B"))
        for y in range(h):
            row_start = y*w*4
            offsets = row_start, row_start+w, row_start+w*2, row_start+w*3
            for x in range(w):
                for bt in range(4):
                    arr.append(bytes_array[offsets[bt] + x])

        arr = array.array(str("f"), arr.tostring())
    else:
        return None


    return ChannelData(Compression.ZIP_WITH_PREDICTION, arr.tostring())


def _read_channel_image_data(fp, layer, depth):
    """
    Reads image data for all channels in a layer.
    """
    channel_data = []

    bytes_per_pixel = depth // 8

    for channel in layer.channels:
        if channel.id == ChannelID.USER_LAYER_MASK:
            w, h = layer.mask_data.width(), layer.mask_data.height()
        else:
            w, h = layer.width(), layer.height()

        start_pos = fp.tell()
        compression = read_fmt("H", fp)[0]

        data = None

        if compression == Compression.RAW:
            data = _decompress_raw(fp, w, h, bytes_per_pixel)

        elif compression == Compression.PACK_BITS:
            byte_counts = read_be_array("H", h, fp)
            data = _decompress_packbits(fp, byte_counts, h, bytes_per_pixel)

        elif compression == Compression.ZIP:
            data = _decompress_zip(fp, channel.length-2)

        elif compression == Compression.ZIP_WITH_PREDICTION:
            data = _decompress_zip_with_prediction(fp, w, h, bytes_per_pixel, channel.length-2)

        if data is None:
            return []
        channel_data.append(data)

        remaining_bytes = channel.length - (fp.tell() - start_pos) - 2
        if remaining_bytes > 0:
            fp.seek(remaining_bytes, 1)

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
    compression = read_fmt("H", fp)[0]

    bytes_per_pixel = header.depth // 8

    channel_byte_counts = []
    if compression == Compression.PACK_BITS:
        for ch in range(header.number_of_channels):
            channel_byte_counts.append(read_be_array("H", h, fp))

    channel_data = []
    for channel_id in range(header.number_of_channels):

        data = None

        if compression == Compression.RAW:
            data = _decompress_raw(fp, w, h, bytes_per_pixel)

        elif compression == Compression.PACK_BITS:
            byte_counts = channel_byte_counts[channel_id]
            data = _decompress_packbits(fp, byte_counts, h, bytes_per_pixel)

        elif compression == Compression.ZIP:
            warnings.warn("ZIP compression of composite image is not supported.")

        elif compression == Compression.ZIP_WITH_PREDICTION:
            warnings.warn("ZIP_WITH_PREDICTION compression of composite image is not supported.")

        if data is None:
            return []
        channel_data.append(data)

    return channel_data
