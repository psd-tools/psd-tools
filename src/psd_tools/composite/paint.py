"""Paint and fill operations for compositing."""

import logging
from typing import TYPE_CHECKING, Any, Callable, Sequence, TypeVar

import numpy as np

from psd_tools.api import numpy_io
from psd_tools.api.utils import EXPECTED_CHANNELS
from psd_tools.color_convert import (
    cmyk_to_rgb,
    gray_to_cmyk,
    gray_to_rgb,
    hsb_to_rgb,
    rgb_to_cmyk,
    rgb_to_grayscale,
)
from psd_tools.composite._compat import require_scipy, require_skimage
from psd_tools.constants import ColorMode, Tag
from psd_tools.psd.descriptor import Descriptor
from psd_tools.terminology import Enum, Key, Klass, Type

if TYPE_CHECKING:
    from psd_tools.api.layers import Layer

logger = logging.getLogger(__name__)


# The modes whose color array is a single channel, so a descriptor color has to
# be reduced to one component to be a legal source for them. Grayscale, bitmap
# and duotone genuinely are one grayscale channel -- duotone's inks live in the
# color mode data section and were never a channel count (#733). Multichannel
# is here for a different reason: its channels are spot inks with no colorimetric relation to RGB, so
# there is no conversion to N of them -- one channel is the honest answer, and
# what a single channel means once widened to N is #722's question, not this
# function's.
_SINGLE_CHANNEL_MODES = (
    ColorMode.BITMAP,
    ColorMode.GRAYSCALE,
    ColorMode.DUOTONE,
    ColorMode.MULTICHANNEL,
)


def _clamp01(value: float) -> float:
    """Hold *value* inside the range a color array is allowed to carry.

    Only the Lab readings need this. Lab is the one color class whose stored
    range is signed, so it is the one whose normalization can leave [0, 1] --
    and :py:func:`psd_tools.composite.composite_pil` casts with
    ``(255 * color).astype(np.uint8)``, which *wraps* rather than saturates. A
    component of 1.29 lands on byte 71 and one of -0.16 on byte 216: not a
    clipped chroma but a colour unrelated to the one asked for. Clamping
    degrades to the end of the axis instead.

    Both branches of ``_get_lab()`` need it, for opposite reasons. The Lab
    target only leaves the range for input outside Photoshop's own -128..127,
    which takes a third-party writer. The RGB and INDEXED targets leave it for
    input squarely *inside* that range: they still divide signed chroma by 255,
    so every negative ``a`` or ``b`` -- every green, every blue -- wraps. That
    reading is wrong for more than its sign and is replaced wholesale by the
    second half of #743; until then it should at least not wrap.
    """
    return min(1.0, max(0.0, value))


def _ink_to_canvas(ink: tuple[float, ...]) -> tuple[float, ...]:
    """Invert an ink-space CMYK tuple into the compositor's canvas convention.

    ``color_convert``'s CMYK helpers are public API with a documented ink-space
    contract -- white is ``(0, 0, 0, 0)``, no ink laid down at all. The
    compositor's arrays are the other way round: they store what is *left*, so
    1.0 is no ink, and ``pil_io.post_process()`` inverts them back on the way
    out. Handing ink space straight to the canvas made a white fill composite
    black (#747).

    Only the conversions *into* CMYK need this. ``_get_cmyk()`` already reads a
    CMYK descriptor through ``_get_invert_color()``, which lands in canvas space
    directly.
    """
    return tuple(1.0 - v for v in ink)


