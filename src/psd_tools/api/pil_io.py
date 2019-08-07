"""
PIL IO module.
"""
from __future__ import absolute_import, unicode_literals
import logging
import io

from psd_tools.psd.image_data import ImageData
from psd_tools.constants import ColorMode, ChannelID, Resource

logger = logging.getLogger(__name__)


def get_color_mode(mode):
    """Convert PIL mode to ColorMode."""
    name = mode.upper()
    name = name.rstrip('A')  # Trim alpha.
    name = {'1': 'BITMAP', 'L': 'GRAYSCALE'}.get(name, name)
    return getattr(ColorMode, name)


def get_pil_mode(color_mode, alpha=False):
    """Get PIL mode from ColorMode."""
    name = {
        ColorMode.GRAYSCALE: 'L',
        ColorMode.BITMAP: '1',
        ColorMode.DUOTONE: 'L',
        ColorMode.INDEXED: 'P',
        ColorMode.MULTICHANNEL: 'L',  # TODO: Cannot support in PIL.
    }.get(color_mode, color_mode.name)
    if alpha and name in ('L', 'RGB'):
        name += 'A'
    return name


def get_pil_channels(pil_mode):
    """Get the number of channels for PIL modes."""
    return {
        '1': 1,
        'L': 1,
        'P': 1,
        'P': 1,
        'RGB': 3,
        'CMYK': 4,
        'YCbCr': 3,
        'LAB': 3,
        'HSV': 3,
        'I': 1,
        'F': 1,
    }.get(pil_mode, 3)


def convert_image_data_to_pil(psd, channel=None, apply_icc=True, **kwargs):
    """Convert ImageData to PIL Image.

    .. note:: Image resources contain extra alpha channels in these keys:
        `ALPHA_NAMES_UNICODE`, `ALPHA_NAMES_PASCAL`, `ALPHA_IDENTIFIERS`.
    """
    from PIL import Image
    size = (psd.width, psd.height)
    channels = []
    for channel_data in psd._record.image_data.get_data(psd._record.header):
        channels.append(_create_image(size, channel_data, psd.depth))
    alpha = _get_alpha_use(psd._record)
    mode = get_pil_mode(psd.color_mode)
    if mode == 'P':
        image = Image.merge('L', channels[:get_pil_channels(mode)])
        image.putpalette(psd._record.color_mode_data.interleave())
    elif mode == 'MULTICHANNEL':
        image = channels[0]  # Multi-channel mode is a collection of alpha.
    else:
        image = Image.merge(mode, channels[:get_pil_channels(mode)])
    if mode == 'CMYK':
        image = image.point(lambda x: 255 - x)
    if apply_icc and Resource.ICC_PROFILE in psd.image_resources:
        image = _apply_icc(
            image, psd.image_resources.get_data(Resource.ICC_PROFILE)
        )
    if alpha and mode in ('L', 'RGB'):
        image.putalpha(channels[-1])
    return _remove_white_background(image)


def convert_layer_to_pil(layer, channel=None, apply_icc=True, **kwargs):
    """Convert Layer to PIL Image."""
    from PIL import Image
    if channel is None:
        image = _merge_channels(layer)
        alpha = _get_channel(layer, ChannelID.TRANSPARENCY_MASK)
        apply_icc &= (Resource.ICC_PROFILE in layer._psd.image_resources)
    else:
        image = _get_channel(layer, channel)
        alpha = None
        apply_icc = False  # TODO: How can we apply ICC for a single channel?

    if not image or channel < 0:
        return image  # Return None, alpha or mask.

    # Fix inverted CMYK.
    if layer._psd.color_mode == ColorMode.CMYK:
        from PIL import ImageChops
        image = ImageChops.invert(image)

    # In Pillow, alpha channel is only available in RGB or L.
    if alpha and image.mode in ('RGB', 'L'):
        image.putalpha(alpha)

    if apply_icc:
        icc_profile = layer._psd.image_resources.get_data(Resource.ICC_PROFILE)
        image = _apply_icc(image, icc_profile)

    return image


