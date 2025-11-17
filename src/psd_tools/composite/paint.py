"""Paint and fill operations for compositing."""

import logging
from typing import Optional, Tuple

import numpy as np

from psd_tools.api import numpy_io
from psd_tools.api.utils import EXPECTED_CHANNELS
from psd_tools.composite._compat import require_scipy, require_skimage
from psd_tools.constants import ColorMode, Tag
from psd_tools.terminology import Enum, Key, Klass, Type

logger = logging.getLogger(__name__)


def _get_color(color_mode, desc) -> Tuple[float, ...]:
    """Return color tuple from descriptor.

    Example descriptor::

        Descriptor(b'solidColorLayer'){
            'Clr ': Descriptor(b'CMYC'){
                'Cyn ': 83.04,
                'Mgnt': 74.03,
                'Ylw ': 80.99,
                'Blck': 58.3
                }
            }

        Descriptor(b'solidColorLayer'){
            'Clr ': Descriptor(b'RGBC'){
                'Rd  ': 235.90926200151443,
                'Grn ': 232.29671984910965,
                'Bl  ': 25.424751117825508,
                'Bk  ': 'PANTONE+® Solid Coated\x00',
                'Nm  ': 'PANTONE 395 C\x00',
                'bookID': 3060,
                'bookKey': RawData(value=b'1123SC')
                }
            }
    """

    def _get_int_color(color_desc, keys):
        return tuple(float(color_desc[key]) / 255.0 for key in keys)

    def _get_invert_color(color_desc, keys):
        return tuple((100.0 - float(color_desc[key])) / 100.0 for key in keys)

    def hsb_to_rgb(h: float, s: float, v: float) -> Tuple[float, ...]:
        if s:
            if h == 1.0:
                h = 0.0
            i = int(h * 6.0)
            f = h * 6.0 - i

            w = v * (1.0 - s)
            q = v * (1.0 - s * f)
            t = v * (1.0 - s * (1.0 - f))

            if i == 0:
                return (v, t, w)
            if i == 1:
                return (q, v, w)
            if i == 2:
                return (w, v, t)
            if i == 3:
                return (w, q, v)
            if i == 4:
                return (t, w, v)
            if i == 5:
                return (v, w, q)
            return (v, v, v)  # fallback for unexpected i values
        else:
            return (v, v, v)

    def rgb_to_cmyk(r, g, b) -> Tuple[float, ...]:
        if (r, g, b) == (0, 0, 0):
            # black
            return (0.0, 0.0, 0.0)
        c = 1 - r
        m = 1 - g
        y = 1 - b

        min_cmy = min(c, m, y)
        c = (c - min_cmy) / (1 - min_cmy)
        m = (m - min_cmy) / (1 - min_cmy)
        y = (y - min_cmy) / (1 - min_cmy)
        k = min_cmy
        return (c, m, y, k)

    def _get_rgb(color_mode, color_desc):
        if Key.Red in color_desc:
            return _get_int_color(color_desc, (Key.Red, Key.Green, Key.Blue))
        else:
            return tuple(
                float(color_desc[key])
                for key in (Key.RedFloat, Key.GreenFloat, Key.BlueFloat)
            )

    def _get_hsb(color_mode, color_desc):
        hue = float(color_desc[Key.Hue]) / 300.0
        saturation = float(color_desc[Key.Saturation]) / 100.0
        brightness = float(color_desc[Key.Brightness]) / 100.0
        rgb_components = hsb_to_rgb(hue, saturation, brightness)
        if color_mode == ColorMode.RGB:
            return rgb_components
        if color_mode == ColorMode.CMYK:
            return rgb_to_cmyk(rgb_components[0], rgb_components[1], rgb_components[2])
        raise ValueError("Unexpected color mode for HSB color %s" % (color_mode))

    def _get_gray(color_mode, x):
        return _get_invert_color(x, (Key.Gray,))

    def _get_cmyk(color_mode, x):
        return _get_invert_color(x, (Key.Cyan, Key.Magenta, Key.Yellow, Key.Black))

    def _get_lab(color_mode, x):
        return _get_int_color(x, (Key.Luminance, Key.A, Key.B))

    _COLOR_FUNC = {
        Klass.RGBColor: _get_rgb,
        Klass.Grayscale: _get_gray,
        Klass.CMYKColor: _get_cmyk,
        Klass.LabColor: _get_lab,
        Klass.HSBColor: _get_hsb,
    }
    color_desc = desc.get(Key.Color)
    assert color_desc, f"Could not find a color descriptor {desc}"
    return _COLOR_FUNC[color_desc.classID](color_mode, color_desc)


