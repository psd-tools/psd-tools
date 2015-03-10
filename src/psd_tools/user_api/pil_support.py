# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, division

import warnings
from psd_tools.utils import be_array_from_bytes
from psd_tools.constants import Compression, ChannelID, ColorMode, ImageResourceID
from psd_tools import icc_profiles

try:
    from PIL import Image
    if hasattr(Image, 'frombytes'):
        frombytes = Image.frombytes
    else:
        frombytes = Image.fromstring  # PIL and older Pillow versions
except ImportError:
    Image = None

try:
    from PIL import ImageCms
except ImportError:
    ImageCms = None


def tobytes(image):
    # Some versions of PIL are missing the tobytes alias for tostring
    if hasattr(image, 'tobytes'):
        return image.tobytes()
    else:
        return image.tostring()


def extract_layer_image(decoded_data, layer_index):
    """
    Converts a layer from the ``decoded_data`` to a PIL image.
    """
    layers = decoded_data.layer_and_mask_data.layers
    layer = layers.layer_records[layer_index]

    return _channel_data_to_PIL(
        channel_data = layers.channel_image_data[layer_index],
        channel_ids = _get_layer_channel_ids(layer),
        color_mode = decoded_data.header.color_mode,  # XXX?
        size = (layer.width(), layer.height()),
        depth = decoded_data.header.depth,
        icc_profile = get_icc_profile(decoded_data)
    )


def extract_composite_image(decoded_data):
    """
    Converts a composite (merged) image from the ``decoded_data``
    to a PIL image.
    """
    header = decoded_data.header
    size = header.width, header.height
    if size == (0, 0):
        return

    channel_ids = _get_header_channel_ids(header)
    if channel_ids is None:
        warnings.warn("This number of channels (%d) is unsupported for this color mode (%s)" % (
                     header.number_of_channels, header.color_mode))
        return

    return _channel_data_to_PIL(
        channel_data=decoded_data.image_data,
        channel_ids=channel_ids,
        color_mode=header.color_mode,
        size=size,
        depth=header.depth,
        icc_profile=get_icc_profile(decoded_data)
    )


def get_icc_profile(decoded_data):
    """
    Return ICC image profile if it exists and was correctly decoded
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
    """ Apply opacity to an image. """
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


def _channel_data_to_PIL(channel_data, channel_ids, color_mode, size, depth, icc_profile):
    bands = _get_band_images(
        channel_data=channel_data,
        channel_ids=channel_ids,
        color_mode=color_mode,
        size=size,
        depth=depth
    )
    return _merge_bands(bands, color_mode, size, icc_profile)


def _merge_bands(bands, color_mode, size, icc_profile):
    if Image is None:
        raise Exception("This module requires PIL (or Pillow) installed.")

    if color_mode == ColorMode.RGB:
        merged_image = Image.merge('RGB', [bands[key] for key in 'RGB'])
    elif color_mode == ColorMode.CMYK:
        merged_image = Image.merge('CMYK', [bands[key] for key in 'CMYK'])
        merged_bytes = tobytes(merged_image)
        # colors are inverted in Photoshop CMYK images; invert them back
        merged_image = frombytes('CMYK', size, merged_bytes, 'raw', 'CMYK;I')
    elif color_mode == ColorMode.GRAYSCALE:
        merged_image = bands['L']
    else:
        raise NotImplementedError()

    if icc_profile is not None:
        assert ImageCms is not None
        try:
            if color_mode in [ColorMode.RGB, ColorMode.CMYK]:
                merged_image = ImageCms.profileToProfile(merged_image, icc_profile, icc_profiles.sRGB, outputMode='RGB')
            elif color_mode == ColorMode.GRAYSCALE:
                ImageCms.profileToProfile(merged_image, icc_profile, icc_profiles.gray, inPlace=True, outputMode='L')
        except ImageCms.PyCMSError as e:
            # PIL/Pillow/(old littlecms?) can't convert some ICC profiles
            warnings.warn(repr(e))

    if color_mode == ColorMode.CMYK:
        merged_image = merged_image.convert('RGB')

    alpha = bands.get('A')
    if alpha:
        merged_image.putalpha(alpha)

    return merged_image


def _get_band_images(channel_data, channel_ids, color_mode, size, depth):
    bands = {}
    for channel, channel_id in zip(channel_data, channel_ids):

        pil_band = _channel_id_to_PIL(channel_id, color_mode)
        if pil_band is None:
            warnings.warn("Unsupported channel type (%d)" % channel_id)
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
    return bands


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


def _channel_id_to_PIL(channel_id, color_mode):
    if ChannelID.is_known(channel_id):
        if channel_id == ChannelID.TRANSPARENCY_MASK:
            return 'A'
        warnings.warn("Channel %s (%s) is not handled" % (channel_id, ChannelID.name_of(channel_id)))
        return None

    try:
        assert channel_id >= 0
        if color_mode == ColorMode.RGB:
            return 'RGB'[channel_id]
        elif color_mode == ColorMode.CMYK:
            return 'CMYK'[channel_id]
        elif color_mode == ColorMode.GRAYSCALE:
            return 'L'[channel_id]

    except IndexError:
        # spot channel
        warnings.warn("Spot channel %s is not handled" % channel_id)
        return None


def _get_header_channel_ids(header):

    if header.color_mode == ColorMode.RGB:
        if header.number_of_channels == 3:
            return [0, 1, 2]
        elif header.number_of_channels == 4:
            return [0, 1, 2, ChannelID.TRANSPARENCY_MASK]

    elif header.color_mode == ColorMode.CMYK:
        if header.number_of_channels == 4:
            return [0, 1, 2, 3]
        elif header.number_of_channels == 5:
            # XXX: how to distinguish
            # "4 CMYK + 1 alpha" and "4 CMYK + 1 spot"?
            return [0, 1, 2, 3, ChannelID.TRANSPARENCY_MASK]

    elif header.color_mode == ColorMode.GRAYSCALE:
        if header.number_of_channels == 1:
            return [0]
        elif header.number_of_channels == 2:
            return [0, ChannelID.TRANSPARENCY_MASK]

    else:
        warnings.warn("Unsupported color mode (%s)" % header.color_mode)


def _get_layer_channel_ids(layer):
    return [info.id for info in layer.channels]