def convert_pattern_to_pil(pattern, version=1):
    """Convert Pattern to PIL Image."""
    from PIL import Image
    mode = get_pil_mode(pattern.image_mode, False)
    # The order is different here.
    size = pattern.data.rectangle[3], pattern.data.rectangle[2]
    channels = [
        _create_image(size, c.get_data(version), c.pixel_depth).convert('L')
        for c in pattern.data.channels if c.is_written
    ]
    if mode in ('RGB', 'L') and len(channels) == len(mode) + 1:
        mode += 'A'  # TODO: Perhaps doesn't work for some modes.
    if mode == 'P':
        image = channels[0]
        image.putpalette([x for rgb in pattern.color_table for x in rgb])
    else:
        image = Image.merge(mode, channels[:len(mode)])
    if mode == 'CMYK':
        image = image.point(lambda x: 255 - x)
    return image


def convert_thumbnail_to_pil(thumbnail, mode='RGB'):
    """Convert thumbnail resource."""
    from PIL import Image
    if thumbnail.fmt == 0:
        size = (thumbnail.width, thumbnail.height)
        stride = thumbnail.widthbytes
        return Image.frombytes(
            'RGBX', size, thumbnail.data, 'raw', mode, stride
        )
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
        return any(key in tagged_blocks for key in keys)
    return False


def _merge_channels(layer):
    from PIL import Image
    mode = get_pil_mode(layer._psd.color_mode)
    channels = [
        _get_channel(layer, info.id) for info in layer._record.channel_info
        if info.id >= 0
    ]
    if any(image is None for image in channels):
        return None
    channels = _check_channels(channels, layer._psd.color_mode)
    return Image.merge(mode, channels)


def _get_channel(layer, channel):
    if channel == ChannelID.USER_LAYER_MASK:
        width = layer.mask._data.right - layer.mask._data.left
        height = layer.mask._data.bottom - layer.mask._data.top
    elif channel == ChannelID.REAL_USER_LAYER_MASK:
        width = layer.mask._data.real_right - layer.mask._data.real_left
        height = layer.mask._data.real_bottom - layer.mask._data.real_top
    else:
        width, height = layer.width, layer.height

    index = {info.id: i for i, info in enumerate(layer._record.channel_info)}
    if channel not in index:
        return None
    depth = layer._psd.depth
    channel_data = layer._channels[index[channel]]
    if width == 0 or height == 0 or len(channel_data.data) == 0:
        return None
    channel = channel_data.get_data(width, height, depth, layer._psd.version)
    return _create_image((width, height), channel, depth)


def _create_image(size, data, depth):
    from PIL import Image
    if depth == 8:
        return Image.frombytes('L', size, data, 'raw')
    elif depth == 16:
        image = Image.frombytes('I', size, data, 'raw', 'I;16B')
        return image.point(lambda x: x * (1. / 256.)).convert('L')
    elif depth == 32:
        image = Image.frombytes('F', size, data, 'raw', 'F;32BF')
        # TODO: Check grayscale range.
        return image.point(lambda x: x * (256.)).convert('L')
    elif depth == 1:
        return Image.frombytes('1', size, data, 'raw', '1;I')
    else:
        raise ValueError('Unsupported depth: %g' % depth)


def _check_channels(channels, color_mode):
    expected_channels = ColorMode.channels(color_mode)
    if len(channels) > expected_channels:
        # Seems possible when FilterMask is attached.
        logger.debug(
            'Channels mismatch: expected %g != given %g' %
            (expected_channels, len(channels))
        )
        channels = channels[:expected_channels]
    elif len(channels) < expected_channels:
        raise ValueError(
            'Channels mismatch: expected %g != given %g' %
            (expected_channels, len(channels))
        )
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

    if image.mode not in ('RGB', ):
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
                x=x,
                a=a
            ) for x in bands[:3]
        ]
        return Image.merge(bands=rgb + [a], mode="RGBA")

    return image