def create_fill_desc(layer, desc, viewport):
    """Create a fill image."""
    if desc.classID == b"solidColorLayer":
        return draw_solid_color_fill(viewport, layer._psd.color_mode, desc)
    if desc.classID == b"patternLayer":
        return draw_pattern_fill(viewport, layer._psd, desc)
    if desc.classID == b"gradientLayer":
        return draw_gradient_fill(viewport, layer._psd.color_mode, desc)
    return None, None


def create_fill(layer, viewport):
    """Create a fill image."""
    if Tag.SOLID_COLOR_SHEET_SETTING in layer.tagged_blocks:
        desc = layer.tagged_blocks.get_data(Tag.SOLID_COLOR_SHEET_SETTING)
        return draw_solid_color_fill(viewport, layer._psd.color_mode, desc)
    if Tag.PATTERN_FILL_SETTING in layer.tagged_blocks:
        desc = layer.tagged_blocks.get_data(Tag.PATTERN_FILL_SETTING)
        return draw_pattern_fill(viewport, layer._psd, desc)
    if Tag.GRADIENT_FILL_SETTING in layer.tagged_blocks:
        desc = layer.tagged_blocks.get_data(Tag.GRADIENT_FILL_SETTING)
        return draw_gradient_fill(viewport, layer._psd.color_mode, desc)
    if Tag.VECTOR_STROKE_CONTENT_DATA in layer.tagged_blocks:
        stroke = layer.tagged_blocks.get_data(Tag.VECTOR_STROKE_DATA)
        if not stroke or stroke.get("fillEnabled").value is True:
            desc = layer.tagged_blocks.get_data(Tag.VECTOR_STROKE_CONTENT_DATA)
            if Key.Color in desc:
                return draw_solid_color_fill(viewport, layer._psd.color_mode, desc)
            elif Key.Pattern in desc:
                return draw_pattern_fill(viewport, layer._psd, desc)
            elif Key.Gradient in desc:
                return draw_gradient_fill(viewport, layer._psd.color_mode, desc)
    return None, None


def draw_solid_color_fill(
    viewport: Tuple[int, int, int, int], color_mode: ColorMode, desc
) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    """
    Create a solid color fill.
    """
    fill = _get_color(color_mode, desc)
    height, width = viewport[3] - viewport[1], viewport[2] - viewport[0]
    color = np.full((height, width, len(fill)), fill, dtype=np.float32)
    return color, None


