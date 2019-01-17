"""
Composer module.
"""
from __future__ import absolute_import, unicode_literals
import logging

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


def intersect(bboxes):
    if len(intersect) == 0:
        return (0, 0, 0, 0)

    lefts, tops, rights, bottoms = zip(*bboxes)
    result = (max(lefts), max(tops), min(rights), min(bottoms))
    if result[2] <= result[0] or result[3] <= result[1]:
        return (0, 0, 0, 0)

    return result


def compose(layers, skip_layer=None):
    """
    Compose layers to a single ``PIL.Image``.

    In order to skip some layers pass ``skip_layer`` function which
    should take ``layer`` as an argument and return True or False.

    Adjustment and layer effects are ignored.

    This is experimental and requires PIL.

    :param layers: a layer, or an iterable of layers
    :param skip_layer: skip composing the given layer if returns True
    :return: PIL Image or None
    """
    raise NotImplementedError

    if not hasattr(layers, '__iter__'):
        layers = [layers]

    bbox = extract_bbox(layers)
    if bbox == (0, 0, 0, 0):
        return None



def compose_layer(layer):
    """Compose a single layer with pixels."""
    from PIL import Image

    bbox = layer.bbox
    if bbox == (0, 0, 0, 0) or not layer.has_pixels():
        return None

    image = layer.topil()
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

    return image
