"""
PIL IO module.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools2.psd.image_data import ImageData
from psd_tools2.constants import ColorMode, ChannelID

logger = logging.getLogger(__name__)


def get_color_mode(mode):
    """Convert PIL mode to ColorMode."""
    name = mode.upper()
    name = name.rstrip('A')  # Trim alpha.
    name = {'1': 'BITMAP', 'L': 'GRAYSCALE'}.get(name, name)
    return getattr(ColorMode, name)


def get_pil_mode(value, alpha=False):
    """Get PIL mode from ColorMode."""
    name = value.name
    name = {'GRAYSCALE': 'L', 'BITMAP': '1'}.get(name, name)
    if alpha:
        name += 'A'
    return name


def convert_image_data_to_pil(psd):
    """Convert ImageData to PIL Image."""
    from PIL import Image
    header = psd.header
    if header.color_mode == ColorMode.BITMAP:
        raise NotImplementedError
    size = (header.width, header.height)
    channels = []
    for channel_data in psd.image_data.get_data(header):
        channels.append(Image.frombytes('L', size, channel_data, 'raw'))
    alpha = _get_alpha_use(psd)
    channel_size = ColorMode.channels(header.color_mode, alpha)
    if len(channels) < channel_size:
        logger.warning('Incorrect channel size: %d vs %d' % (
            len(channels), channel_size)
        )
        channel_size = len(channels)
        alpha = False
    mode = get_pil_mode(header.color_mode, alpha)
    image = Image.merge(mode, channels[:channel_size])
    return _remove_white_background(image)


def convert_layer_to_pil(layer):
    """Convert Layer to PIL Image."""
    from PIL import Image
    header = layer._psd.header
    if header.color_mode == ColorMode.BITMAP:
        raise NotImplementedError
    width, height = layer.width, layer.height
    channels, alpha = [], None
    for ci, cd in zip(layer._record.channel_info, layer._channels):
        if ci.id in (ChannelID.USER_LAYER_MASK,
                     ChannelID.REAL_USER_LAYER_MASK):
            continue
        channel = cd.get_data(width, height, header.depth, header.version)
        channel_image = Image.frombytes('L', (width, height), channel, 'raw')
        if ci.id == ChannelID.TRANSPARENCY_MASK:
            alpha = channel_image
        else:
            channels.append(channel_image)
    if alpha is not None:
        mode = get_pil_mode(header.color_mode, True)
        image = Image.merge(mode, channels + [alpha])
    else:
        mode = get_pil_mode(header.color_mode, False)
        image = Image.merge(mode, channels)
    return image


def convert_mask_to_pil(mask, real=True):
    """Convert Mask to PIL Image."""
    from PIL import Image
    header = mask._layer._psd.header
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
    return Image.frombytes('L', (width, height), data, 'raw')


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
