# -*- coding: utf-8 -*-
"""
PSD layer composer.
"""
from __future__ import absolute_import, unicode_literals
import logging
from psd_tools.user_api import BBox
from psd_tools.user_api import pil_support
import psd_tools.user_api.layers
from PIL import Image

logger = logging.getLogger(__name__)


def combined_bbox(layers):
    """
    Returns a bounding box for ``layers`` or BBox(0, 0, 0, 0) if the layers
    have no bbox.
    """
    bboxes = [layer.bbox for layer in layers if not layer.bbox.is_empty()]
    if len(bboxes) == 0:
        return BBox(0, 0, 0, 0)
    lefts, tops, rights, bottoms = zip(*bboxes)
    return BBox(min(lefts), min(tops), max(rights), max(bottoms))


# TODO: Implement and refactor layer effects.
def _apply_coloroverlay(layer, layer_image):
    """
    Apply color overlay effect.
    """
    for effect in layer.effects.find('coloroverlay'):
        opacity = effect.opacity.value * 255.0 / 100
        color = tuple(int(x) for x in effect.color.value + (opacity,))
        tmp = Image.new("RGBA", layer_image.size, color=color)
        layer_image = Image.alpha_composite(layer_image, tmp)
    return layer_image



def compose(layers, respect_visibility=True, ignore_blend_mode=True,
            skip_layer=lambda layer: False, bbox=None):
    """
    Compose layers to a single ``PIL.Image`` (the first layer is on top).

    By default hidden layers are not rendered;
    pass ``respect_visibility=False`` to render them.

    In order to skip some layers pass ``skip_layer`` function which
    should take ``layer`` as an argument and return True or False.

    If ``bbox`` is not None, it should be a 4-tuple with coordinates;
    returned image will be restricted to this rectangle.

    Adjustment and layer effects are ignored.

    This is experimental.

    :param layers: a layer, or an iterable of layers
    :param respect_visibility: Take visibility flag into account
    :param ignore_blend_mode: Ignore blending mode
    :param skip_layer: skip composing the given layer if returns True
    :rtype: `PIL.Image`
    """

    # FIXME: this currently assumes PIL
    if isinstance(layers, psd_tools.user_api.layers._RawLayer):
        layers = [layers]

    if bbox is None:
        bbox = combined_bbox(layers)

    if bbox.is_empty():
        return None

    result = Image.new(
        "RGBA",
        (bbox.width, bbox.height),
        color=(255, 255, 255, 0)  # fixme: transparency is incorrect
    )

    for layer in reversed(layers):
        if skip_layer(layer) or not layer.has_box() or (
                not layer.visible and respect_visibility):
            continue

        if layer.is_group():
            layer_image = layer.as_PIL(
                respect_visibility=respect_visibility,
                ignore_blend_mode=ignore_blend_mode,
                skip_layer=skip_layer)
        else:
            layer_image = layer.as_PIL()

        if not layer_image:
            continue

        if not ignore_blend_mode and layer.blend_mode != "normal":
            logger.warning("Blend mode is not implemented: %s",
                           layer.blend_mode)
            continue

        clip_image = None
        if len(layer.clip_layers):
            clip_box = combined_bbox(layer.clip_layers)
            if not clip_box.is_empty():
                intersect = clip_box.intersect(layer.bbox)
                if not intersect.is_empty():
                    clip_image = compose(
                        layer.clip_layers, respect_visibility,
                        ignore_blend_mode, skip_layer)
                    clip_image = clip_image.crop(
                        intersect.offset((clip_box.x1, clip_box.y1)))
                    clip_mask = layer_image.crop(
                        intersect.offset((layer.bbox.x1, layer.bbox.y1)))

        layer_image = pil_support.apply_opacity(layer_image, layer.opacity)
        layer_image = _apply_coloroverlay(layer, layer_image)

        layer_offset = layer.bbox.offset((bbox.x1, bbox.y1))
        mask = None
        if layer.has_mask():
            mask_box = layer.mask.bbox
            if not layer.mask.disabled and not mask_box.is_empty():
                mask_color = layer.mask.background_color
                mask = Image.new("L", layer_image.size, color=(mask_color,))
                mask.paste(
                    layer.mask.as_PIL(),
                    mask_box.offset((layer.bbox.x1, layer.bbox.y1))
                )

        if layer_image.mode == 'RGBA':
            tmp = Image.new("RGBA", result.size, color=(255, 255, 255, 0))
            tmp.paste(layer_image, layer_offset, mask=mask)
            result = Image.alpha_composite(result, tmp)
        elif layer_image.mode == 'RGB':
            result.paste(layer_image, layer_offset, mask=mask)
        else:
            logger.warning(
                "layer image mode is unsupported for merging: %s",
                layer_image.mode)
            continue

        if clip_image is not None:
            offset = (intersect.x1 - bbox.x1, intersect.y1 - bbox.y1)
            if clip_image.mode == 'RGBA':
                tmp = Image.new("RGBA", result.size, color=(255, 255, 255, 0))
                tmp.paste(clip_image, offset, mask=clip_mask)
                result = Image.alpha_composite(result, tmp)
            elif clip_image.mode == 'RGB':
                result.paste(clip_image, offset, mask=clip_mask)

    return result
