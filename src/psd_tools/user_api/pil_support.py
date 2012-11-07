# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, division

import warnings
from psd_tools.utils import be_array_from_bytes
from psd_tools.constants import Compression, ChannelID, ColorMode, ImageResourceID

try:
    from PIL import Image, ImageCms
    if hasattr(Image, 'frombytes'):
        frombytes = Image.frombytes
    else:
        frombytes = Image.fromstring

except ImportError:
    Image = None


def extract_layer_image(decoded_data, layer_index):
    """
    Converts a layer from the ``decoded_data`` to a PIL image.
    """
    layers = decoded_data.layer_and_mask_data.layers
    layer = layers.layer_records[layer_index]

    channels_data = layers.channel_image_data[layer_index]
    size = layer.width(), layer.height()
    channel_types = [info.id for info in layer.channels]

    return _channels_data_to_PIL(
        channels_data, channel_types, size,
        decoded_data.header.depth, get_icc_profile(decoded_data))

def extract_composite_image(decoded_data):
    """
    Converts a composite (merged) image from the ``decoded_data``
    to a PIL image.
    """
    header = decoded_data.header
    size = header.width, header.height

    if header.color_mode == ColorMode.RGB:

        if header.number_of_channels == 3:
            channel_types = [0, 1, 2]
        elif header.number_of_channels == 4:
            channel_types = [0, 1, 2, -1]
        else:
            warnings.warn("This number of channels (%d) is unsupported for this color mode (%s)" % (
                         header.number_of_channels, header.color_mode))
            return

    else:
        warnings.warn("Unsupported color mode (%s)" % header.color_mode)
        return

    return _channels_data_to_PIL(
        decoded_data.image_data,
        channel_types,
        size,
        header.depth,
        get_icc_profile(decoded_data),
    )


def _channels_data_to_PIL(channels_data, channel_types, size, depth, icc_profile):
    if Image is None:
        raise Exception("This module requires PIL (or Pillow) installed.")

    if size == (0, 0):
        return

    bands = {}

    for channel, channel_type in zip(channels_data, channel_types):

        pil_band = channel_id_to_PIL(channel_type)
        if pil_band is None:
            warnings.warn("Unsupported channel type (%d)" % channel_type)
            continue

        if channel.compression in [Compression.RAW, Compression.ZIP, Compression.ZIP_WITH_PREDICTION]:
            if depth == 8:
                im = _from_8bit_raw(channel.data, size)
            elif depth == 16:
                im = _from_16bit_raw(channel.data, size)
            elif depth == 32:
                im = _from_32bit_raw(channel.data, size)
            else:
                warnings.warn("Unsupported depth (%s)" % depth)
                continue

        elif channel.compression == Compression.PACK_BITS:
            if depth != 8:
                warnings.warn("Depth %s is unsupported for PackBits compression" % depth)
                continue
            im = frombytes('L', size, channel.data, "packbits", 'L')
        else:
            if Compression.is_known(channel.compression):
                warnings.warn("Compression method is not implemented (%s)" % channel.compression)
            else:
                warnings.warn("Unknown compression method (%s)" % channel.compression)
            continue

        bands[pil_band] = im.convert('L')

    mode = _get_mode(bands.keys())
    merged_image = Image.merge(mode, [bands[band] for band in mode])

    if icc_profile is not None:
        display_profile = ImageCms.createProfile('sRGB') # XXX: ImageCms.get_display_profile()?
        ImageCms.profileToProfile(merged_image, icc_profile, display_profile, inPlace=True)

    return merged_image


def channel_id_to_PIL(channel_id):
    BANDS_MAP = {
        ChannelID.RED: 'R',
        ChannelID.GREEN: 'G',
        ChannelID.BLUE: 'B',
        ChannelID.TRANSPARENCY_MASK: 'A'
    }
    return BANDS_MAP.get(channel_id, None)


def _get_mode(band_keys):
    for mode in ['RGBA', 'RGB']:
        if set(band_keys) == set(list(mode)):
            return mode

def _from_8bit_raw(data, size):
    return frombytes('L', size, data, "raw", 'L')

def _from_16bit_raw(data, size):
    im = frombytes('I', size, data, "raw", 'I;16B')
    return im.point(lambda i: i * (1/(256.0)))

def _from_32bit_raw(data, size):
    pixels = be_array_from_bytes("f", data)
    im = Image.new("F", size)
    im.putdata(pixels, 255, 0)
    return im

def get_icc_profile(decoded_data):
    """
    Returns ICC image profile (if it exists and was correctly decoded)
    """
    # fixme: move this function somewhere?
    icc_profiles = [res.data for res in decoded_data.image_resource_blocks
                   if res.resource_id == ImageResourceID.ICC_PROFILE]

    if not icc_profiles:
        return None

    icc_profile = icc_profiles[0]

    if isinstance(icc_profile, bytes): # profile was not decoded
        return None

    return icc_profile

def apply_opacity(im, opacity):
    """
    Applies opacity to an image.
    """
    if im.mode == 'RGB':
        im.putalpha(opacity)
        return im
    elif im.mode == 'RGBA':
        r, g, b, a = im.split()
        opacity_scale = opacity / 255
        a = a.point(lambda i: i*opacity_scale)
        return Image.merge('RGBA', [r, g, b, a])
    else:
        raise NotImplementedError()