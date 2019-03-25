"""
PIL IO module.
"""
from __future__ import absolute_import, unicode_literals
import logging
import io

from psd_tools.psd.image_data import ImageData
from psd_tools.constants import ColorMode, ChannelID

logger = logging.getLogger(__name__)


def get_color_mode(mode):
    """Convert PIL mode to ColorMode."""
    name = mode.upper()
    name = name.rstrip('A')  # Trim alpha.
    name = {'1': 'BITMAP', 'L': 'GRAYSCALE'}.get(name, name)
    return getattr(ColorMode, name)


def get_pil_mode(value, alpha=False):
    """Get PIL mode from ColorMode."""
    name = {
        'GRAYSCALE': 'L',
        'BITMAP': '1',
        'DUOTONE': 'L',
        'INDEXED': 'P',
    }.get(value, value)
    if alpha and name in ('L', 'RGB'):
        name += 'A'
    return name


def extract_pil_mode(psd):
    """Extract PIL mode from PSD."""
    alpha = _get_alpha_use(psd)
    return get_pil_mode(psd.header.color_mode, alpha)


def convert_image_data_to_pil(psd, apply_icc=True, **kwargs):
    """Convert ImageData to PIL Image."""
    from PIL import Image, ImageOps
    header = psd.header
    size = (header.width, header.height)
    channels = []
    for channel_data in psd.image_data.get_data(header):
        channels.append(_create_channel(size, channel_data, header.depth))
    alpha = _get_alpha_use(psd)
    mode = get_pil_mode(header.color_mode.name)
    if mode == 'P':
        image = Image.merge('L', channels[:(len(channels) - alpha)])
        image.putpalette(psd.color_mode_data.interleave())
    elif mode == 'MULTICHANNEL':
        image = channels[0]  # Multi-channel mode is a collection of alpha.
    else:
        image = Image.merge(mode, channels[:(len(channels) - alpha)])
    if mode == 'CMYK':
        image = image.point(lambda x: 255 - x)
    if apply_icc and 'ICC_PROFILE' in psd.image_resources:
        image = _apply_icc(image, psd.image_resources.get_data('ICC_PROFILE'))
    if alpha and mode in ('L', 'RGB'):
        image.putalpha(channels[-1])
    return _remove_white_background(image)


def convert_layer_to_pil(layer, apply_icc=True, **kwargs):
    """Convert Layer to PIL Image."""
    from PIL import Image
    header = layer._psd._record.header
    if header.color_mode == ColorMode.BITMAP:
        raise NotImplementedError
    width, height = layer.width, layer.height
    channels, alpha = [], None
    for ci, cd in zip(layer._record.channel_info, layer._channels):
        if ci.id in (ChannelID.USER_LAYER_MASK,
                     ChannelID.REAL_USER_LAYER_MASK):
            continue
        channel = cd.get_data(width, height, header.depth, header.version)
        channel_image = _create_channel(
            (width, height), channel, header.depth
        )
        if ci.id == ChannelID.TRANSPARENCY_MASK:
            alpha = channel_image
        else:
            channels.append(channel_image)
    mode = get_pil_mode(header.color_mode.name)
    channels = _check_channels(channels, header.color_mode)
    image = Image.merge(mode, channels)
    if mode == 'CMYK':
        image = image.point(lambda x: 255 - x)
    if alpha is not None:
        if mode in ('RGB', 'L'):
            image.putalpha(alpha)
        else:
            logger.debug('Alpha channel is not supported in %s' % (mode))

    if apply_icc and 'ICC_PROFILE' in layer._psd.image_resources:
        image = _apply_icc(
            image, layer._psd.image_resources.get_data('ICC_PROFILE')
        )
    return image


