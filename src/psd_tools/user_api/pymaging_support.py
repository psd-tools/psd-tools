# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import warnings
import array

try:
    from pymaging import Image
    from pymaging.colors import RGB, RGBA
    from pymaging.pixelarray import get_pixel_array
except ImportError:
    Image = None

from psd_tools.constants import ColorMode, Compression

def extract_composite_image(decoded_data):
    """
    Converts a composite (merged) image from the ``decoded_data``
    to a pymaging.Image.
    """
    if Image is None:
        raise Exception("This module requires `pymaging` library installed.")

    header = decoded_data.header
    size = header.width, header.height

    if header.color_mode != ColorMode.RGB:
        raise NotImplementedError(
            "This color mode (%s) is not supported yet" % ColorMode.name_of(header.color_mode)
        )

    if header.depth != 8:
        raise NotImplementedError("Only 8bit images are currently supported with pymaging.")

    if header.number_of_channels == 3:
        mode = RGB
    elif header.number_of_channels == 4:
        mode = RGBA
    else:
        raise NotImplementedError("This number of channels (%d) is unsupported for this color mode (%s)" % (
                         header.number_of_channels, header.color_mode))

    return _channels_data_to_image(decoded_data.image_data,
        mode,
        size,
        header.depth,
    )


def _channels_data_to_image(channels_data, mode, size, depth):

    if size == (0, 0):
        return

    num_channels = mode.length
    assert depth == 8
    assert len(channels_data) == num_channels

    total_size = size[0]*size[1]*num_channels

    image_bytes = array.array(str("B"), [0]*total_size)

    for index, channel in enumerate(channels_data):
        if channel.compression == Compression.PACK_BITS:
            raise NotImplementedError("PackBits decompression is not implemented for pymaging")

        image_bytes[index::num_channels] = array.array(str("B"), channel.data)

    pixels = get_pixel_array(image_bytes, size[0], size[1], mode.length)

    return Image(pixels, mode)
