import numpy as np
from skimage.transform import resize
from scipy import interpolate
import logging

from psd_tools.terminology import Enum, Key, Type, Klass
from psd_tools.constants import Tag
from psd_tools.api.numpy_io import get_pattern


logger = logging.getLogger(__name__)


_COLOR_FUNC = {
    Klass.RGBColor: lambda x: x / 255.,
    Klass.Grayscale: lambda x: (100. - x) / 100.,
    Klass.CMYKColor: lambda x: (100 - x) / 100.,
    Klass.LabColor: lambda x: x / 255.,
}


def draw_vector_mask(layer):
    return _draw_path(layer, brush={'color': 255})


def draw_stroke(layer):
    setting = layer.stroke._data
    _CAP = {
        'strokeStyleButtCap': 0,
        'strokeStyleSquareCap': 1,
        'strokeStyleRoundCap': 2,
    }
    _JOIN = {
        'strokeStyleMiterJoin': 0,
        'strokeStyleRoundJoin': 2,
        'strokeStyleBevelJoin': 3,
    }
    width = float(setting.get('strokeStyleLineWidth', 1.))
    linejoin = setting.get('strokeStyleLineJoinType', None)
    linejoin = linejoin.enum if linejoin else 'strokeStyleMiterJoin'
    linecap = setting.get('strokeStyleLineCapType', None)
    linecap = linecap.enum if linecap else 'strokeStyleButtCap'
    miterlimit = setting.get('strokeStyleMiterLimit', 100.0) / 100.
    # aggdraw >= 1.3.12 will support additional params.
    return _draw_path(layer, pen={
        'color': 255,
        'width': width,
        # 'linejoin': _JOIN.get(linejoin, 0),
        # 'linecap': _CAP.get(linecap, 0),
        # 'miterlimit': miterlimit,
    })


def _draw_path(layer, **kwargs):
    height, width = layer._psd.height, layer._psd.width
    color = layer.vector_mask.initial_fill_rule

    mask = np.full((height, width, 1), color)
    first = True
    for subpath in layer.vector_mask.paths:
        plane = _draw_subpath(subpath, width, height, **kwargs)
        if subpath.operation == 0:
            mask = np.maximum(0, mask - plane)
        elif subpath.operation == 1:
            mask = np.maximum(mask, plane)
        elif subpath.operation in (2, -1):
            if first:
                mask = 1 - mask
            mask = np.maximum(0, mask - plane)
        elif subpath.operation == 3:
            if first:
                mask = 1 - mask
            mask = np.minimum(mask, plane)
        first = False
    return np.minimum(1, np.maximum(0, mask))


def _draw_subpath(subpath, width, height, brush=None, pen=None):
    """
    Rasterize Bezier curves.

    TODO: Replace aggdraw implementation.
    """
    from PIL import Image
    import aggdraw
    mask = Image.new('L', (width, height), 0)
    if len(subpath) <= 1:
        logger.warning('not enough knots: %d' % len(subpath))
        return mask
    path = ' '.join(map(str, _generate_symbol(subpath, width, height)))
    draw = aggdraw.Draw(mask)
    pen = aggdraw.Pen(**pen) if pen else None
    brush = aggdraw.Brush(**brush) if brush else None
    symbol = aggdraw.Symbol(path)
    draw.symbol((0, 0), symbol, pen, brush)
    draw.flush()
    del draw
    return np.expand_dims(np.array(mask) / 255., 2)


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


def create_fill_desc(layer, desc, viewport):
    """Create a fill image."""
    if desc.classID == b'solidColorLayer':
        return draw_solid_color_fill(viewport, desc)
    if desc.classID == b'patternLayer':
        return draw_pattern_fill(viewport, layer._psd, desc)
    if desc.classID == b'gradientLayer':
        return draw_gradient_fill(viewport, desc)
    return None, None


def create_fill(layer, viewport):
    """Create a fill image."""
    if Tag.SOLID_COLOR_SHEET_SETTING in layer.tagged_blocks:
        setting = layer.tagged_blocks.get_data(Tag.SOLID_COLOR_SHEET_SETTING)
        return draw_solid_color_fill(viewport, setting)
    if Tag.PATTERN_FILL_SETTING in layer.tagged_blocks:
        setting = layer.tagged_blocks.get_data(Tag.PATTERN_FILL_SETTING)
        return draw_pattern_fill(viewport, layer._psd, setting)
    if Tag.GRADIENT_FILL_SETTING in layer.tagged_blocks:
        setting = layer.tagged_blocks.get_data(Tag.GRADIENT_FILL_SETTING)
        return draw_gradient_fill(viewport, setting)
    return None, None


def draw_solid_color_fill(viewport, setting):
    """
    Create a solid color fill.
    """
    color_desc = setting.get(Key.Color)
    color_fn = _COLOR_FUNC.get(color_desc.classID, 1.0)
    fill = [color_fn(x) for x in color_desc.values()]
    height, width = viewport[3] - viewport[1], viewport[2] - viewport[0]
    color = np.full((height, width, len(fill)), fill)
    return color, None


def draw_pattern_fill(viewport, psd, setting):
    """
    Create a pattern fill.
    """
    pattern_id = setting[Enum.Pattern][Key.ID].value.rstrip('\x00')
    pattern = psd._get_pattern(pattern_id)
    if not pattern:
        logger.error('Pattern not found: %s' % (pattern_id))
        return None

    panel = get_pattern(pattern, psd._record.header.version)

    scale = float(setting.get(Key.Scale, 100.)) / 100.
    if scale != 1.:
        new_shape = (max(1, int(panel.shape[0] * scale)),
                     max(1, int(panel.shape[1] * scale)))
        panel = resize(panel, new_shape)

    height, width = viewport[3] - viewport[1], viewport[2] - viewport[0]
    reps = (
        int(np.ceil(height / panel.shape[0])),
        int(np.ceil(width / panel.shape[1])),
        1,
    )
    return np.tile(panel, reps)[:height, :width, :], None


