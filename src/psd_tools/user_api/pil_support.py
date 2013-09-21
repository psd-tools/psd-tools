# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, division

import warnings
from psd_tools.utils import be_array_from_bytes
from psd_tools.constants import Compression, ChannelID, ColorMode, ImageResourceID
from psd_tools.icc_profiles import GrayProfile

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

    channel_data = layers.channel_image_data[layer_index]
    size = layer.width(), layer.height()
    channel_ids = [info.id for info in layer.channels]

    return _channel_data_to_PIL(
        channel_data = channel_data,
        channel_ids = channel_ids,
        color_mode = decoded_data.header.color_mode,  # XXX?
        size = size,
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
    
    channel_ids = None
    if header.color_mode == ColorMode.RGB:
        if header.number_of_channels == 3:
            channel_ids = [0, 1, 2]
        elif header.number_of_channels == 4:
            channel_ids = [0, 1, 2, -1]

    elif header.color_mode == ColorMode.CMYK:
        if header.number_of_channels == 4:
            channel_ids = [0, 1, 2, 3]
        elif header.number_of_channels == 5:
            # XXX: how to distinguish
            # "4 CMYK + 1 alpha" and "4 CMYK + 1 spot"?
            channel_ids = [-1, 0, 1, 2, 3] # XXX: unchecked!

    elif header.color_mode == ColorMode.GRAYSCALE:
        if header.number_of_channels == 1:
            channel_ids = [0]
        elif header.number_of_channels == 2:
            channel_ids = [0, -1]
            
    else:
        warnings.warn("Unsupported color mode (%s)" % ColorMode.name_of(header.color_mode))
        return

    if channel_ids is None:
        warnings.warn("This number of channels (%d) is unsupported for this color mode (%s)" % (
                     header.number_of_channels, header.color_mode))
        return


    return _channel_data_to_PIL(
        channel_data = decoded_data.image_data,
        channel_ids = channel_ids,
        color_mode = header.color_mode,
        size = size,
        depth = header.depth,
        icc_profile = get_icc_profile(decoded_data),
    )


def _channel_data_to_PIL(channel_data, channel_ids, color_mode, size, depth, icc_profile): 
    if Image is None:
        raise Exception("This module requires PIL (or Pillow) installed.")

    if size == (0, 0):
        return

    bands = {}

    for channel, channel_id in zip(channel_data, channel_ids):

        pil_band = channel_id_to_PIL(channel_id, color_mode)
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

    sRGB = ImageCms.createProfile('sRGB')

    if color_mode == ColorMode.RGB:
        if 'A' in bands:
            merged_image = Image.merge('RGBA', [bands[key] for key in 'RGBA'])
        else:
            merged_image = Image.merge('RGB', [bands[key] for key in 'RGB'])
        output_profile = sRGB

    elif color_mode == ColorMode.CMYK:
        if 'A' in bands:
            # CMYK with alpha channels is not supported by PIL/Pillow
            # see https://github.com/python-imaging/Pillow/issues/257
            del bands['A']
            warnings.warn("CMYKA images are not supported; alpha channel is dropped")

        merged_image = Image.merge('CMYK', [bands[key] for key in 'CMYK'])
        # colors are inverted in Photoshop CMYK images; invert them back
        merged_image = frombytes('CMYK', size, merged_image.tobytes(), 'raw', 'CMYK;I')
        output_profile = sRGB

    elif color_mode == ColorMode.GRAYSCALE:
        if 'A' in bands:
            merged_image = Image.merge('LA', [bands[key] for key in 'LA'])
        else:
            merged_image = Image.merge('L', [bands[key] for key in 'L'])
        output_profile = GrayProfile
            
    else:
        raise NotImplementedError()

    if icc_profile is not None:
        try:
            if color_mode == ColorMode.CMYK:
                merged_image = ImageCms.profileToProfile(merged_image, icc_profile, output_profile, outputMode='RGB')
            else:
                ImageCms.profileToProfile(merged_image, icc_profile, output_profile, inPlace=True)
        except ImageCms.PyCMSError as e:
            warnings.warn(repr(e))

    return merged_image


def channel_id_to_PIL(channel_id, color_mode):
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
    if im.mode in ('RGB', 'L'):
        im.putalpha(opacity)
        return im
    elif im.mode in ('RGBA', 'LA'):
        bands = im.split()
        bands, a = bands[:-1], bands[-1]
        opacity_scale = opacity / 255
        a = a.point(lambda i: i*opacity_scale)
        result_im = Image.merge(im.mode, bands + (a,))
        im.paste(result_im) # Modify image passed in, to be consistent
        return im
    else:
        raise NotImplementedError()
