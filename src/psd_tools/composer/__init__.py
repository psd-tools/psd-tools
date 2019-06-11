"""
Composer API.

Composer takes responsibility of rendering layers as an image.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools.constants import Tag, BlendMode
from psd_tools.api.pil_io import get_pil_mode
from psd_tools.api.layers import Group
from psd_tools.composer.blend import blend
from psd_tools.composer.vector import (
    draw_pattern_fill, draw_gradient_fill, draw_solid_color_fill,
    draw_vector_mask
)

logger = logging.getLogger(__name__)


def union(*bboxes):
    if len(bboxes) == 0:
        return (0, 0, 0, 0)

    lefts, tops, rights, bottoms = zip(*bboxes)
    result = (min(lefts), min(tops), max(rights), max(bottoms))
    if result[2] <= result[0] or result[3] <= result[1]:
        return (0, 0, 0, 0)

    return result


def intersect(*bboxes):
    if len(bboxes) == 0:
        return (0, 0, 0, 0)

    lefts, tops, rights, bottoms = zip(*bboxes)
    result = (max(lefts), max(tops), min(rights), min(bottoms))
    if result[2] <= result[0] or result[3] <= result[1]:
        return (0, 0, 0, 0)

    return result


def compose(
    layers, bbox=None, context=None, layer_filter=None, color=None, **kwargs
):
    """
    Compose layers to a single :py:class:`PIL.Image`.
    If the layers do not have visible pixels, the function returns `None`.

    Example::

        image = compose([layer1, layer2])

    In order to skip some layers, pass `layer_filter` function which
    should take `layer` as an argument and return `True` to keep the layer
    or return `False` to skip::

        image = compose(
            layers,
            layer_filter=lambda x: x.is_visible() and x.kind == 'type'
        )

    By default, visible layers are composed.

    .. note:: This function is experimental and does not guarantee
        Photoshop-quality rendering.

        Currently the following are ignored:

         - Adjustments layers
         - Layer effects
         - Blending mode (all blending modes become normal)

        Shape drawing is inaccurate if the PSD file is not saved with
        maximum compatibility.

    :param layers: a layer, or an iterable of layers.
    :param bbox: (left, top, bottom, right) tuple that specifies a region to
        compose. By default, all the visible area is composed. The origin
        is at the top-left corner of the PSD document.
    :param context: `PIL.Image` object for the backdrop rendering context. Must
        be used with the correct `bbox` size.
    :param layer_filter: a callable that takes a layer and returns `bool`.
    :param color: background color in `int` or `tuple`.
    :return: :py:class:`PIL.Image` or `None`.
    """
    from PIL import Image

    if not hasattr(layers, '__iter__'):
        layers = [layers]

    def _default_filter(layer):
        return layer.is_visible()

    layer_filter = layer_filter or _default_filter
    valid_layers = [x for x in layers if layer_filter(x)]
    if len(valid_layers) == 0:
        return context

    if bbox is None:
        bbox = Group.extract_bbox(valid_layers)
        if bbox == (0, 0, 0, 0):
            return context

    if context is None:
        mode = get_pil_mode(valid_layers[0]._psd.color_mode, True)
        context = Image.new(
            mode,
            (bbox[2] - bbox[0], bbox[3] - bbox[1]),
            color=color if color is not None else 'white',
        )
        context.putalpha(0)  # Alpha must be forced to correctly blend.
        context.info['offset'] = (bbox[0], bbox[1])

    for layer in valid_layers:
        if intersect(layer.bbox, bbox) == (0, 0, 0, 0):
            continue

        if layer.is_group():
            if layer.blend_mode == BlendMode.PASS_THROUGH:
                image = layer.compose(context=context, bbox=bbox)
            else:
                image = layer.compose(**kwargs)
        else:
            image = compose_layer(layer, **kwargs)
        if image is None:
            continue

        logger.debug('Composing %s' % layer)
        offset = image.info.get('offset', layer.offset)
        offset = (offset[0] - bbox[0], offset[1] - bbox[1])
        context = blend(context, image, offset, layer.blend_mode)

    return context


def compose_layer(layer, force=False, **kwargs):
    """Compose a single layer with pixels."""
    from PIL import Image, ImageChops
    assert layer.bbox != (0, 0, 0, 0), 'Layer bbox is (0, 0, 0, 0)'

    image = layer.topil(**kwargs)
    if image is None or force:
        texture = create_fill(layer)
        if texture is not None:
            image = texture

    if image is None:
        return image

    # TODO: Group should have the following too.

    # Apply vector mask.
    if layer.has_vector_mask() and (force or not layer.has_pixels()):
        vector_mask = draw_vector_mask(layer)
        # TODO: Stroke drawing.
        if image.mode.endswith('A'):
            vector_mask = ImageChops.darker(image.getchannel('A'), vector_mask)
        image.putalpha(vector_mask)

    # Apply mask.
    image = apply_mask(layer, image)

    # Apply layer fill effects.
    apply_effect(layer, image)

    # Clip layers.
    if layer.has_clip_layers():
        clip_box = Group.extract_bbox(layer.clip_layers)
        inter_box = intersect(layer.bbox, clip_box)
        if inter_box != (0, 0, 0, 0):
            offset = image.info.get('offset', layer.offset)
            bbox = offset + (offset[0] + image.width, offset[1] + image.height)
            clip_image = compose(layer.clip_layers, bbox=bbox)
            mask = image.getchannel('A')
            if clip_image.mode.endswith('A'):
                mask = ImageChops.multiply(clip_image.getchannel('A'), mask)
            clip_image.putalpha(mask)
            image = blend(image, clip_image, (0, 0))

    # Apply opacity.
    apply_opacity(layer, image)

    return image


def create_fill(layer):
    from PIL import Image
    mode = get_pil_mode(layer._psd.color_mode, True)
    image = None
    if Tag.VECTOR_STROKE_CONTENT_DATA in layer.tagged_blocks:
        image = Image.new(mode, (layer.width, layer.height), 'white')
        setting = layer.tagged_blocks.get_data(Tag.VECTOR_STROKE_CONTENT_DATA)
        if b'Ptrn' in setting:
            draw_pattern_fill(image, layer._psd, setting)
        elif b'Grad' in setting:
            draw_gradient_fill(image, setting)
        else:
            draw_solid_color_fill(image, setting)
    elif Tag.SOLID_COLOR_SHEET_SETTING in layer.tagged_blocks:
        image = Image.new(mode, (layer.width, layer.height), 'white')
        setting = layer.tagged_blocks.get_data(Tag.SOLID_COLOR_SHEET_SETTING)
        draw_solid_color_fill(image, setting)
    elif Tag.PATTERN_FILL_SETTING in layer.tagged_blocks:
        image = Image.new(mode, (layer.width, layer.height), 'white')
        setting = layer.tagged_blocks.get_data(Tag.PATTERN_FILL_SETTING)
        draw_pattern_fill(image, layer._psd, setting)
    elif Tag.GRADIENT_FILL_SETTING in layer.tagged_blocks:
        image = Image.new(mode, (layer.width, layer.height), 'white')
        setting = layer.tagged_blocks.get_data(Tag.GRADIENT_FILL_SETTING)
        draw_gradient_fill(image, setting)
    return image


def apply_mask(layer, image):
    """
    Apply raster mask to the image.

    This might change the size and offset of the image. Resulting offset wrt
    the psd viewport is kept in `image.info['offset']` field.

    :param layer: `~psd_tools.api.layers.Layer`
    :param image: PIL.Image
    :return: PIL.Image
    """
    from PIL import Image, ImageChops

    image.info['offset'] = layer.offset  # Later needed for composition.
    if layer.has_mask() and not layer.mask.disabled:
        mask_bbox = layer.mask.bbox
        if mask_bbox != (0, 0, 0, 0):
            color = layer.mask.background_color
            if color == 0:
                bbox = mask_bbox
            else:
                bbox = layer._psd.viewbox
            size = (bbox[2] - bbox[0], bbox[3] - bbox[1])
            image_ = Image.new(image.mode, size)
            image_.paste(image, (layer.left - bbox[0], layer.top - bbox[1]))
            mask = Image.new('L', size, color=color)
            mask_image = layer.mask.topil()
            if mask_image:
                mask.paste(
                    mask_image,
                    (mask_bbox[0] - bbox[0], mask_bbox[1] - bbox[1])
                )
            if image_.mode.endswith('A'):
                mask = ImageChops.darker(image_.getchannel('A'), mask)
            image_.putalpha(mask)
            image_.info['offset'] = (bbox[0], bbox[1])
            return image_
    return image


def apply_effect(layer, image):
    """Apply effect to the image.

    ..note: Correct effect order is the following. All the effects are first
        applied to the original image then blended together.

        * dropshadow
        * outerglow
        * (original)
        * patternoverlay
        * gradientoverlay
        * coloroverlay
        * innershadow
        * innerglow
        * bevelemboss
        * satin
        * stroke
    """
    for effect in layer.effects:
        if effect.__class__.__name__ == 'PatternOverlay':
            draw_pattern_fill(
                image, layer._psd, effect.value, effect.blend_mode
            )

    for effect in layer.effects:
        if effect.__class__.__name__ == 'GradientOverlay':
            draw_gradient_fill(image, effect.value, effect.blend_mode)

    for effect in layer.effects:
        if effect.__class__.__name__ == 'ColorOverlay':
            draw_solid_color_fill(image, effect.value, effect.blend_mode)


def apply_opacity(layer, image):
    fill_opacity = layer.tagged_blocks.get_data(Tag.BLEND_FILL_OPACITY, 255)
    if layer.opacity < 255 or fill_opacity < 255:
        opacity = (layer.opacity / 255.) * (fill_opacity / 255.)
        if image.mode.endswith('A'):
            alpha = image.getchannel('A')
            alpha = alpha.point(lambda x: int(round(x * opacity)))
            image.putalpha(alpha)
        else:
            image.putalpha(int(255 * opacity))
