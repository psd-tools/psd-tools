"""
Composer module.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools.api.pil_io import get_pil_mode, convert_pattern_to_pil

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


def _blend(target, image, offset):
    if offset[0] < 0:
        if image.width <= -offset[0]:
            return target
        image = image.crop((-offset[0], 0, image.width, image.height))
        offset = (0, offset[1])

    if offset[1] < 0:
        if image.height <= -offset[1]:
            return target
        image = image.crop((0, -offset[1], image.width, image.height))
        offset = (offset[0], 0)

    if target.mode == 'RGBA':
        target.alpha_composite(image.convert('RGBA'), offset)
    else:
        tmp = target.convert('RGBA')
        tmp.alpha_composite(image.convert('RGBA'), offset)
        target = tmp.convert(target.mode)
    return target


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
        bbox = extract_bbox(valid_layers)
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

        image = compose_layer(layer, **kwargs)
        if image is None:
            continue

        logger.debug('Composing %s' % layer)
        offset = (layer.left - bbox[0], layer.top - bbox[1])
        result = _blend(result, image, offset)

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
        clip_box = extract_bbox(layer.clip_layers)
        inter_box = intersect(layer.bbox, clip_box)
        if inter_box != (0, 0, 0, 0):
            clip_image = compose(layer.clip_layers, bbox=layer.bbox)
            mask = image.getchannel('A')
            if clip_image.mode.endswith('A'):
                mask = ImageChops.multiply(clip_image.getchannel('A'), mask)
            clip_image.putalpha(mask)
            image = _blend(image, clip_image, (0, 0))

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
    if 'SOLID_COLOR_SHEET_SETTING' in layer.tagged_blocks:
        image = Image.new(mode, (layer.width, layer.height), 'white')
        setting = layer.tagged_blocks.get_data('SOLID_COLOR_SHEET_SETTING')
        draw_solid_color_fill(image, setting, blend=False)
    elif 'VECTOR_STROKE_CONTENT_DATA' in layer.tagged_blocks:
        image = Image.new(mode, (layer.width, layer.height), 'white')
        setting = layer.tagged_blocks.get_data('VECTOR_STROKE_CONTENT_DATA')
        draw_solid_color_fill(image, setting, blend=False)
    elif 'PATTERN_FILL_SETTING' in layer.tagged_blocks:
        image = Image.new(mode, (layer.width, layer.height), 'white')
        setting = layer.tagged_blocks.get_data('PATTERN_FILL_SETTING')
        draw_pattern_fill(image, layer._psd, setting, blend=False)
    elif 'GRADIENT_FILL_SETTING' in layer.tagged_blocks:
        image = Image.new(mode, (layer.width, layer.height), 'white')
        setting = layer.tagged_blocks.get_data('GRADIENT_FILL_SETTING')
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


def draw_vector_mask(layer):
    from PIL import Image, ImageChops
    width = layer._psd.width
    height = layer._psd.height
    color = 255 * layer.vector_mask.initial_fill_rule

    mask = Image.new('L', (width, height), color)
    first = True
    for subpath in layer.vector_mask.paths:
        plane = _draw_subpath(subpath, width, height)
        if subpath.operation == 0:
            mask = ImageChops.difference(mask, plane)
        elif subpath.operation == 1:
            mask = ImageChops.lighter(mask, plane)
        elif subpath.operation == 2:
            if first:
                mask = ImageChops.invert(mask)
            mask = ImageChops.subtract(mask, plane)
        elif subpath.operation == 3:
            if first:
                mask = ImageChops.invert(mask)
            mask = ImageChops.darker(mask, plane)
        first = False
    return mask.crop(layer.bbox)


def _draw_subpath(subpath, width, height):
    from PIL import Image
    import aggdraw
    mask = Image.new('L', (width, height), 0)
    path = ' '.join(map(str, _generate_symbol(subpath, width, height)))
    draw = aggdraw.Draw(mask)
    brush = aggdraw.Brush(255)
    symbol = aggdraw.Symbol(path)
    draw.symbol((0, 0), symbol, None, brush)
    draw.flush()
    del draw
    return mask


def _generate_symbol(path, width, height, command='C'):
    """Sequence generator for SVG path."""
    if len(path) == 0:
        return

    # Initial point.
    yield 'M'
    yield path[0].anchor[1] * width
    yield path[0].anchor[0] * height
    yield command

    # Closed path or open path
    points = (
        zip(path, path[1:] +
            path[0:1]) if path.is_closed() else zip(path, path[1:])
    )

    # Rest of the points.
    for p1, p2 in points:
        yield p1.leaving[1] * width
        yield p1.leaving[0] * height
        yield p2.preceding[1] * width
        yield p2.preceding[0] * height
        yield p2.anchor[1] * width
        yield p2.anchor[0] * height

    if path.is_closed():
        yield 'Z'


def draw_solid_color_fill(image, setting, blend=True):
    from PIL import Image, ImageDraw, ImageChops
    color = tuple(int(x) for x in setting.get(b'Clr ').values())
    canvas = Image.new(image.mode, image.size)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, canvas.width, canvas.height), fill=color)
    del draw
    if blend:
        canvas.putalpha(image.getchannel('A'))
        _blend(image, canvas, (0, 0))
    else:
        image.paste(canvas)


def draw_pattern_fill(image, psd, setting, blend=True):
    """
    Draw pattern fill on the image.

    :param image: Image to be filled.
    :param psd: :py:class:`PSDImage`.
    :param setting: Descriptor containing pattern fill.
    :param blend: Blend the fill or ignore. Effects blend.
    """
    from PIL import Image
    pattern_id = setting[b'Ptrn'][b'Idnt'].value.rstrip('\x00')
    pattern = psd._get_pattern(pattern_id)
    if not pattern:
        logger.error('Pattern not found: %s' % (pattern_id))
        return None
    panel = convert_pattern_to_pil(pattern, psd._record.header.version)

    scale = setting.get(b'Scl ', 100) / 100.
    if scale != 1.:
        panel = panel.resize(
            (int(panel.width * scale), int(panel.height * scale))
        )

    opacity = int(setting.get(b'Opct', 100) / 100. * 255)
    if opacity != 255:
        panel.putalpha(opacity)

    pattern_image = Image.new(image.mode, image.size)
    mask = image.getchannel('A') if blend else Image.new('L', image.size, 255)

    for left in range(0, pattern_image.width, panel.width):
        for top in range(0, pattern_image.height, panel.height):
            panel_mask = mask.crop(
                (left, top, left + panel.width, top + panel.height)
            )
            pattern_image.paste(panel, (left, top), panel_mask)

    if blend:
        image.paste(_blend(image, pattern_image, (0, 0)))
    else:
        image.paste(pattern_image)


def draw_gradient_fill(image, setting, blend=True):
    try:
        import numpy as np
        from scipy import interpolate
    except ImportError:
        logger.error('Gradient fill requires numpy and scipy.')
        return None

    angle = float(setting.get(b'Angl'))
    gradient_kind = setting.get(b'Type').get_name()
    if gradient_kind == 'Linear':
        Z = _make_linear_gradient(image.width, image.height, -angle)
    else:
        logger.warning('Only linear gradient is supported.')
        Z = np.ones((image.height, image.width)) * 0.5

    gradient_image = _apply_color_map(image.mode, setting.get(b'Grad'), Z)
    if blend:
        gradient_image.putalpha(image.getchannel('A'))
        _blend(image, gradient_image, offset=(0, 0))
    else:
        image.paste(gradient_image)


def _make_linear_gradient(width, height, angle=90.):
    """Generates index map for linear gradients."""
    import numpy as np
    X, Y = np.meshgrid(np.linspace(0, 1, width), np.linspace(0, 1, height))
    theta = np.radians(angle % 360)
    c, s = np.cos(theta), np.sin(theta)
    if 0 <= theta and theta < 0.5 * np.pi:
        Z = np.abs(c * X + s * Y)
    elif 0.5 * np.pi <= theta and theta < np.pi:
        Z = np.abs(c * (X - width) + s * Y)
    elif np.pi <= theta and theta < 1.5 * np.pi:
        Z = np.abs(c * (X - width) + s * (Y - height))
    elif 1.5 * np.pi <= theta and theta < 2.0 * np.pi:
        Z = np.abs(c * X + s * (Y - height))
    return (Z - Z.min()) / (Z.max() - Z.min())


def _apply_color_map(mode, grad, Z):
    """"""
    import numpy as np
    from scipy import interpolate
    from PIL import Image

    stops = grad.get(b'Clrs')
    scalar = {
        'RGB': 1.0,
        'L': 2.55,
        'CMYK': 2.55,
    }.get(mode, 1.0)

    X = [stop.get(b'Lctn').value / 4096. for stop in stops]
    Y = [
        tuple(int(scalar * x.value) for x in stop.get(b'Clr ').values())
        for stop in stops
    ]
    if len(stops) == 1:
        X = [0., 1.]
        Y = [Y[0], Y[0]]
    G = interpolate.interp1d(X, Y, axis=0, fill_value='extrapolate')
    pixels = G(Z).astype(np.uint8)
    if pixels.shape[-1] == 1:
        pixels = pixels[:, :, 0]

    image = Image.fromarray(pixels, mode.rstrip('A'))
    if b'Trns' in grad and mode.endswith('A'):
        stops = grad.get(b'Trns')
        X = [stop.get(b'Lctn').value / 4096 for stop in stops]
        Y = [stop.get(b'Opct').value * 2.55 for stop in stops]
        if len(stops) == 1:
            X = [0., 1.]
            Y = [Y[0], Y[0]]
        G_opacity = interpolate.interp1d(
            X, Y, axis=0, fill_value='extrapolate'
        )
        alpha = G_opacity(Z).astype(np.uint8)
        image.putalpha(Image.fromarray(alpha, 'L'))

    return image
