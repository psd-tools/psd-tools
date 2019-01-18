"""
Composer module.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools2.api.pil_io import extract_pil_mode

logger = logging.getLogger(__name__)


def extract_bbox(layers):
    """
    Returns a bounding box for ``layers`` or (0, 0, 0, 0) if the layers
    have no bounding box.
    """
    if not hasattr(layers, '__iter__'):
        layers = [layers]
    bboxes = [
        layer.bbox for layer in layers
        if layer.is_visible() and not layer.bbox == (0, 0, 0, 0)
    ]
    if len(bboxes) == 0:  # Empty bounding box.
        return (0, 0, 0, 0)
    lefts, tops, rights, bottoms = zip(*bboxes)
    return (min(lefts), min(tops), max(rights), max(bottoms))


def intersect(*bboxes):
    if len(bboxes) == 0:
        return (0, 0, 0, 0)

    lefts, tops, rights, bottoms = zip(*bboxes)
    result = (max(lefts), max(tops), min(rights), min(bottoms))
    if result[2] <= result[0] or result[3] <= result[1]:
        return (0, 0, 0, 0)

    return result


def _blend(target, image, offset, mask=None):
    if target.mode == 'RGBA':
        target.alpha_composite(image.convert('RGBA'), offset)
    elif target.mode in ('LA', 'CMYKA'):
        tmp = target.convert('RGBA')
        tmp.alpha_composite(tmp, image.convert('RGBA'), offset)
        target = tmp.convert(target.mode)
    else:
        target.paste(image, offset, mask=mask)

    return target


def compose(layers, bbox=None, layer_filter=None, color=None):
    """
    Compose layers to a single ``PIL.Image``.

    In order to skip some layers, pass ``layer_filter`` function which
    should take ``layer`` as an argument and return True to keep the layer
    or return False to skip. By default, layers that satisfies the following
    condition is composed::

        layer.has_pixels() and layer.is_visible()

    Currently the following are ignored:

     - Clipping layers.
     - Layers that do not have associated pixels in the file.
     - Adjustments layers.
     - Layer effects.
     - Blending mode (all blending modes become normal).

    This function is experimental and does not guarantee Photoshop-quality
    rendering.

    :param layers: a layer, or an iterable of layers.
    :param bbox: (left, top, bottom, right) tuple that specifies a region to
        compose. By default, all the visible area is composed. The origin
        is at the top-left corner of the PSD document.
    :param layer_filter: a callable that takes a layer and returns bool.
    :param color: background color in int or tuple.
    :return: PIL Image or None.
    """
    from PIL import Image

    if not hasattr(layers, '__iter__'):
        layers = [layers]

    def _default_filter(layer):
        return layer.is_visible() and layer.has_pixels()

    layer_filter = layer_filter or _default_filter
    valid_layers = [x for x in layers if layer_filter(x)]
    if len(valid_layers) == 0:
        return None

    if bbox is None:
        bbox = extract_bbox(valid_layers)
        if bbox == (0, 0, 0, 0):
            return None

    result = Image.new(
        extract_pil_mode(valid_layers[0]._psd),
        (bbox[2] - bbox[0], bbox[3] - bbox[1]),
        color=color,
    )

    initial_layer = True
    for layer in valid_layers:
        if intersect(layer.bbox, bbox) == (0, 0, 0, 0):
            continue

        image = layer.compose()
        if image is None:
            continue

        logger.debug('Composing %s' % layer)
        offset = (layer.left - bbox[0], layer.top - bbox[1])
        if initial_layer:
            result.paste(image, offset)
            initial_layer = False
        else:
            result = _blend(result, image, offset)

    return result


def compose_layer(layer):
    """Compose a single layer with pixels."""
    from PIL import Image

    bbox = layer.bbox
    if bbox == (0, 0, 0, 0) or not layer.has_pixels():
        return None

    image = layer.topil()

    # Apply mask.
    if layer.has_mask() and not layer.mask.disabled:
        mask_bbox = layer.mask.bbox
        if mask_bbox != (0, 0, 0, 0):
            color = layer.mask.background_color
            offset = (mask_bbox[0] - layer.left, mask_bbox[1] - layer.top)
            mask = Image.new('L', image.size, color=color)
            mask.paste(layer.mask.topil(), offset)
            if image.mode.endswith('A'):
                # What should we do here? There are two alpha channels.
                pass
            image.putalpha(mask)

    # Clip layers.
    # if layer.has_clip_layers():
    #     clip_box = extract_bbox(layer.clip_layers)
    #     if clip_box != (0, 0, 0, 0):
    #         clip_image = compose(layer.clip_layers, bbox=clip_box)


    # Apply opacity.
    if layer.opacity < 255:
        opacity = int(
            layer.tagged_blocks.get_data('BLEND_FILL_OPACITY', 1) *
            layer.opacity
        )
        if image.mode.endswith('A'):
            opacity = opacity / 255.
            channels = list(image.split())
            channels[-1] = channels[-1].point(lambda x: int(x * opacity))
            image = Image.merge(image.mode, channels)
        else:
            image.putalpha(opacity)

    return image
