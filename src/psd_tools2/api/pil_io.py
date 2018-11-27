"""
PIL IO module.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools2.psd.image_data import ImageData
from psd_tools2.constants import ColorMode

logger = logging.getLogger(__name__)


def get_color_mode(mode):
    """
    Convert PIL mode to ColorMode.
    """
    name = mode.upper()
    name = name.rstrip('A')  # Trim alpha.
    name = {'1': 'BITMAP', 'L': 'GRAYSCALE'}.get(name, name)
    return getattr(ColorMode, name)


def get_pil_mode(value, alpha=False):
    name = value.name
    name = {'GRAYSCALE': 'L', 'BITMAP': '1'}.get(name, name)
    if alpha:
        name += 'A'
    return name


def convert_image_data_to_pil(psd):
    from PIL import Image
    channels = []
    header = psd.header
    if header.color_mode == ColorMode.BITMAP:
        raise NotImplementedError
    size = (header.width, header.height)
    for channel_data in psd.image_data.get_data(header):
        channels.append(Image.frombytes('L', size, channel_data, 'raw'))
    # if psd.layer_and_mask_information.layer_info.layer_count < 0:
    #     alpha = True
    alpha = (header.channels - ColorMode.channels(header.color_mode)) > 0
    mode = get_pil_mode(header.color_mode, alpha)
    image = Image.merge(mode, channels)
    return _remove_white_background(image)


def convert_pil_to_image_data(header, image):
    raw_data = b''.join(channel.tobytes() for channel in image.split())
    return ImageData


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
