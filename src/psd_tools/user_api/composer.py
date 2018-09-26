# -*- coding: utf-8 -*-
"""
PSD layer composer.
"""
from __future__ import absolute_import, unicode_literals
import logging
from psd_tools.user_api import BBox
from psd_tools.user_api import pil_support
from psd_tools.constants import TaggedBlock, ColorMode
import psd_tools.user_api.layers
from PIL import Image

logger = logging.getLogger(__name__)


# Color mode mappings.
COLOR_MODES = {
    ColorMode.BITMAP: '1',
    ColorMode.GRAYSCALE: 'LA',
    ColorMode.INDEXED: 'P',         # Not supported.
    ColorMode.RGB: 'RGBA',
    ColorMode.CMYK: 'RGBA',         # Force RGB.
    ColorMode.MULTICHANNEL: 'RGB',  # Not supported.
    ColorMode.DUOTONE: 'RGB',       # Not supported.
    ColorMode.LAB: 'LAB',
}


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


def _get_default_color(mode):
    color = 0
    if mode in ('RGBA', 'LA'):
        color = tuple([255] * (len(mode) - 1) + [0])
    elif mode in ('RGB', 'L'):
        color = tuple([255] * len(mode))
    return color


def _apply_opacity(layer_image, layer):
    layer_opacity = layer.opacity
    if layer.has_tag(TaggedBlock.BLEND_FILL_OPACITY):
        layer_opacity *= layer.get_tag(TaggedBlock.BLEND_FILL_OPACITY)
    if layer_opacity == 255:
        return layer_image
    return pil_support.apply_opacity(layer_image, layer_opacity)


# TODO: Implement and refactor layer effects.
def _apply_coloroverlay(layer, layer_image):
    """
    Apply color overlay effect.
    """
    for effect in layer.effects.find('coloroverlay'):
        opacity = effect.opacity.value * 255.0 / 100
        color = tuple(int(x) for x in effect.color.value + (opacity,))
        tmp = Image.new("RGBA", layer_image.size, color=color)

        # Overlay only applies strokes when fill is disabled.
        fill_only = (
            layer.kind == 'shape' and layer.has_stroke() and
            layer.stroke.get(b'fillEnabled', True)
        )
        if not fill_only:
            tmp.putalpha(layer_image.split()[-1])

        layer_image = Image.alpha_composite(layer_image, tmp)
    return layer_image


def _blend(target, image, offset, mask):
    if image.mode == 'RGBA':
        tmp = Image.new(image.mode, target.size,
                        _get_default_color(image.mode))
        tmp.paste(image, offset, mask=mask)
        target = Image.alpha_composite(target, tmp)
    elif target.mode == 'LA':
        tmp = Image.new('RGBA', target.size, _get_default_color('RGBA'))
        tmp.paste(image.convert('RGBA'), offset, mask=mask)
        target = Image.alpha_composite(target.convert('RGBA'), tmp)
        target = target.convert('LA')
    else:
        target.paste(image, offset, mask=mask)

    return target


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

    This is experimental and requires PIL.

    :param layers: a layer, or an iterable of layers
    :param respect_visibility: Take visibility flag into account
    :param ignore_blend_mode: Ignore blending mode
    :param skip_layer: skip composing the given layer if returns True
    :rtype: `PIL.Image`
    """

    if isinstance(layers, psd_tools.user_api.layers._RawLayer):
        layers = [layers]

    if bbox is None:
        bbox = combined_bbox(layers)

    if bbox.is_empty():
        return None

    mode = 'RGBA'
    if len(layers):
        mode = COLOR_MODES.get(layers[0]._psd.header.color_mode, 'RGBA')
    result = Image.new(mode, (bbox.width, bbox.height),
                       color=_get_default_color(mode))

    for layer in reversed(layers):
        if skip_layer(layer) or (
                not layer.is_visible() and respect_visibility):
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

        if not ignore_blend_mode and layer.blend_mode != 'normal':
            logger.warning('Blend mode is not implemented: %s',
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

        layer_image = _apply_opacity(layer_image, layer)
        layer_image = _apply_coloroverlay(layer, layer_image)

        layer_offset = layer.bbox.offset((bbox.x1, bbox.y1))
        mask = None
        if layer.has_mask():
            mask_box = layer.mask.bbox
            if not layer.mask.disabled and not mask_box.is_empty():
                mask_color = layer.mask.background_color
                mask = Image.new('L', layer_image.size, color=(mask_color,))
                mask.paste(
                    layer.mask.as_PIL(),
                    mask_box.offset((layer.bbox.x1, layer.bbox.y1))
                )

        result = _blend(result, layer_image, layer_offset, mask)

        if clip_image is not None:
            offset = (intersect.x1 - bbox.x1, intersect.y1 - bbox.y1)
            result = _blend(result, clip_image, offset, clip_mask)

    return result