def _from_rgb(color_mode: ColorMode, rgb: tuple[float, ...]) -> tuple[float, ...]:
    """Convert a canonical RGB triple to *color_mode*'s color array width.

    Every descriptor color class reaches the document through here, so the
    result is as wide as the document's own arrays rather than as wide as the
    descriptor happened to be. A fill that is neither one channel nor exactly
    the document's width trips ``Compositor._assert_source_fits()``, which is
    what a solid color, gradient or stroke did on a bitmap, duotone,
    multichannel and (for some classes) indexed, grayscale or Lab document.

    Indexed is deliberately three: its single stored channel expands through
    the palette, so three is the width its pixel arrays carry.
    """
    if color_mode == ColorMode.CMYK:
        return _ink_to_canvas(rgb_to_cmyk(*rgb))
    if color_mode in _SINGLE_CHANNEL_MODES:
        return (rgb_to_grayscale(*rgb),)
    return rgb


def _get_color(color_mode: ColorMode, desc: Descriptor) -> tuple[float, ...]:
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

    def _get_int_color(color_desc: Descriptor, keys: tuple) -> tuple[float, ...]:
        return tuple(float(color_desc[key]) / 255.0 for key in keys)

    def _get_invert_color(color_desc: Descriptor, keys: tuple) -> tuple[float, ...]:
        return tuple((100.0 - float(color_desc[key])) / 100.0 for key in keys)

    def _get_rgb(color_mode: ColorMode, color_desc: Descriptor) -> tuple[float, ...]:
        if Key.Red in color_desc:
            rgb = _get_int_color(color_desc, (Key.Red, Key.Green, Key.Blue))
        else:
            rgb = tuple(
                float(color_desc[key])
                for key in (Key.RedFloat, Key.GreenFloat, Key.BlueFloat)
            )
        return _from_rgb(color_mode, rgb)

    def _get_hsb(color_mode: ColorMode, color_desc: Descriptor) -> tuple[float, ...]:
        hue = float(color_desc[Key.Hue]) / 300.0
        saturation = float(color_desc[Key.Saturation]) / 100.0
        brightness = float(color_desc[Key.Brightness]) / 100.0
        # Every mode but RGB and CMYK used to raise here, which made an HSB
        # solid color or gradient unrenderable on a grayscale, Lab, indexed,
        # bitmap, duotone or multichannel document.
        return _from_rgb(color_mode, hsb_to_rgb(hue, saturation, brightness))

    def _get_gray(color_mode: ColorMode, x: Descriptor) -> tuple[float, ...]:
        (gray,) = _get_invert_color(x, (Key.Gray,))
        if color_mode == ColorMode.RGB:
            return gray_to_rgb(gray)
        if color_mode == ColorMode.CMYK:
            return _ink_to_canvas(gray_to_cmyk(gray))
        return (gray,)

    def _get_cmyk(color_mode: ColorMode, x: Descriptor) -> tuple[float, ...]:
        c, m, y, k = _get_invert_color(
            x, (Key.Cyan, Key.Magenta, Key.Yellow, Key.Black)
        )
        if color_mode == ColorMode.CMYK:
            return (c, m, y, k)
        return _from_rgb(color_mode, cmyk_to_rgb(c, m, y, k))

    def _get_lab(color_mode: ColorMode, x: Descriptor) -> tuple[float, ...]:
        if color_mode == ColorMode.LAB:
            # 255 was the right divisor for none of the three (#743). L runs
            # 0..100 and a/b are signed, which is why psd/color.py reads Lab as
            # "4h" where every other space is "4H".
            #
            # These arrays leave through PIL mode "LAB", whose bytes are
            # L * 255/100 with the two chroma axes offset by 128 -- byte 128 is
            # a = 0, byte 0 is a = -128, at slope exactly 1. So this is not a
            # conversion at all, only a relabelling into the destination's own
            # encoding, and Photoshop's merged preview of a Lab fill agrees with
            # it to within 1/255 across the full a/b range including both ends.
            # (Photoshop's own slope is 254/255: it puts a = 127 on byte 254.
            # Copying that would gain under half a code value against the
            # preview and lose the same against any ImageCms decode.)
            return (
                _clamp01(float(x[Key.Luminance]) / 100.0),
                _clamp01((float(x[Key.A]) + 128.0) / 255.0),
                _clamp01((float(x[Key.B]) + 128.0) / 255.0),
            )
        # Every other target still takes the /255 reading: RGB and INDEXED get
        # the triple, and the modes that would otherwise be the wrong width
        # reduce from L alone. Neither is a conversion. The reduction drops a/b
        # rather than carrying them, so two colours differing only in chroma
        # collapse to one value; the triple keeps them but reads signed chroma
        # as if it were unsigned. Routing both through a real Lab -> RGB and on
        # through _from_rgb() is the second half of #743, and it moves rendered
        # output for RGB and INDEXED documents, so it is left to its own change.
        lab = tuple(
            _clamp01(v) for v in _get_int_color(x, (Key.Luminance, Key.A, Key.B))
        )
        if color_mode in (ColorMode.RGB, ColorMode.INDEXED):
            return lab
        lightness = lab[0]
        if color_mode == ColorMode.CMYK:
            return _ink_to_canvas(gray_to_cmyk(lightness))
        return (lightness,)

    _COLOR_FUNC = {
        Klass.RGBColor: _get_rgb,
        Klass.Grayscale: _get_gray,
        Klass.CMYKColor: _get_cmyk,
        Klass.LabColor: _get_lab,
        Klass.HSBColor: _get_hsb,
    }
    color_desc = desc.get(Key.Color)
    if not color_desc:
        raise ValueError(f"Could not find a color descriptor {desc}")
    return _COLOR_FUNC[color_desc.classID](color_mode, color_desc)


