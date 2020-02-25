"""
Composer API.

Composer takes responsibility of rendering layers as an image.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools.api import deprecated
from psd_tools.constants import Tag, BlendMode
from psd_tools.api.pil_io import get_pil_mode
from psd_tools.api.layers import Group
from psd_tools.composer.blend import blend
from psd_tools.composer.effects import create_stroke_effect
from psd_tools.composer.vector import (
    draw_pattern_fill, draw_gradient_fill, draw_solid_color_fill,
    draw_vector_mask, draw_stroke
)
from psd_tools.terminology import Enum, Key

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


@deprecated
def compose(
    layers,
    force=False,
    bbox=None,
    layer_filter=None,
    context=None,
    color=None,
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
         - Blending modes: dissolve and darker/lighter color becomes normal

        Shape drawing is inaccurate if the PSD file is not saved with
        maximum compatibility.

        Some of the blending modes do not reproduce photoshop blending.

    :param layers: a layer, or an iterable of layers.
    :param bbox: (left, top, bottom, right) tuple that specifies a region to
        compose. By default, all the visible area is composed. The origin
        is at the top-left corner of the PSD document.
    :param context: `PIL.Image` object for the backdrop rendering context. Must
        be used with the correct `bbox` size.
    :param layer_filter: a callable that takes a layer and returns `bool`.
    :param color: background color in `int` or `tuple`.
    :param kwargs: arguments passed to underling `topil()` call.
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
                _context = layer.compose(
                    force=force,
                    context=context,
                    bbox=bbox,
                    layer_filter=layer_filter,
                    color=color,
                )
                offset = _context.info.get('offset', (0, 0))
                # TODO: group opacity is not properly considered here.
                context.paste(
                    _context, (offset[0] - bbox[0], offset[1] - bbox[1])
                )
                continue
            else:
                image = layer.compose(layer_filter=layer_filter)
        else:
            image = compose_layer(layer, force=force)
        if image is None:
            continue

        logger.debug('Composing %s' % layer)
        offset = image.info.get('offset', layer.offset)
        offset = (offset[0] - bbox[0], offset[1] - bbox[1])

        context = blend(context, image, offset, layer.blend_mode)

    logger.debug('Composing: %s' % layers)
    if isinstance(layers, Group):
        context = _apply_layer_ops(layers, context)

    return context


def compose_layer(layer, force=False):
    """Compose a single layer with pixels."""
    assert layer.bbox != (0, 0, 0, 0), 'Layer bbox is (0, 0, 0, 0)'

    image = layer.topil()
    if image is None or force:
        texture = create_fill(layer)
        if texture is not None:
            image = texture
    if image is None:
        return image

    return _apply_layer_ops(layer, image, force=force)


def _apply_layer_ops(layer, image, force=False, bbox=None):
    """Apply layer masks, effects, and clipping."""
    from PIL import Image, ImageChops
    # Apply vector mask.
    if layer.has_vector_mask() and (force or not layer.has_pixels()):
        offset = image.info.get('offset', layer.offset)
        mask_box = offset + (offset[0] + image.width, offset[1] + image.height)
        vector_mask = draw_vector_mask(layer, mask_box)
        if image.mode.endswith('A'):
            offset = vector_mask.info['offset']
            vector_mask = ImageChops.darker(image.getchannel('A'), vector_mask)
            vector_mask.info['offset'] = offset
        image.putalpha(vector_mask)

        # Apply stroke.
        if layer.has_stroke() and layer.stroke.enabled:
            image = draw_stroke(image, layer, vector_mask)

    # Apply mask.
    image = apply_mask(layer, image, bbox=bbox)

    # Apply layer fill effects.
    apply_opacity(
        image, layer.tagged_blocks.get_data(Tag.BLEND_FILL_OPACITY, 255)
    )
    if layer.effects.enabled:
        image = apply_effect(layer, image, image.copy())

    # Clip layers.
    if layer.has_clip_layers():
        clip_box = Group.extract_bbox(layer.clip_layers)
        offset = image.info.get('offset', layer.offset)
        bbox = offset + (offset[0] + image.width, offset[1] + image.height)
        if intersect(bbox, clip_box) != (0, 0, 0, 0):
            clip_image = compose(
                layer.clip_layers,
                force=force,
                bbox=bbox,
                context=image.copy()
            )
            if image.mode.endswith('A'):
                mask = image.getchannel('A')
            else:
                mask = Image.new('L', image.size, 255)
            if clip_image.mode.endswith('A'):
                mask = ImageChops.darker(clip_image.getchannel('A'), mask)
            clip_image.putalpha(mask)
            image = blend(image, clip_image, (0, 0))

    # Apply opacity.
    apply_opacity(image, layer.opacity)

    return image


def create_fill(layer):
    from PIL import Image
    mode = get_pil_mode(layer._psd.color_mode, True)
    size = (layer.width, layer.height)
    fill_image = None
    stroke = layer.tagged_blocks.get_data(Tag.VECTOR_STROKE_DATA)

    # Apply fill.
    if Tag.VECTOR_STROKE_CONTENT_DATA in layer.tagged_blocks:
        setting = layer.tagged_blocks.get_data(Tag.VECTOR_STROKE_CONTENT_DATA)
        if stroke and bool(stroke.get('fillEnabled', True)) is False:
            fill_image = Image.new(mode, size)
        elif Enum.Pattern in setting:
            fill_image = draw_pattern_fill(size, layer._psd, setting)
        elif Key.Gradient in setting:
            fill_image = draw_gradient_fill(size, setting)
        else:
            fill_image = draw_solid_color_fill(size, setting)
    elif Tag.SOLID_COLOR_SHEET_SETTING in layer.tagged_blocks:
        setting = layer.tagged_blocks.get_data(Tag.SOLID_COLOR_SHEET_SETTING)
        fill_image = draw_solid_color_fill(size, setting)
    elif Tag.PATTERN_FILL_SETTING in layer.tagged_blocks:
        setting = layer.tagged_blocks.get_data(Tag.PATTERN_FILL_SETTING)
        fill_image = draw_pattern_fill(size, layer._psd, setting)
    elif Tag.GRADIENT_FILL_SETTING in layer.tagged_blocks:
        setting = layer.tagged_blocks.get_data(Tag.GRADIENT_FILL_SETTING)
        fill_image = draw_gradient_fill(size, setting)

    return fill_image


def apply_mask(layer, image, bbox=None):
    """
    Apply raster mask to the image.

    This might change the size and offset of the image. Resulting offset wrt
    the psd viewport is kept in `image.info['offset']` field.

    :param layer: `~psd_tools.api.layers.Layer`
    :param image: PIL.Image
    :return: PIL.Image
    """
    from PIL import Image, ImageChops

    offset = image.info.get('offset', layer.offset)
    image.info['offset'] = offset
    if layer.has_mask() and not layer.mask.disabled:
        mask_bbox = layer.mask.bbox
        if mask_bbox != (0, 0, 0, 0):
            color = layer.mask.background_color
            if bbox:
                pass
            elif color == 0:
                bbox = mask_bbox
            else:
                bbox = layer._psd.viewbox
            size = (bbox[2] - bbox[0], bbox[3] - bbox[1])
            image_ = Image.new(image.mode, size)
            image_.paste(image, (offset[0] - bbox[0], offset[1] - bbox[1]))
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


def apply_effect(layer, backdrop, base_image):
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
    from PIL import ImageChops

    for effect in layer.effects:
        if effect.__class__.__name__ == 'PatternOverlay':
            image = draw_pattern_fill(
                base_image.size, layer._psd, effect.value
            )
            if base_image.mode.endswith('A'):
                alpha = base_image.getchannel('A')
                if image.mode.endswith('A'):
                    alpha = ImageChops.darker(alpha, image.getchannel('A'))
                image.putalpha(alpha)
            backdrop = blend(backdrop, image, (0, 0), effect.blend_mode)

    for effect in layer.effects:
        if effect.__class__.__name__ == 'GradientOverlay':
            image = draw_gradient_fill(base_image.size, effect.value)
            if base_image.mode.endswith('A'):
                alpha = base_image.getchannel('A')
                if image.mode.endswith('A'):
                    alpha = ImageChops.darker(alpha, image.getchannel('A'))
                image.putalpha(alpha)
            backdrop = blend(backdrop, image, (0, 0), effect.blend_mode)

    for effect in layer.effects:
        if effect.__class__.__name__ == 'ColorOverlay':
            image = draw_solid_color_fill(base_image.size, effect.value)
            if base_image.mode.endswith('A'):
                alpha = base_image.getchannel('A')
                if image.mode.endswith('A'):
                    alpha = ImageChops.darker(alpha, image.getchannel('A'))
                image.putalpha(alpha)
            backdrop = blend(backdrop, image, (0, 0), effect.blend_mode)

    for effect in layer.effects:
        if effect.__class__.__name__ == 'Stroke':
            from PIL import ImageOps

            if layer.has_vector_mask():
                alpha = draw_vector_mask(layer)
            elif base_image.mode.endswith('A'):
                alpha = base_image.getchannel('A')
            else:
                alpha = base_image.convert('L')
            alpha.info['offset'] = base_image.info['offset']
            flat = alpha.getextrema()[0] < 255

            # Expand the image size
            setting = effect.value
            size = int(setting.get(Key.SizeKey))
            offset = backdrop.info['offset']
            backdrop = ImageOps.expand(backdrop, size)
            backdrop.info['offset'] = tuple(x - size for x in offset)
            offset = alpha.info['offset']
            alpha = ImageOps.expand(alpha, size)
            alpha.info['offset'] = tuple(x - size for x in offset)

            if not layer.has_vector_mask() and setting.get(
                Key.Style
            ).enum == Enum.InsetFrame and flat:
                image = create_stroke_effect(alpha, setting, layer._psd, True)
                backdrop.paste(image)
            else:
                image = create_stroke_effect(alpha, setting, layer._psd)
                backdrop = blend(backdrop, image, (0, 0), effect.blend_mode)

    return backdrop


def apply_opacity(image, opacity):
    if opacity < 255:
        if image.mode.endswith('A'):
            opacity /= 255.
            alpha = image.getchannel('A')
            alpha = alpha.point(lambda x: int(round(x * opacity)))
            image.putalpha(alpha)
        else:
            image.putalpha(int(opacity))
