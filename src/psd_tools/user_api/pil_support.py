# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, division

import warnings
import io
from psd_tools.utils import be_array_from_bytes
from psd_tools.constants import (
    Compression, ChannelID, ColorMode, ImageResourceID)
from psd_tools import icc_profiles

try:
    from PIL import Image, ImageDraw, ImageMath
    if hasattr(Image, 'frombytes'):
        frombytes = Image.frombytes
    else:
        frombytes = Image.fromstring  # PIL and older Pillow versions
except ImportError:
    Image = None
    ImageDraw = None

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
        channel_data=layers.channel_image_data[layer_index],
        channel_ids=_get_layer_channel_ids(layer),
        color_mode=decoded_data.header.color_mode,  # XXX?
        size=(layer.width(), layer.height()),
        depth=decoded_data.header.depth,
        icc_profile=get_icc_profile(decoded_data)
    )


def extract_layer_mask(decoded_data, layer_index, real_mask):
    """
    Converts a layer mask from the ``decoded_data`` to a PIL image.

    If ``real_mask`` is True, extract real mask consisting of both bitmap and
    vector mask.
    """
    layers = decoded_data.layer_and_mask_data.layers
    layer = layers.layer_records[layer_index]
    mask_data = layer.mask_data
    if not mask_data:
        return None
    real_mask = real_mask and mask_data.real_flags
    if real_mask:
        size = (mask_data.real_right - mask_data.real_left,
                mask_data.real_bottom - mask_data.real_top)
    else:
        size = (mask_data.right - mask_data.left,
                mask_data.bottom - mask_data.top)

    return _mask_data_to_PIL(
        channel_data=layers.channel_image_data[layer_index],
        channel_ids=_get_layer_channel_ids(layer),
        size=size,
        depth=decoded_data.header.depth,
        real_mask=real_mask
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
        warnings.warn(
            "This number of channels (%d) is unsupported for this color mode"
            "(%s)" % (header.number_of_channels, header.color_mode))
        return
    if len(channel_ids) > len(decoded_data.image_data):
        warnings.warn("Image data is broken")
        return

    image = _channel_data_to_PIL(
        channel_data=decoded_data.image_data,
        channel_ids=channel_ids,
        color_mode=header.color_mode,
        size=size,
        depth=header.depth,
        icc_profile=get_icc_profile(decoded_data)
    )

    # Composed image is blended into white background. Remove here.
    return _remove_white_background(image)


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

    if isinstance(icc_profile, bytes):  # profile was not decoded
        return None

    return icc_profile


def apply_opacity(im, opacity):
    """ Apply opacity to an image. """
    if im.mode in ('RGBA', 'LA'):
        channels = list(im.split())
        opacity_scale = opacity / 255.
        channels[-1] = channels[-1].point(lambda i: int(i * opacity_scale))
        return Image.merge(im.mode, channels)
    elif im.mode in ('RGB', 'L'):
        im.putalpha(opacity)
        return im
    else:
        warnings.warn("%s converted to RGB" % im.mode)
        im = im.convert('RGB')
        im.putalpha(opacity)
        return im


def pattern_to_PIL(pattern):
    channels = [_decompress_pattern_channel(c) for c in pattern.data.channels]
    if not all(channels):
        return None

    image = None
    if len(channels) == 1:
        image = channels[0]
    elif len(channels) == 3:
        image = Image.merge('RGB', channels)
    elif len(channels) == 4:
        image = Image.merge('RGBA', channels)
    return image


def draw_polygon(bbox, anchors, fill=(255, 255, 255, 255)):
    image = Image.new("RGBA", (bbox.width, bbox.height),
                      color=(255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.polygon(anchors, fill=fill)
    del draw
    return image


def extract_thumbnail(resource, mode="RGB"):
    if resource.format == 0:
        size = (resource.width, resource.height)
        stride = resource.widthbytes
        image = frombytes('RGBX', size, data.value, 'raw', mode, stride)
    elif resource.format == 1:
        image = Image.open(io.BytesIO(resource.data.value))
    return image


def _channel_data_to_PIL(channel_data, channel_ids, color_mode, size, depth,
                         icc_profile):
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
                merged_image = ImageCms.profileToProfile(
                    merged_image, icc_profile, icc_profiles.sRGB,
                    outputMode='RGB')
            elif color_mode == ColorMode.GRAYSCALE:
                ImageCms.profileToProfile(
                    merged_image, icc_profile, icc_profiles.gray,
                    inPlace=True, outputMode='L')
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
            continue

        im = _decompress_channel(channel, depth, size)
        if im:
            bands[pil_band] = im
    return bands


def _mask_data_to_PIL(channel_data, channel_ids, size, depth, real_mask):
    target_id = (
        ChannelID.REAL_USER_LAYER_MASK if real_mask
        else ChannelID.USER_LAYER_MASK
    )
    for channel, channel_id in zip(channel_data, channel_ids):
        if channel_id == target_id:
            return _decompress_channel(channel, depth, size)
    return None


def _decompress_channel(channel, depth, size):
    if channel.compression in (Compression.RAW, Compression.ZIP,
                               Compression.ZIP_WITH_PREDICTION):
        if depth == 8:
            im = _from_8bit_raw(channel.data, size)
        elif depth == 16:
            im = _from_16bit_raw(channel.data, size)
        elif depth == 32:
            im = _from_32bit_raw(channel.data, size)
        else:
            warnings.warn("Unsupported depth (%s)" % depth)
            return None

    elif channel.compression == Compression.PACK_BITS:
        if depth != 8:
            warnings.warn(
                "Depth %s is unsupported for PackBits compression" % depth)
        im = frombytes('L', size, channel.data, "packbits", 'L')
    else:
        if Compression.is_known(channel.compression):
            warnings.warn(
                "Compression method is not implemented "
                "(%s)" % channel.compression)
        else:
            warnings.warn(
                "Unknown compression method (%s)" % channel.compression)
        return None
    return im.convert('L')


def _decompress_pattern_channel(channel):
    depth = channel.depth
    size = (channel.rectangle[3], channel.rectangle[2])
    if channel.compression in (Compression.RAW, Compression.ZIP,
                               Compression.ZIP_WITH_PREDICTION):
        if depth == 8:
            im = _from_8bit_raw(channel.data.value, size)
        elif depth == 16:
            im = _from_16bit_raw(channel.data.value, size)
        elif depth == 32:
            im = _from_32bit_raw(channel.data.value, size)
        else:
            warnings.warn("Unsupported depth (%s)" % depth)
            return None
    elif channel.compression == Compression.PACK_BITS:
        if depth != 8:
            warnings.warn(
                "Depth %s is unsupported for PackBits compression" % depth)
        try:
            import packbits
            channel_data = packbits.decode(channel.data.value)
        except ImportError as e:
            warnings.warn("Install packbits (%s)" % e)
            channel_data = b'\x00' * (size[0] * size[1])  # Default fill
        except IndexError as e:
            warnings.warn("Failed to decode pattern (%s)" % e)
            channel_data = b'\x00' * (size[0] * size[1])  # Default fill
        # Packbit pattern tends not to have the correct size ???
        padding = len(channel_data) - size[0] * size[1]
        if padding < 0:
            warnings.warn('Broken pattern data (%g for %g)' % (
                len(channel_data), size[0] * size[1]))
            channel_data += b'\x00' * -padding  # Append default fill
            padding = 0
        im = frombytes('L', size, channel_data[padding:], "raw", 'L')
    else:
        if Compression.is_known(channel.compression):
            warnings.warn(
                "Compression method is not implemented "
                "(%s)" % channel.compression)
        else:
            warnings.warn(
                "Unknown compression method (%s)" % channel.compression)
        return None
    return im.convert('L')


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
        elif channel_id in (ChannelID.USER_LAYER_MASK,
                            ChannelID.REAL_USER_LAYER_MASK):
            return None
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
        elif header.number_of_channels >= 4:
            if header.number_of_channels > 4:
                warnings.warn("header.number_of_channels = %d > 4" % (
                    header.number_of_channels))
            return [0, 1, 2, ChannelID.TRANSPARENCY_MASK]

    elif header.color_mode == ColorMode.CMYK:
        if header.number_of_channels == 4:
            return [0, 1, 2, 3]
        elif header.number_of_channels >= 5:
            # XXX: how to distinguish
            # "4 CMYK + 1 alpha" and "4 CMYK + 1 spot"?
            if header.number_of_channels > 5:
                warnings.warn("header.number_of_channels = %d > 5" % (
                    header.number_of_channels))
            return [0, 1, 2, 3, ChannelID.TRANSPARENCY_MASK]

    elif header.color_mode == ColorMode.GRAYSCALE:
        if header.number_of_channels == 1:
            return [0]
        elif header.number_of_channels >= 2:
            if header.number_of_channels > 2:
                warnings.warn("header.number_of_channels = %d > 2" % (
                    header.number_of_channels))
            return [0, ChannelID.TRANSPARENCY_MASK]

    else:
        warnings.warn("Unsupported color mode (%s)" % header.color_mode)


def _get_layer_channel_ids(layer):
    return [info.id for info in layer.channels]


def _remove_white_background(image):
    """Remove white background in the preview image."""
    if image.mode == "RGBA":
        bands = image.split()
        a = bands[3]
        rgb = [
            ImageMath.eval(
                'convert('
                'float(x + a - 255) * 255.0 / float(max(a, 1)) * '
                'float(min(a, 1)) + float(x) * float(1 - min(a, 1))'
                ', "L")',
                x=x, a=a
            )
            for x in bands[:3]
        ]
        return Image.merge(bands=rgb + [a], mode="RGBA")

    return image