@require_skimage
def draw_pattern_fill(
    viewport: Tuple[int, int, int, int], psd, desc
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """
    Create a pattern fill.

    Example descriptor::

        Descriptor(b'patternFill'){
            'enab': True,
            'present': True,
            'showInDialog': True,
            'Md  ': (b'BlnM', b'CBrn'),
            'Opct': 100.0 Percent,
            'Ptrn': Descriptor(b'Ptrn'){
                'Nm  ': 'foo\x00',
                'Idnt': '5e1713ab-e968-4c4c-8855-c8fa2cde8610\x00'
                },
            'Angl': 0.0 Angle,
            'Scl ': 87.0 Percent,
            'Algn': True,
            'phase': Descriptor(b'Pnt '){'Hrzn': 0.0, 'Vrtc': 0.0}
            }

    .. todo:: Test this.
    """
    from skimage.transform import resize

    pattern_id = desc[Enum.Pattern][Key.ID].value.rstrip("\x00")
    pattern = psd._get_pattern(pattern_id)
    if not pattern:
        logger.error("Pattern not found: %s" % (pattern_id))
        return None, None

    panel = numpy_io.get_pattern(pattern)
    assert panel.shape[0] > 0

    scale = float(desc.get(Key.Scale, 100.0)) / 100.0
    if scale != 1.0:
        new_shape = (
            max(1, int(panel.shape[0] * scale)),
            max(1, int(panel.shape[1] * scale)),
        )
        panel = resize(panel, new_shape)

    height, width = viewport[3] - viewport[1], viewport[2] - viewport[0]
    reps = (
        int(np.ceil(float(height) / panel.shape[0])),
        int(np.ceil(float(width) / panel.shape[1])),
        1,
    )
    channels = EXPECTED_CHANNELS.get(pattern.image_mode)
    pixels = np.tile(panel, reps)[:height, :width, :]
    if channels is not None and pixels.shape[2] > channels:
        return pixels[:, :, :channels], pixels[:, :, -1:]
    return pixels, None


@require_scipy
def draw_gradient_fill(
    viewport: Tuple[int, int, int, int], color_mode: ColorMode, desc
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """
    Create a gradient fill image.

    Requires scipy for gradient color interpolation.
    """
    height, width = viewport[3] - viewport[1], viewport[2] - viewport[0]

    angle = float(desc.get(Key.Angle, 0))
    scale = float(desc.get(Key.Scale, 100.0)) / 100.0
    ratio = angle % 90
    scale *= (90.0 - ratio) / 90.0 * width + (ratio / 90.0) * height
    X, Y = np.meshgrid(
        np.linspace(-width / scale, width / scale, width, dtype=np.float32),
        np.linspace(-height / scale, height / scale, height, dtype=np.float32),
    )

    gradient_kind = desc.get(Key.Type).enum
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
        logger.warning("Unknown gradient style: %s." % (gradient_kind))
        Z = np.full((height, width), 0.5, dtype=np.float32)

    Z = np.maximum(0.0, np.minimum(1.0, Z))
    if bool(desc.get(Key.Reverse, False)):
        Z = 1.0 - Z

    G, Ga = _make_gradient_color(color_mode, desc.get(Key.Gradient))
    color = G(Z) if G is not None else None
    shape = np.expand_dims(Ga(Z), 2) if Ga is not None else None
    return color, shape


def _make_linear_gradient(X, Y, angle):
    """Generates index map for linear gradients."""
    theta = np.radians(angle % 360)
    Z = 0.5 * (np.cos(theta) * X - np.sin(theta) * Y + 1)
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
    Z = np.abs(np.cos(theta) * X - np.sin(theta) * Y) + np.abs(
        np.sin(theta) * X + np.cos(theta) * Y
    )
    return Z


def _make_gradient_color(color_mode, grad):
    gradient_form = grad.get(Type.GradientForm).enum
    if gradient_form == Enum.ColorNoise:
        return _make_noise_gradient_color(grad)
    elif gradient_form == Enum.CustomStops:
        return _make_linear_gradient_color(color_mode, grad)

    logger.error("Unknown gradient form: %s" % gradient_form)
    return None, None


def _make_linear_gradient_color(color_mode, grad):
    from scipy import interpolate  # type: ignore[import-untyped]

    X, Y = [], []
    for stop in grad.get(Key.Colors, []):
        location = float(stop.get(Key.Location)) / 4096.0
        color = np.array(_get_color(color_mode, stop), dtype=np.float32)
        if len(X) and X[-1] == location:
            logger.debug("Duplicate stop at %d" % location)
            X.pop(), Y.pop()
        X.append(location), Y.append(color)
    assert len(X) > 0
    if len(X) == 1:
        X = [0.0, 1.0]
        Y = [Y[0], Y[0]]
    G = interpolate.interp1d(X, Y, axis=0, bounds_error=False, fill_value=(Y[0], Y[-1]))
    if Key.Transparency not in grad:
        return G, None

    X, Y = [], []
    for stop in grad.get(Key.Transparency):
        location = float(stop.get(Key.Location)) / 4096.0
        opacity = float(stop.get(Key.Opacity)) / 100.0
        if len(X) and X[-1] == location:
            logger.debug("Duplicate stop at %d" % location)
            X.pop(), Y.pop()
        X.append(location), Y.append(opacity)
    assert len(X) > 0
    if len(X) == 1:
        X = [0.0, 1.0]
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
    from scipy import interpolate  # type: ignore[import-untyped]
    from scipy.ndimage import maximum_filter1d, uniform_filter1d  # type: ignore[import-untyped]

    logger.debug("Noise gradient is not accurate.")
    roughness = grad.get(Key.Smoothness).value / 4096.0  # Larger is sharper.
    maximum = np.array([x.value for x in grad.get(Key.Maximum)], dtype=np.float32)
    minimum = np.array([x.value for x in grad.get(Key.Minimum)], dtype=np.float32)
    seed = grad.get(Key.RandomSeed).value
    rng = np.random.RandomState(seed)
    Y = rng.binomial(1, 0.5, (256, len(maximum))).astype(np.float32)
    size = max(1, int(roughness))
    Y = maximum_filter1d(Y, size, axis=0)
    Y = uniform_filter1d(Y, size * 64, axis=0)
    Y = Y / np.max(Y, axis=0)
    Y = ((maximum - minimum) * Y + minimum) / 100.0
    X = np.linspace(0, 1, 256, dtype=np.float32)
    if grad.get(Key.ShowTransparency):
        G = interpolate.interp1d(
            X, Y[:, :-1], axis=0, bounds_error=False, fill_value=(Y[0, :-1], Y[-1, :-1])
        )
        Ga = interpolate.interp1d(
            X, Y[:, -1], axis=0, bounds_error=False, fill_value=(Y[0, -1], Y[-1, -1])
        )
    else:
        G = interpolate.interp1d(
            X, Y[:, :3], axis=0, bounds_error=False, fill_value=(Y[0, :3], Y[-1, :3])
        )
        Ga = None
    return G, Ga