def draw_gradient_fill(viewport, setting):
    """
    Create a gradient fill image.
    """
    height, width = viewport[3] - viewport[1], viewport[2] - viewport[0]

    angle = float(setting.get(Key.Angle, 0))
    scale = float(setting.get(Key.Scale, 100.)) / 100.
    ratio = (angle % 90)
    scale *= (90. - ratio) / 90. * width + (ratio / 90.) * height
    X, Y = np.meshgrid(
        np.linspace(-width / scale, width / scale, width),
        np.linspace(-height / scale, height / scale, height),
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
    else:
        # Unsupported: b'shapeburst', only avail in stroke effect
        logger.warning('Unknown gradient style: %s.' % (gradient_kind))
        Z = np.ones((height, width)) * 0.5

    Z = np.maximum(0., np.minimum(1., Z))
    if bool(setting.get(Key.Reverse, False)):
        Z = 1. - Z

    G, Ga = _make_gradient_color(setting.get(Key.Gradient))
    color = G(Z) if G is not None else None
    shape = np.expand_dims(Ga(Z), 2) if Ga is not None else None
    return color, shape


def _make_linear_gradient(X, Y, angle):
    """Generates index map for linear gradients."""
    theta = np.radians(angle % 360)
    Z = .5 * (np.cos(theta) * X - np.sin(theta) * Y + 1)
    return Z


def _make_radial_gradient(X, Y):
    """Generates index map for radial gradients."""
    Z = np.sqrt(np.power(X, 2) + np.power(Y, 2))
    return Z


def _make_angle_gradient(X, Y, angle):
    """Generates index map for angle gradients."""
    Z = (((180 * np.arctan2(Y, X) / np.pi) + angle) % 360) / 360
    return Z


def _make_reflected_gradient(X, Y, angle):
    """Generates index map for reflected gradients."""
    theta = np.radians(angle % 360)
    Z = np.abs((np.cos(theta) * X - np.sin(theta) * Y))
    return Z


def _make_diamond_gradient(X, Y, angle):
    """Generates index map for diamond gradients."""
    theta = np.radians(angle % 360)
    Z = np.abs(np.cos(theta) * X - np.sin(theta) *
               Y) + np.abs(np.sin(theta) * X + np.cos(theta) * Y)
    return Z


def _make_gradient_color(grad):
    gradient_form = grad.get(Type.GradientForm).enum
    if gradient_form == Enum.ColorNoise:
        return _make_noise_gradient_color(grad)
    elif gradient_form == Enum.CustomStops:
        return _make_linear_gradient_color(grad)

    logger.error('Unknown gradient form: %s' % gradient_form)
    return None

def _make_linear_gradient_color(grad):
    X, Y = [], []
    for stop in grad.get(Key.Colors, []):
        location = float(stop.get(Key.Location)) / 4096.
        color_fn = _COLOR_FUNC.get(stop.get(Key.Color).classID)
        color = np.array([color_fn(x) for x in stop.get(Key.Color).values()])
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
    if Key.Transparency not in grad:
        return G, None

    X, Y = [], []
    for stop in grad.get(Key.Transparency):
        location = float(stop.get(Key.Location)) / 4096.
        opacity = float(stop.get(Key.Opacity)) / 100.
        if len(X) and X[-1] == location:
            logger.debug('Duplicate stop at %d' % location)
            X.pop(), Y.pop()
        X.append(location), Y.append(opacity)
    assert len(X) > 0
    if len(X) == 1:
        X = [0., 1.]
        Y = [Y[0], Y[0]]
    Ga = interpolate.interp1d(
        X, Y, axis=0, bounds_error=False, fill_value=(Y[0], Y[-1])
    )
    return G, Ga


def _make_noise_gradient_color(grad):
    """
    Make a noise gradient color.

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
    from scipy.ndimage.filters import maximum_filter1d, uniform_filter1d
    logger.debug('Noise gradient is not accurate.')
    roughness = grad.get(Key.Smoothness).value / 4096.  # Larger is sharper.
    maximum = np.array([x.value for x in grad.get(Key.Maximum)])
    minimum = np.array([x.value for x in grad.get(Key.Minimum)])
    seed = grad.get(Key.RandomSeed).value
    rng = np.random.RandomState(seed)
    Y = rng.binomial(1, .5, (256, len(maximum))).astype(np.float)
    size = max(1, int(roughness))
    Y = maximum_filter1d(Y, size, axis=0)
    Y = uniform_filter1d(Y, size * 64, axis=0)
    Y = Y / np.max(Y, axis=0)
    Y = ((maximum - minimum) * Y + minimum) / 100.
    X = np.linspace(0, 1, 256)
    if grad.get(Key.ShowTransparency):
        G = interpolate.interp1d(
           X, Y[:, :-1], axis=0, bounds_error=False,
           fill_value=(Y[0, :-1], Y[-1, :-1])
        )
        Ga = interpolate.interp1d(
           X, Y[:, -1], axis=0, bounds_error=False,
           fill_value=(Y[0, -1], Y[-1, -1])
        )
    else:
        G = interpolate.interp1d(
           X, Y[:, :3], axis=0, bounds_error=False,
           fill_value=(Y[0, :3], Y[-1, :3])
        )
        Ga = None
    return G, Ga