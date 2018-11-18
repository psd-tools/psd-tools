"""
PIL IO module.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools2.psd.image_data import ImageData
from psd_tools2.constants import ColorMode

try:
    from PIL import Image
except ImportError:
    Image = None

logger = logging.getLogger(__name__)


def get_color_mode(mode):
    """
    Convert PIL mode to ColorMode.
    """
    name = mode.upper()
    name = name.rstrip('A')  # Trim alpha.
    name = {'L': 'GRAYSCALE'}.get(name, name)
    return getattr(ColorMode, name)


def get_pil_mode(value, alpha=True):
    name = value.name
    name = {'GRAYSCALE': 'L'}.get(name, name)
    if alpha:
        name += 'A'
    return name


def convert_image_data_to_pil(psd):
    assert Image, 'PIL package is missing'
    channels = []
    header = psd.header
    size = (header.width, header.height)
    for channel_data in psd.image_data.get_data(psd.header):
        channels.append(Image.frombytes('L', size, channel_data, 'raw'))
    alpha = (header.channels - ColorMode.channels(header.color_mode)) > 0
    mode = get_pil_mode(header.color_mode, alpha)
    return Image.merge(mode, channels)


def convert_pil_to_image_data(header, image):
    raw_data = b''.join(channel.tobytes() for channel in image.split())
    return ImageData