def create_fill_desc(
    layer: "Layer",
    desc: Descriptor,
    viewport: tuple[int, int, int, int],
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Create a fill image."""
    if desc.classID == b"solidColorLayer":
        return draw_solid_color_fill(viewport, layer._psd.color_mode, desc)
    if desc.classID == b"patternLayer":
        return draw_pattern_fill(viewport, layer._psd, desc)
    if desc.classID == b"gradientLayer":
        return draw_gradient_fill(viewport, layer._psd.color_mode, desc)
    return None, None


def create_fill(
    layer: "Layer",
    viewport: tuple[int, int, int, int],
) -> tuple[np.ndarray | None, np.ndarray | None]:
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
    viewport: tuple[int, int, int, int],
    color_mode: ColorMode,
    desc: Descriptor,
) -> tuple[np.ndarray, np.ndarray | None]:
    """
    Create a solid color fill.
    """
    fill = _get_color(color_mode, desc)
    height, width = viewport[3] - viewport[1], viewport[2] - viewport[0]
    color = np.full((height, width, len(fill)), fill, dtype=np.float32)
    return color, None


@require_skimage
def draw_pattern_fill(
    viewport: tuple[int, int, int, int],
    psd: Any,
    desc: Descriptor,
) -> tuple[np.ndarray | None, np.ndarray | None]:
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
    from skimage.transform import resize  # noqa: PLC0415

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
    # Keyed on the *pattern's* mode, not the document's, so this is the one
    # place a document-derived count would be wrong. It is still broken for a
    # multichannel-mode pattern, whose entry is 64 and so never splits the
    # alpha: the real colour count is not recoverable from the parsed pattern
    # (the stored channel count is a fixed 24 slots), so that needs a sample
    # rather than a table fix. See #741.
    channels = EXPECTED_CHANNELS.get(pattern.image_mode)
    pixels = np.tile(panel, reps)[:height, :width, :]
    if channels is not None and pixels.shape[2] > channels:
        return pixels[:, :, :channels], pixels[:, :, -1:]
    return pixels, None


@require_scipy
def draw_gradient_fill(
    viewport: tuple[int, int, int, int],
    color_mode: ColorMode,
    desc: Descriptor,
) -> tuple[np.ndarray | None, np.ndarray | None]:
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


def _make_linear_gradient(X: np.ndarray, Y: np.ndarray, angle: float) -> np.ndarray:
    """Generates index map for linear gradients."""
    theta = np.radians(angle % 360)
    Z = 0.5 * (np.cos(theta) * X - np.sin(theta) * Y + 1)
    return Z


def _make_radial_gradient(X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """Generates index map for radial gradients."""
    Z = np.sqrt(np.power(X, 2) + np.power(Y, 2))
    return Z


def _make_angle_gradient(X: np.ndarray, Y: np.ndarray, angle: float) -> np.ndarray:
    """Generates index map for angle gradients."""
    Z = (((180 * np.arctan2(Y, X) / np.pi) + angle) % 360) / 360
    return Z


def _make_reflected_gradient(X: np.ndarray, Y: np.ndarray, angle: float) -> np.ndarray:
    """Generates index map for reflected gradients."""
    theta = np.radians(angle % 360)
    Z = np.abs((np.cos(theta) * X - np.sin(theta) * Y))
    return Z


def _make_diamond_gradient(X: np.ndarray, Y: np.ndarray, angle: float) -> np.ndarray:
    """Generates index map for diamond gradients."""
    theta = np.radians(angle % 360)
    Z = np.abs(np.cos(theta) * X - np.sin(theta) * Y) + np.abs(
        np.sin(theta) * X + np.cos(theta) * Y
    )
    return Z


def _make_gradient_color(
    color_mode: ColorMode, grad: Descriptor
) -> tuple[Any | None, Any | None]:
    gradient_form = grad.get(Type.GradientForm).enum
    if gradient_form == Enum.ColorNoise:
        return _make_noise_gradient_color(grad)
    elif gradient_form == Enum.CustomStops:
        return _make_linear_gradient_color(color_mode, grad)

    logger.error("Unknown gradient form: %s" % gradient_form)
    return None, None


_T = TypeVar("_T")


def _collect_stops(
    stops: Sequence[Any], value_fn: Callable[[Any], _T]
) -> tuple[list[float], list[_T]]:
    """Collect gradient stop (location, value) pairs, deduplicating co-located stops."""
    X: list[float] = []
    Y: list[_T] = []
    for stop in stops:
        location = float(stop.get(Key.Location)) / 4096.0
        value = value_fn(stop)
        if X and X[-1] == location:
            logger.debug("Duplicate stop at %s", location)
            X.pop()
            Y.pop()
        X.append(location)
        Y.append(value)
    if not X:
        raise ValueError("Gradient has no stops.")
    if len(X) == 1:
        X = [0.0, 1.0]
        Y = [Y[0], Y[0]]
    return X, Y


def _make_linear_gradient_color(
    color_mode: ColorMode, grad: Descriptor
) -> tuple[Any | None, Any | None]:
    from scipy import interpolate  # type: ignore[import-untyped]  # noqa: PLC0415

    Xc, Yc = _collect_stops(
        grad.get(Key.Colors, []),
        lambda stop: np.array(_get_color(color_mode, stop), dtype=np.float32),
    )
    G = interpolate.interp1d(
        Xc, Yc, axis=0, bounds_error=False, fill_value=(Yc[0], Yc[-1])
    )
    if Key.Transparency not in grad:
        return G, None

    Xt, Yt = _collect_stops(
        grad.get(Key.Transparency),
        lambda stop: float(stop.get(Key.Opacity)) / 100.0,
    )
    Ga = interpolate.interp1d(
        Xt, Yt, axis=0, bounds_error=False, fill_value=(Yt[0], Yt[-1])
    )
    return G, Ga


def _make_noise_gradient_color(grad: Descriptor) -> tuple[Any | None, Any | None]:
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
    from scipy import interpolate  # type: ignore[import-untyped]  # noqa: PLC0415
    from scipy.ndimage import maximum_filter1d, uniform_filter1d  # type: ignore[import-untyped]  # noqa: PLC0415

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
