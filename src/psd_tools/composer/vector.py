"""
Vector module.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools.api.pil_io import convert_pattern_to_pil
from psd_tools.terminology import Enum, Key, Type, Klass

logger = logging.getLogger(__name__)

_COLORSPACE = {
    Klass.CMYKColor: 'CMYK',
    Klass.RGBColor: 'RGB',
    Klass.LabColor: 'LAB',
    Klass.Grayscale: 'L',
}


def draw_vector_mask(layer, bbox=None):
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
        elif subpath.operation in (2, -1):
            if first:
                mask = ImageChops.invert(mask)
            mask = ImageChops.subtract(mask, plane)
        elif subpath.operation == 3:
            if first:
                mask = ImageChops.invert(mask)
            mask = ImageChops.darker(mask, plane)
        first = False

    mask = mask.crop(bbox or layer.bbox)
    mask.info['offset'] = layer.offset
    return mask


def draw_stroke(backdrop, layer, vector_mask=None):
    from PIL import Image, ImageChops
    import aggdraw
    from psd_tools.composer.blend import blend
    width = layer._psd.width
    height = layer._psd.height
    setting = layer.stroke._data

    # Draw mask.
    stroke_width = float(setting.get('strokeStyleLineWidth', 1.))
    mask = Image.new('L', (width, height))
    draw = aggdraw.Draw(mask)
    for subpath in layer.vector_mask.paths:
        path = ' '.join(map(str, _generate_symbol(subpath, width, height)))
        symbol = aggdraw.Symbol(path)
        pen = aggdraw.Pen(255, int(2 * stroke_width))
        draw.symbol((0, 0), symbol, pen, None)
    draw.flush()
    del draw

    # For now, path operations are not implemented.
    if vector_mask:
        vector_mask_ = Image.new('L', (width, height))
        vector_mask_.paste(vector_mask, vector_mask.info['offset'])
        mask = ImageChops.darker(mask, vector_mask_)

    offset = backdrop.info.get('offset', layer.offset)
    bbox = offset + (offset[0] + backdrop.width, offset[1] + backdrop.height)
    mask = mask.crop(bbox)

    # Paint the mask.
    painter = setting.get('strokeStyleContent')
    mode = setting.get('strokeStyleBlendMode').enum
    if not painter:
        logger.warning('Empty stroke style content.')
        return backdrop

    if painter.classID == b'solidColorLayer':
        image = draw_solid_color_fill(mask.size, painter)
    elif painter.classID == b'gradientLayer':
        image = draw_gradient_fill(mask.size, painter)
    elif painter.classID == b'patternLayer':
        image = draw_pattern_fill(mask.size, layer._psd, painter)
    else:
        logger.warning('Unknown painter: %s' % painter)
        return backdrop

    image.putalpha(mask)
    return blend(backdrop, image, (0, 0), mode)


def _draw_subpath(subpath, width, height):
    from PIL import Image
    import aggdraw
    mask = Image.new('L', (width, height), 0)
    if len(subpath) <= 1:
        logger.warning('not enough knots: %d' % len(subpath))
        return mask
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


def _apply_opacity(image, setting):
    opacity = int(setting.get(Key.Opacity, 100))
    if opacity != 100:
        if image.mode.endswith('A'):
            alpha = image.getchannel('A')
            alpha = alpha.point(lambda x: int(x * opacity / 100.))
            image.putalpha(alpha)
        else:
            image.putalpha(int(opacity * 2.55))


def draw_solid_color_fill(size, setting):
    from PIL import Image, ImageDraw
    color = setting.get(Key.Color)
    mode = _COLORSPACE.get(color.classID)
    fill = tuple(int(x) for x in list(color.values())[:len(mode)])
    canvas = Image.new(mode, size)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, canvas.width, canvas.height), fill=fill)
    del draw
    _apply_opacity(canvas, setting)
    return canvas


def draw_pattern_fill(size, psd, setting):
    """
    Create a pattern fill image.

    :param size: (width, height) tuple.
    :param psd: :py:class:`PSDImage`.
    :param setting: Descriptor containing pattern fill.
    """
    from PIL import Image
    pattern_id = setting[Enum.Pattern][Key.ID].value.rstrip('\x00')
    pattern = psd._get_pattern(pattern_id)
    if not pattern:
        logger.error('Pattern not found: %s' % (pattern_id))
        return None
    panel = convert_pattern_to_pil(pattern)

    scale = float(setting.get(Key.Scale, 100.)) / 100.
    if scale != 1.:
        panel = panel.resize((
            max(1, int(panel.width * scale)),
            max(1, int(panel.height * scale)),
        ))
    _apply_opacity(panel, setting)

    pattern_image = Image.new(panel.mode, size)
    for top in range(0, pattern_image.height, panel.height):
        for left in range(0, pattern_image.width, panel.width):
            pattern_image.paste(panel, (left, top))

    return pattern_image


def draw_gradient_fill(size, setting):
    """
    Create a gradient fill image.

    :param size: (width, height) tuple.
    :param setting: Descriptor containing pattern fill.
    """
    try:
        import numpy as np
    except ImportError:
        logger.error('Gradient fill requires numpy and scipy.')
        return None

    angle = float(setting.get(Key.Angle, 0))
    scale = float(setting.get(Key.Scale, 100.)) / 100.
    ratio = (angle % 90)
    scale *= (90. - ratio) / 90. * size[0] + (ratio / 90.) * size[1]
    X, Y = np.meshgrid(
        np.linspace(-size[0] / scale, size[0] / scale, size[0]),
        np.linspace(-size[1] / scale, size[1] / scale, size[1]),
    )

    gradient_kind = setting.get(Key.Type).enum
    if gradient_kind == Enum.Linear:
        Z = _make_linear_gradient(X, Y, angle)
    elif gradient_kind == Enum.Radial:
        Z = _make_radial_gradient(X, Y)
    elif gradient_kind == Enum.Angle:
        Z = _make_angle_gradient(X, Y, angle)
    elif gradient_kind == Enum.Reflected:
        Z = _make_reflected_gradient(X, Y, angle)
    elif gradient_kind == Enum.Diamond:
        Z = _make_diamond_gradient(X, Y, angle)
    elif gradient_kind == b'shapeburst':
        # Only available in stroke effect.
        logger.warning('Gradient style not supported: %s' % gradient_kind)
        Z = np.ones((size[1], size[0])) * 0.5
    else:
        logger.warning('Unknown gradient style: %s.' % (gradient_kind))
        Z = np.ones((size[1], size[0])) * 0.5

    Z = np.maximum(0, np.minimum(1, Z))
    if bool(setting.get(Key.Reverse, False)):
        Z = 1 - Z

    gradient_image = _apply_color_map(setting.get(Key.Gradient), Z)
    _apply_opacity(gradient_image, setting)
    return gradient_image


def _make_linear_gradient(X, Y, angle):
    """Generates index map for linear gradients."""
    import numpy as np
    theta = np.radians(angle % 360)
    Z = .5 * (np.cos(theta) * X - np.sin(theta) * Y + 1)
    return Z


def _make_radial_gradient(X, Y):
    """Generates index map for radial gradients."""
    import numpy as np
    Z = np.sqrt(np.power(X, 2) + np.power(Y, 2))
    return Z


def _make_angle_gradient(X, Y, angle):
    """Generates index map for angle gradients."""
    import numpy as np
    Z = (((180 * np.arctan2(Y, X) / np.pi) + angle) % 360) / 360
    return Z


def _make_reflected_gradient(X, Y, angle):
    """Generates index map for reflected gradients."""
    import numpy as np
    theta = np.radians(angle % 360)
    Z = np.abs((np.cos(theta) * X - np.sin(theta) * Y))
    return Z


def _make_diamond_gradient(X, Y, angle):
    """Generates index map for diamond gradients."""
    import numpy as np
    theta = np.radians(angle % 360)
    Z = np.abs(np.cos(theta) * X - np.sin(theta) *
               Y) + np.abs(np.sin(theta) * X + np.cos(theta) * Y)
    return Z


def _apply_color_map(grad, Z):
    """"""
    import numpy as np
    from scipy import interpolate
    from PIL import Image

    gradient_form = grad.get(Type.GradientForm).enum
    if gradient_form == Enum.ColorNoise:
        """
        TODO: Improve noise gradient quality.

        Example:

            Descriptor(b'Grdn'){
                'Nm  ': 'Custom\x00',
                'GrdF': (b'GrdF', b'ClNs'),
                'ShTr': False,
                'VctC': False,
                'ClrS': (b'ClrS', b'RGBC'),
                'RndS': 3650322,
                'Smth': 2048,
                'Mnm ': [0, 0, 0, 0],
                'Mxm ': [0, 100, 100, 100]
            }
        """
        logger.debug('Noise gradient is not accurate.')
        from scipy.ndimage.filters import maximum_filter1d, uniform_filter1d
        roughness = grad.get(
            Key.Smoothness
        ).value / 4096.  # Larger is sharper.
        maximum = np.array([x.value for x in grad.get(Key.Maximum)])
        minimum = np.array([x.value for x in grad.get(Key.Minimum)])
        seed = grad.get(Key.RandomSeed).value
        mode = _COLORSPACE.get(grad.get(Key.ColorSpace).enum)

        rng = np.random.RandomState(seed)
        G = rng.binomial(1, .5, (256, len(maximum))).astype(np.float)
        size = max(1, int(roughness * 4))
        G = maximum_filter1d(G, size, axis=0)
        G = uniform_filter1d(G, size * 64, axis=0)
        G = (2.55 * ((maximum - minimum) * G + minimum)).astype(np.uint8)
        Z = (255 * Z).astype(np.uint8)
        pixels = G[Z]
        if pixels.shape[-1] == 1:
            pixels = pixels[:, :, 0]
        image = Image.fromarray(pixels, mode)
    elif gradient_form == Enum.CustomStops:
        scalar = {
            'RGB': 1.0,
            'L': 2.55,
            'CMYK': 2.55,
            'LAB': 1.0,
        }
        X, Y = [], []
        mode = None
        for stop in grad.get(Key.Colors, []):
            mode = _COLORSPACE.get(stop.get(Key.Color).classID)
            s = scalar.get(mode, 1.0)
            location = int(stop.get(Key.Location)) / 4096.
            color = list(stop.get(Key.Color).values())[:len(mode)]
            color = tuple(s * int(x) for x in color)
            if len(X) and X[-1] == location:
                logger.debug('Duplicate stop at %d' % location)
                X.pop(), Y.pop()
            X.append(location), Y.append(color)
        assert len(X) > 0
        if len(X) == 1:
            X = [0., 1.]
            Y = [Y[0], Y[0]]
        G = interpolate.interp1d(
            X, Y, axis=0, bounds_error=False, fill_value=(Y[0], Y[-1])
        )
        pixels = G(Z).astype(np.uint8)
        if pixels.shape[-1] == 1:
            pixels = pixels[:, :, 0]

        image = Image.fromarray(pixels, mode)
        if Key.Transparency in grad:
            if mode in ('RGB', 'L'):
                X, Y = [], []
                for stop in grad.get(Key.Transparency):
                    location = int(stop.get(Key.Location)) / 4096.
                    opacity = float(stop.get(Key.Opacity)) * 2.55
                    if len(X) and X[-1] == location:
                        logger.debug('Duplicate stop at %d' % location)
                        X.pop(), Y.pop()
                    X.append(location), Y.append(opacity)
                assert len(X) > 0
                if len(X) == 1:
                    X = [0., 1.]
                    Y = [Y[0], Y[0]]
                G = interpolate.interp1d(
                    X, Y, axis=0, bounds_error=False, fill_value=(Y[0], Y[-1])
                )
                alpha = G(Z).astype(np.uint8)
                image.putalpha(Image.fromarray(alpha, 'L'))
            else:
                logger.warning('Alpha not supported in %s' % (mode))
    else:
        logger.error('Unknown gradient form: %s' % gradient_form)
        return None
    return image
