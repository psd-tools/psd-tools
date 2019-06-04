"""
Composer API.

Composer takes responsibility of rendering layers as an image.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools.constants import Tag
from psd_tools.api.pil_io import get_pil_mode
from psd_tools.api.layers import Group
from psd_tools.composer.blend import blend
from psd_tools.composer.vector import (
    draw_pattern_fill, draw_gradient_fill, draw_solid_color_fill,
    draw_vector_mask
)

logger = logging.getLogger(__name__)


def intersect(*bboxes):
    if len(bboxes) == 0:
        return (0, 0, 0, 0)

    lefts, tops, rights, bottoms = zip(*bboxes)
    result = (max(lefts), max(tops), min(rights), min(bottoms))
    if result[2] <= result[0] or result[3] <= result[1]:
        return (0, 0, 0, 0)

    return result


def compose(layers, bbox=None, layer_filter=None, color=None, **kwargs):
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
        return None

    if bbox is None:
        bbox = Group.extract_bbox(valid_layers)
        if bbox == (0, 0, 0, 0):
            return None

    # Alpha must be forced to correctly blend.
    mode = get_pil_mode(valid_layers[0]._psd.color_mode, True)
    result = Image.new(
        mode,
        (bbox[2] - bbox[0], bbox[3] - bbox[1]),
        color=color if color is not None else 'white',
    )
    result.putalpha(0)

    for layer in valid_layers:
        if intersect(layer.bbox, bbox) == (0, 0, 0, 0):
            continue

        if layer.is_group():
            image = layer.compose(**kwargs)
        else:
            image = compose_layer(layer, **kwargs)
        if image is None:
            continue

        logger.debug('Composing %s' % layer)
        offset = (layer.left - bbox[0], layer.top - bbox[1])
        result = blend(result, image, offset)

    return result


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

    # Apply mask.
    if layer.has_mask() and not layer.mask.disabled:
        mask_bbox = layer.mask.bbox
        if ((mask_bbox[2] - mask_bbox[0]) > 0 and
            (mask_bbox[3] - mask_bbox[1]) > 0):
            color = layer.mask.background_color
            offset = (mask_bbox[0] - layer.left, mask_bbox[1] - layer.top)
            mask = Image.new('L', image.size, color=color)
            mask.paste(layer.mask.topil(), offset)
            if image.mode.endswith('A'):
                # What should we do here? There are two alpha channels.
                pass
            image.putalpha(mask)
    elif layer.has_vector_mask() and (force or not layer.has_pixels()):
        mask = draw_vector_mask(layer)
        # TODO: Stroke drawing.
        texture = image
        image = Image.new(image.mode, image.size, 'white')
        image.paste(texture, mask=mask)

    # Apply layer fill effects.
    apply_effect(layer, image)

    # Clip layers.
    if layer.has_clip_layers():
        clip_box = Group.extract_bbox(layer.clip_layers)
        inter_box = intersect(layer.bbox, clip_box)
        if inter_box != (0, 0, 0, 0):
            clip_image = compose(layer.clip_layers, bbox=layer.bbox)
            mask = image.getchannel('A')
            if clip_image.mode.endswith('A'):
                mask = ImageChops.multiply(clip_image.getchannel('A'), mask)
            clip_image.putalpha(mask)
            image = blend(image, clip_image, (0, 0))

    # Apply opacity.
    if layer.opacity < 255:
        opacity = layer.opacity
        if image.mode.endswith('A'):
            opacity = opacity / 255.
            channels = list(image.split())
            channels[-1] = channels[-1].point(lambda x: int(x * opacity))
            image = Image.merge(image.mode, channels)
        else:
            image.putalpha(opacity)

    return image


def create_fill(layer):
    from PIL import Image
    mode = get_pil_mode(layer._psd.color_mode, True)
    image = None
    if Tag.VECTOR_STROKE_CONTENT_DATA in layer.tagged_blocks:
        image = Image.new(mode, (layer.width, layer.height), 'white')
        setting = layer.tagged_blocks.get_data(Tag.VECTOR_STROKE_CONTENT_DATA)
        if b'Ptrn' in setting:
            draw_pattern_fill(image, layer._psd, setting, blend=False)
        elif b'Grad' in setting:
            draw_gradient_fill(image, setting, blend=False)
        else:
            draw_solid_color_fill(image, setting, blend=False)
    elif Tag.SOLID_COLOR_SHEET_SETTING in layer.tagged_blocks:
        image = Image.new(mode, (layer.width, layer.height), 'white')
        setting = layer.tagged_blocks.get_data(Tag.SOLID_COLOR_SHEET_SETTING)
        draw_solid_color_fill(image, setting, blend=False)
    elif Tag.PATTERN_FILL_SETTING in layer.tagged_blocks:
        image = Image.new(mode, (layer.width, layer.height), 'white')
        setting = layer.tagged_blocks.get_data(Tag.PATTERN_FILL_SETTING)
        draw_pattern_fill(image, layer._psd, setting, blend=False)
    elif Tag.GRADIENT_FILL_SETTING in layer.tagged_blocks:
        image = Image.new(mode, (layer.width, layer.height), 'white')
        setting = layer.tagged_blocks.get_data(Tag.GRADIENT_FILL_SETTING)
        draw_gradient_fill(image, setting, blend=False)
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
            draw_pattern_fill(image, layer._psd, effect.value)

    for effect in layer.effects:
        if effect.__class__.__name__ == 'GradientOverlay':
            draw_gradient_fill(image, effect.value)

    for effect in layer.effects:
        if effect.__class__.__name__ == 'ColorOverlay':
            draw_solid_color_fill(image, effect.value)
