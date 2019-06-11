"""
Vector module.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools.api.pil_io import convert_pattern_to_pil
from psd_tools.composer.blend import blend
from psd_tools.terminology import Enum, Key

logger = logging.getLogger(__name__)


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


def draw_solid_color_fill(image, setting, mode=None):
    from PIL import Image, ImageDraw, ImageChops
    color = tuple(int(x) for x in setting.get(b'Clr ').values())
    canvas = Image.new(image.mode, image.size)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, canvas.width, canvas.height), fill=color)
    del draw
    if mode:
        if image.mode.endswith('A'):
            canvas.putalpha(image.getchannel('A'))
        blend(image, canvas, (0, 0), mode=mode)
    else:
        image.paste(canvas)


def draw_pattern_fill(image, psd, setting, mode=None):
    """
    Draw pattern fill on the image.

    :param image: Image to be filled.
    :param psd: :py:class:`PSDImage`.
    :param setting: Descriptor containing pattern fill.
    :param mode: Blend the fill or ignore if None.
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
    if mode and image.mode.endswith('A'):
        mask = image.getchannel('A')
    else:
        mask = Image.new('L', image.size, 255)

    for left in range(0, pattern_image.width, panel.width):
        for top in range(0, pattern_image.height, panel.height):
            panel_mask = mask.crop(
                (left, top, left + panel.width, top + panel.height)
            )
            pattern_image.paste(panel, (left, top), panel_mask)

    if mode:
        image.paste(blend(image, pattern_image, (0, 0), mode=mode))
    else:
        image.paste(pattern_image)


def draw_gradient_fill(image, setting, mode=None):
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
    if gradient_image:
        if mode:
            if image.mode.endswith('A'):
                gradient_image.putalpha(image.getchannel('A'))
            blend(image, gradient_image, (0, 0), mode=mode)
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

    if grad.get(b'GrdF').enum == Enum.ColorNoise:
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

        rng = np.random.RandomState(seed)
        G = rng.binomial(1, .5, (256, len(maximum))).astype(np.float)
        size = int(roughness * 4)
        G = maximum_filter1d(G, size, axis=0)
        G = uniform_filter1d(G, size * 64, axis=0)
        G = (2.55 * ((maximum - minimum) * G + minimum)).astype(np.uint8)
        Z = (255 * Z).astype(np.uint8)
        pixels = G[Z]
        if pixels.shape[-1] == 1:
            pixels = pixels[:, :, 0]
        image = Image.fromarray(pixels, mode)
    elif grad.get(b'GrdF').enum == Enum.CustomStops:
        scalar = {
            'RGB': 1.0,
            'L': 2.55,
            'CMYK': 2.55,
        }.get(mode, 1.0)
        stops = grad.get(b'Clrs')
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