def convert_mask_to_pil(mask, real=True):
    """Convert Mask to PIL Image."""
    from PIL import Image
    header = mask._layer._psd._record.header
    channel_ids = [ci.id for ci in mask._layer._record.channel_info]
    if real and mask._has_real():
        width = mask._data.real_right - mask._data.real_left
        height = mask._data.real_bottom - mask._data.real_top
        channel = mask._layer._channels[
            channel_ids.index(ChannelID.REAL_USER_LAYER_MASK)
        ]
    else:
        width = mask._data.right - mask._data.left
        height = mask._data.bottom - mask._data.top
        channel = mask._layer._channels[
            channel_ids.index(ChannelID.USER_LAYER_MASK)
        ]
    data = channel.get_data(width, height, header.depth, header.version)
    return _create_channel((width, height), data, header.depth)


def convert_pattern_to_pil(pattern, version=1):
    """Convert Pattern to PIL Image."""
    from PIL import Image
    mode = get_pil_mode(pattern.image_mode.name, False)
    # The order is different here.
    size = pattern.data.rectangle[3], pattern.data.rectangle[2]
    channels = [
        _create_channel(size, c.get_data(version), c.pixel_depth).convert('L')
        for c in pattern.data.channels if c.is_written
    ]
    if len(channels) == len(mode) + 1:
        mode += 'A'  # TODO: Perhaps doesn't work for some modes.
    image = Image.merge(mode, channels)
    if mode == 'CMYK':
        image = image.point(lambda x: 255 - x)
    return image


def convert_thumbnail_to_pil(thumbnail, mode='RGB'):
    """Convert thumbnail resource."""
    from PIL import Image
    if thumbnail.fmt == 0:
        size = (thumbnail.width, thumbnail.height)
        stride = thumbnail.widthbytes
        return Image.frombytes('RGBX', size, thumbnail.data, 'raw', mode,
                                stride)
    elif thumbnail.fmt == 1:
        return Image.open(io.BytesIO(thumbnail.data))
    else:
        raise ValueError('Unknown thumbnail format %d' % (thumbnail.fmt))


def _get_alpha_use(psd):
    layer_info = psd._get_layer_info()
    if layer_info and layer_info.layer_count < 0:
        return True
    tagged_blocks = psd.layer_and_mask_information.tagged_blocks
    if tagged_blocks:
        keys = (
            'SAVING_MERGED_TRANSPARENCY',
            'SAVING_MERGED_TRANSPARENCY16',
            'SAVING_MERGED_TRANSPARENCY32',
        )
        for key in keys:
            if key in tagged_blocks:
                return True
    return False


def _create_channel(size, channel_data, depth):
    from PIL import Image
    if depth == 8:
        return Image.frombytes('L', size, channel_data, 'raw')
    elif depth == 16:
        image = Image.frombytes('I', size, channel_data, 'raw', 'I;16B')
        return image.point(lambda x: x * (1. / 256.)).convert('L')
    elif depth == 32:
        image = Image.frombytes('F', size, channel_data, 'raw', 'F;32BF')
        # TODO: Check grayscale range.
        return image.point(lambda x: x * (256.)).convert('L')
    else:
        raise ValueError('Unsupported depth: %g' % depth)


def _check_channels(channels, color_mode):
    expected_channels = ColorMode.channels(color_mode)
    if len(channels) > expected_channels:
        logger.warning('Channels mismatch: expected %g != given %g' % (
            expected_channels, len(channels)
        ))
        channels = channels[:expected_channels]
    elif len(channels) < expected_channels:
        raise ValueError('Channels mismatch: expected %g != given %g' % (
            expected_channels, len(channels)
        ))
    return channels


def _apply_icc(image, icc_profile):
    """Apply ICC Color profile."""
    from io import BytesIO
    try:
        from PIL import ImageCms
    except ImportError:
        logger.debug(
            'ICC profile found but not supported. Install little-cms.'
        )
        return image

    if image.mode not in ('RGB',):
        logger.debug('%s ICC profile is not supported.' % image.mode)
        return image

    try:
        in_profile = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
        out_profile = ImageCms.createProfile('sRGB')
        return ImageCms.profileToProfile(image, in_profile, out_profile)
    except ImageCms.PyCMSError as e:
        logger.warning('PyCMSError: %s' % (e))

    return image


def _remove_white_background(image):
    """Remove white background in the preview image."""
    from PIL import ImageMath, Image
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
