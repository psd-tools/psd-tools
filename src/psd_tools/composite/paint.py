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
    lab_to_rgb,
    rgb_to_cmyk,
    rgb_to_grayscale,
    rgb_to_lab,
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

    Every descriptor color class normalizes by a fixed divisor, and nothing in
    the format constrains the component to the range that divisor assumes: a
    writer emitting ``a = 200`` yields 1.29, ``Gry = 150`` yields -0.5 and
    ``Rd   = 300`` yields 1.18.

    A component outside ``[0, 1]`` reaches the image by two routes, and only
    one of them is still open. ``Compositor`` runs ``utils.clip()`` on its own
    arrays, but the clip runs *after* the value has been blended, so wherever
    the color is composited rather than laid down flat -- an effect, a partial
    alpha, an anti-aliased vector edge -- the out-of-range component corrupts
    the arithmetic first and clipping has nothing left to recover. Forging
    ``Gry = 150`` into ``adjustment-fillers.psd`` puts 194 white pixels along
    the shape's stroke where the stroke is ``(26, 26, 26)``, and
    ``H = 0, Strt = 120, Brgh = 150`` puts 150 bright cyan ones there (#757).

    The closed route is the uint8 cast. ``composite_pil()`` used to write
    ``(255 * color).astype(np.uint8)``, and numpy *wraps* rather than
    saturating, so those three components would have landed on bytes 72, 129
    and 44. It clips as of #757, so nothing here depends on that cast to
    saturate; the two guards are independent on purpose.

    Clamping degrades to the end of the axis instead, which is the policy
    :py:func:`psd_tools.color_convert.lab_to_rgb` already follows. Applied
    where the untrusted number enters rather than inside ``color_convert``, so
    those conversions keep their documented ``[0, 1]`` input contracts instead
    of having to defend them. Saturation and brightness are the exception: they
    reach :py:func:`psd_tools.color_convert.hsb_to_rgb`, which is total and
    clamps them itself, so they never arrive here.

    NaN maps to 0.0, because ``nan > 0.0`` is false and ``max`` therefore keeps
    its first argument. That is wanted -- a malformed descriptor degrades to the
    end of the axis rather than poisoning the canvas -- but it is a property of
    the argument order, so do not reverse it.
    """
    return min(1.0, max(0.0, value))


def _lab_to_canvas(lightness: float, a: float, b: float) -> tuple[float, ...]:
    """Encode native CIE L*a*b* into the compositor's Lab color array.

    The arrays leave through PIL mode "LAB", whose bytes are ``L * 255/100``
    with the two chroma axes offset by 128 -- byte 128 is ``a = 0``, byte 0 is
    ``a = -128``, at slope exactly 1. So this is a relabelling into the
    destination's own encoding rather than a conversion, and Photoshop's own
    render of a Lab fill agrees with it to within 1/255 across the full a/b
    range (#743).

    Shared by the two ways a Lab value arrives: a Lab descriptor on a Lab
    document, which lands here unconverted, and any other color class on a Lab
    document, which reaches here through
    :py:func:`psd_tools.color_convert.rgb_to_lab` (#752).
    """
    return (
        _clamp01(lightness / 100.0),
        _clamp01((a + 128.0) / 255.0),
        _clamp01((b + 128.0) / 255.0),
    )


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

    Lab is a real conversion rather than a width choice. It used to fall through
    to ``return rgb``, which is three wide and so passed the width assertion
    while meaning nothing: red arrived as ``(1.0, 0.0, 0.0)``, which a Lab array
    reads as white at the extreme green-blue corner rather than as
    ``(0.543, 0.819, 0.776)`` (#752).
    """
    if color_mode == ColorMode.CMYK:
        return _ink_to_canvas(rgb_to_cmyk(*rgb))
    if color_mode == ColorMode.LAB:
        return _lab_to_canvas(*rgb_to_lab(*rgb))
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
        return tuple(_clamp01(float(color_desc[key]) / 255.0) for key in keys)

    def _get_invert_color(color_desc: Descriptor, keys: tuple) -> tuple[float, ...]:
        return tuple(_clamp01((100.0 - float(color_desc[key])) / 100.0) for key in keys)

    def _get_rgb(color_mode: ColorMode, color_desc: Descriptor) -> tuple[float, ...]:
        if Key.Red in color_desc:
            rgb = _get_int_color(color_desc, (Key.Red, Key.Green, Key.Blue))
        else:
            # No divisor, unlike ``Rd  ``/``Grn ``/``Bl  ``: these components
            # are the format's own normalized spelling. Nothing under
            # tests/psd_files carries one, so that scale is taken on the
            # format's word rather than measured here -- which is exactly why
            # the clamp matters on this path. If the scale is what it claims,
            # the clamp never fires; if it is not, an unexpected value
            # saturates instead of wrapping to an unrelated colour (#757).
            rgb = tuple(
                _clamp01(float(color_desc[key]))
                for key in (Key.RedFloat, Key.GreenFloat, Key.BlueFloat)
            )
        return _from_rgb(color_mode, rgb)

    def _get_hsb(color_mode: ColorMode, color_desc: Descriptor) -> tuple[float, ...]:
        # ``H   `` is an angle in degrees, so the full turn is 360 and not 300.
        # The old divisor rotated every non-zero hue -- 120 deg was read as
        # 0.4, which is 144 deg -- and pushed 360 clean off the end of the
        # six-sector table, where the achromatic fallback turned a fully
        # saturated red into white (#754).
        hue = float(color_desc[Key.Hue]) / 360.0
        # Not clamped, unlike the other classes. Hue is cyclic, so 400 deg
        # names a real angle and ``hsb_to_rgb`` wraps it; clamping would turn
        # it into 360. Saturation and brightness are clamped by ``hsb_to_rgb``
        # itself, which is total, so guarding them again here would defend the
        # same two numbers twice (#757).
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
        if color_mode == ColorMode.LAB:
            # Not left to widen(): one channel is a legal width, so a grey fill
            # was reaching a Lab canvas as a bare lightness and being widened
            # with a neutral a/b. That put it on the right axis but at the wrong
            # height -- the grey itself rather than its L* -- and disagreed with
            # the same grey written as an RGB descriptor (#752).
            return _from_rgb(color_mode, gray_to_rgb(gray))
        return (gray,)

    def _get_cmyk(color_mode: ColorMode, x: Descriptor) -> tuple[float, ...]:
        c, m, y, k = _get_invert_color(
            x, (Key.Cyan, Key.Magenta, Key.Yellow, Key.Black)
        )
        if color_mode == ColorMode.CMYK:
            return (c, m, y, k)
        return _from_rgb(color_mode, cmyk_to_rgb(c, m, y, k))

    def _get_lab(color_mode: ColorMode, x: Descriptor) -> tuple[float, ...]:
        lightness = float(x[Key.Luminance])
        a = float(x[Key.A])
        b = float(x[Key.B])
        if color_mode == ColorMode.LAB:
            # Straight into the array's own encoding, with no trip through RGB
            # to lose anything on (#743).
            return _lab_to_canvas(lightness, a, b)
        # Everything else is a real conversion now. It used to divide all three
        # by 255 and hand RGB and INDEXED the raw triple -- reading signed
        # chroma as unsigned, and putting L = 100 at 0.39 -- while the narrower
        # modes reduced from L alone, dropping a/b so that two colours differing
        # only in chroma collapsed to one value (the second half of #743).
        return _from_rgb(color_mode, lab_to_rgb(lightness, a, b))

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
        return _make_noise_gradient_color(color_mode, grad)
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


def _noise_color_components(table: np.ndarray) -> np.ndarray:
    """The three color columns of a noise gradient's table.

    Narrower is not something any writer here has produced; replicating the
    first column keeps such a file rendering as a grey ramp rather than
    raising on the unpack in :py:func:`_noise_to_canvas`.
    """
    if table.shape[1] >= 3:
        return table[:, :3]
    logger.debug("Noise gradient has %d components, expected 4.", table.shape[1])
    return np.repeat(table[:, :1], 3, axis=1)


def _noise_to_canvas(
    color_mode: ColorMode, space: bytes, table: np.ndarray
) -> np.ndarray:
    """Map a noise gradient's lookup table from *space* into the document's arrays.

    The three colour components of a noise gradient are stored as percentages
    of their own space's normalized encoding rather than as native values.
    Measured against Photoshop 2026 by authoring flat gradients -- ``Mnm ``
    equal to ``Mxm ``, which pins the noise field to one colour and so gives a
    render comparable without reproducing Photoshop's noise synthesis -- and
    reading the stored channels back:

    - ``RGBC``: ``v / 100`` is the channel, so 50 is 128/255.
    - ``HSBl``: ``v / 100`` is the fraction of a full turn for the hue, and the
      fraction of the axis for saturation and brightness; 33 rendered as 118.8
      degrees.
    - ``LbCl``: ``v / 100`` is the *byte* of the eight-bit Lab encoding, which
      is the compositor's own Lab array convention. So ``L* = v``, and
      ``a = b = 0`` at 50 rather than at 0. In a Lab document the table needs
      no conversion at all; the value stored for a flat ``[60, 60, 60]``
      gradient is exactly ``(153, 153, 153)``.

    Every one of the three is a colour space independent of the document's
    mode, which is the width bug this fixes: the table came back three wide
    whatever the document was (#730).
    """
    if space not in (Enum.RGBColor, Enum.HSBColor, Enum.LabColor):
        # Photoshop offers exactly those three, so anything else is another
        # writer's. Reading it as RGB is what this did for all three before,
        # and a wrong color beats refusing to render.
        logger.debug("Unknown noise gradient color space: %s", space)

    rows: list[tuple[float, ...]] = []
    for row in table:
        c0, c1, c2 = (float(value) for value in row)
        if space == Enum.HSBColor:
            rgb = hsb_to_rgb(c0, c1, c2)
        elif space == Enum.LabColor:
            if color_mode == ColorMode.LAB:
                # Already the destination encoding, so a trip through RGB
                # would only lose the out-of-gamut values on the way.
                rows.append((_clamp01(c0), _clamp01(c1), _clamp01(c2)))
                continue
            rgb = lab_to_rgb(c0 * 100.0, c1 * 255.0 - 128.0, c2 * 255.0 - 128.0)
        else:
            # Clamped for the same reason the descriptor readers are: these
            # components come from ``Mnm ``/``Mxm ``, which are raw file
            # values, so a band at ``Mxm = 150`` leaves [0, 1]. The other two
            # spaces are already covered -- HSB by ``hsb_to_rgb`` and Lab by
            # ``lab_to_rgb`` and ``_clamp01`` above -- which left RGB as the
            # one unguarded noise path (#757).
            rgb = (_clamp01(c0), _clamp01(c1), _clamp01(c2))
        rows.append(_from_rgb(color_mode, rgb))
    return np.array(rows, dtype=np.float32)


def _make_noise_gradient_color(
    color_mode: ColorMode, grad: Descriptor
) -> tuple[Any | None, Any | None]:
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
    # Photoshop writes four components for each of its three noise color
    # spaces -- three color and one transparency -- and writes the fourth
    # whether or not ``ShTr`` is set, so the color triple is the leading three
    # either way.
    color_space = grad.get(Key.ColorSpace)
    Yc = _noise_to_canvas(
        color_mode,
        color_space.enum if color_space is not None else Enum.RGBColor,
        _noise_color_components(Y),
    )
    G = interpolate.interp1d(
        X, Yc, axis=0, bounds_error=False, fill_value=(Yc[0], Yc[-1])
    )
    if not grad.get(Key.ShowTransparency):
        return G, None
    # Clamped like the color components, and from the same raw ``Mnm ``/``Mxm ``
    # values (#757).
    Ya = np.clip(Y[:, -1], 0.0, 1.0)
    Ga = interpolate.interp1d(
        X, Ya, axis=0, bounds_error=False, fill_value=(Ya[0], Ya[-1])
    )
    return G, Ga
