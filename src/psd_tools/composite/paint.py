"""Paint and fill operations for compositing."""

import logging
import math
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, TypeVar

import numpy as np

from psd_tools.api import numpy_io
from psd_tools.api.utils import check_pixel_size, dimension_limit
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
from psd_tools.composite._compat import require_scipy
from psd_tools.composite.utils import is_fill_disabled
from psd_tools.constants import ColorMode, Tag
from psd_tools.psd.descriptor import Descriptor
from psd_tools.terminology import Enum, Key, Klass, Type

if TYPE_CHECKING:
    from psd_tools.api.layers import Layer

logger = logging.getLogger(__name__)


class _UnreadableDescriptor(ValueError):
    """A fill descriptor that cannot be read, as opposed to one over budget."""


# Per pixel, what a gradient fill peaks at: its coordinate grids and ramp
# planes outweigh the float32 colour it returns.
GRADIENT_FILL_BYTES = 128


# The modes whose color array is a single channel, so a descriptor color has to
# be reduced to one component to be a legal source for them. Grayscale, bitmap
# and duotone genuinely are one grayscale channel -- duotone's inks live in the
# color mode data section and were never a channel count (#733). Multichannel
# is here for a different reason: its channels are spot inks with no colorimetric relation to RGB, so
# there is no conversion to N of them -- one channel is the honest answer, and
# what a single channel means once widened to N is #722's question -- #749's
# where the single channel is a source, as this one is -- not this function's.
_SINGLE_CHANNEL_MODES = (
    ColorMode.BITMAP,
    ColorMode.GRAYSCALE,
    ColorMode.DUOTONE,
    ColorMode.MULTICHANNEL,
)


def _clamp01(value: float) -> float:
    """Clamp an unconstrained descriptor component to [0, 1], NaN to 0.0 (#757).

    Applied where the untrusted number enters, because ``utils.clip()`` runs
    too late once the color is blended. ``max`` keeps its first argument when
    a comparison with NaN is false, so the bound goes first; do not reverse it.
    """
    return min(1.0, max(0.0, value))


def _lab_to_canvas(lightness: float, a: float, b: float) -> tuple[float, ...]:
    """Encode native CIE L*a*b* into the compositor's Lab color array.

    PIL mode "LAB" stores ``L * 255/100`` with the chroma axes offset by 128, so
    this is a relabelling, not a conversion (#743). Shared by a Lab descriptor
    on a Lab document and by other color classes via
    :py:func:`psd_tools.color_convert.rgb_to_lab` (#752).
    """
    return (
        _clamp01(lightness / 100.0),
        _clamp01((a + 128.0) / 255.0),
        _clamp01((b + 128.0) / 255.0),
    )


def _ink_to_canvas(ink: tuple[float, ...]) -> tuple[float, ...]:
    """Invert an ink-space CMYK tuple into the compositor's canvas convention.

    Ink space has white at all zeros; the canvas stores what is *left*, so 1.0
    is no ink (#747). Only conversions *into* CMYK need this; ``_get_cmyk()``
    already lands in canvas space.
    """
    return tuple(1.0 - v for v in ink)


def _from_rgb(color_mode: ColorMode, rgb: tuple[float, ...]) -> tuple[float, ...]:
    """Convert a canonical RGB triple to *color_mode*'s color array width.

    Every descriptor color class goes through here, so a fill matches the
    document's array width, which ``Compositor._assert_source_fits()`` checks.
    Indexed is three because its stored channel expands through the palette.
    Lab is a real conversion, not a width choice (#752).
    """
    if color_mode == ColorMode.CMYK:
        return _ink_to_canvas(rgb_to_cmyk(*rgb))
    if color_mode == ColorMode.LAB:
        return _lab_to_canvas(*rgb_to_lab(*rgb))
    if color_mode in _SINGLE_CHANNEL_MODES:
        return (rgb_to_grayscale(*rgb),)
    return rgb


def _get_color(color_mode: ColorMode, desc: Descriptor) -> tuple[float, ...]:
    r"""Return color tuple from descriptor.

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
        # ``H   `` is an angle in degrees, so the full turn is 360 and not 300
        # (#754).
        hue = float(color_desc[Key.Hue]) / 360.0
        # Not clamped, unlike the other classes. Hue is cyclic, so 400 deg
        # names a real angle and ``hsb_to_rgb`` wraps it; clamping would turn
        # it into 360. Saturation and brightness are clamped by ``hsb_to_rgb``
        # itself, which is total, so guarding them again here would defend the
        # same two numbers twice (#757).
        saturation = float(color_desc[Key.Saturation]) / 100.0
        brightness = float(color_desc[Key.Brightness]) / 100.0
        return _from_rgb(color_mode, hsb_to_rgb(hue, saturation, brightness))

    def _get_gray(color_mode: ColorMode, x: Descriptor) -> tuple[float, ...]:
        # ``Gry `` is percent *black*, so 0 is white. Inverting it yields a
        # luminance, which is what every helper below takes -- a real
        # conversion, not the canvas-convention flip that ``_ink_to_canvas()``
        # performs.
        gray = _clamp01((100.0 - float(x[Key.Gray])) / 100.0)
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
        # Read as ink -- 0.0 is no ink -- which is both the descriptor's own
        # spelling and ``color_convert``'s documented contract. The compositor's
        # arrays store what is *left*, so only the CMYK branch flips, and it
        # says so by name (#747, #763).
        ink = tuple(
            _clamp01(float(x[key]) / 100.0)
            for key in (Key.Cyan, Key.Magenta, Key.Yellow, Key.Black)
        )
        if color_mode == ColorMode.CMYK:
            return _ink_to_canvas(ink)
        return _from_rgb(color_mode, cmyk_to_rgb(*ink))

    def _get_lab(color_mode: ColorMode, x: Descriptor) -> tuple[float, ...]:
        lightness = float(x[Key.Luminance])
        a = float(x[Key.A])
        b = float(x[Key.B])
        if color_mode == ColorMode.LAB:
            # Straight into the array's own encoding, with no trip through RGB
            # to lose anything on (#743).
            return _lab_to_canvas(lightness, a, b)
        # Everything else is a real conversion, through sRGB: the chroma axes
        # are signed, so neither the raw triple nor ``L`` alone stands in for
        # the colour (the second half of #743).
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
        raise _UnreadableDescriptor(f"Could not find a color descriptor {desc}")
    if (read := _COLOR_FUNC.get(color_desc.classID)) is None:
        raise _UnreadableDescriptor(f"Unknown color class {color_desc.classID!r}")
    return read(color_mode, color_desc)


def create_fill_desc(
    layer: "Layer",
    desc: Descriptor,
    viewport: tuple[int, int, int, int],
    anchor: tuple[int, int, int, int] | None = None,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Create a fill image, laid out on ``anchor`` and drawn on ``viewport``."""
    if desc.classID == b"solidColorLayer":
        return draw_solid_color_fill(viewport, layer._psd.color_mode, desc)
    if desc.classID == b"patternLayer":
        return draw_pattern_fill(viewport, layer._psd, desc, anchor)
    if desc.classID == b"gradientLayer":
        _check_gradient_size(layer, viewport)
        return draw_gradient_fill(viewport, layer._psd.color_mode, desc, anchor)
    return None, None


def _check_gradient_size(layer: "Layer", viewport: tuple[int, int, int, int]) -> None:
    """Raise :class:`ValueError` when a gradient drawn on ``viewport`` is over budget."""
    width, height = viewport[2] - viewport[0], viewport[3] - viewport[1]
    # An empty axis still builds a ramp along the other, so that one is bounded.
    if width < 1 or height < 1:
        width, height = max(width, height, 0), 1
        if width < 1:
            return
    check_pixel_size(
        width,
        height,
        max_alloc_bytes=layer._psd._max_alloc_bytes,
        estimated_bytes=width * height * GRADIENT_FILL_BYTES,
        warn=False,
        max_dimension=dimension_limit(layer._psd.version),
    )


def create_fill(
    layer: "Layer",
    viewport: tuple[int, int, int, int],
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Create a fill image."""
    if is_fill_disabled(layer):
        return None, None
    blocks = layer.tagged_blocks
    if (desc := blocks.get_data(Tag.SOLID_COLOR_SHEET_SETTING)) is not None:
        return draw_solid_color_fill(viewport, layer._psd.color_mode, desc)
    if (desc := blocks.get_data(Tag.PATTERN_FILL_SETTING)) is not None:
        return draw_pattern_fill(
            viewport, layer._psd, desc, _pattern_anchor(layer, desc)
        )
    if (desc := blocks.get_data(Tag.GRADIENT_FILL_SETTING)) is not None:
        _check_gradient_size(layer, viewport)
        return draw_gradient_fill(viewport, layer._psd.color_mode, desc)
    if (desc := blocks.get_data(Tag.VECTOR_STROKE_CONTENT_DATA)) is not None:
        if Key.Color in desc:
            return draw_solid_color_fill(viewport, layer._psd.color_mode, desc)
        elif Enum.Pattern in desc:
            return draw_pattern_fill(
                viewport, layer._psd, desc, _pattern_anchor(layer, desc)
            )
        elif Key.Gradient in desc:
            _check_gradient_size(layer, viewport)
            return draw_gradient_fill(viewport, layer._psd.color_mode, desc)
    return None, None


def _pattern_anchor(
    layer: "Layer", desc: Descriptor
) -> tuple[float, float, float, float] | None:
    """Where the tiling starts, as a zero-size box; ``None`` leaves it to the viewport."""
    try:
        if bool(desc.get(b"Algn", True)):
            reference = layer.tagged_blocks.get_data(Tag.REFERENCE_POINT)
            if reference is None:
                return None
            x, y = float(reference[0]), float(reference[1])
        else:
            x = y = 0.0
        phase = desc.get(b"phase")
        if isinstance(phase, Descriptor):
            x += float(phase.get(b"Hrzn", 0.0))
            y += float(phase.get(b"Vrtc", 0.0))
    except (TypeError, ValueError, IndexError):
        return None
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    return x, y, x, y


def _sample_axis(
    src: np.ndarray, axis: int, origin: int, count: int, anchor: float, scale: float
) -> np.ndarray:
    """
    Sample ``src`` tiled along ``axis`` at ``scale``, for ``count`` pixels from ``origin``.

    The tiling starts at ``anchor``. Photoshop reads a pattern bilinearly above
    half size and averages the source span a pixel covers at or below it.
    """
    size = src.shape[axis]
    offset = origin - math.fmod(float(anchor), size * scale)
    at = np.mod((np.arange(count) + offset) / scale, size)
    shape = [1] * src.ndim
    shape[axis] = -1
    if scale > 0.5:
        first = np.floor(at)
        weight = (at - first).astype(np.float32).reshape(shape)
        index = first.astype(np.intp)
        low = np.take(src, index % size, axis=axis)
        high = np.take(src, (index + 1) % size, axis=axis)
        return low + (high - low) * weight

    cumulative = np.cumsum(src, axis=axis, dtype=np.float64)
    cumulative = np.concatenate(
        [np.zeros_like(np.take(cumulative, [0], axis=axis)), cumulative], axis=axis
    )
    total = np.take(cumulative, [size], axis=axis)

    def integral(x: np.ndarray) -> np.ndarray:
        whole = np.floor(x / size)
        index = np.minimum(np.floor(x - whole * size).astype(np.intp), size - 1)
        part = (x - whole * size - index).reshape(shape)
        low = np.take(cumulative, index, axis=axis)
        high = np.take(cumulative, index + 1, axis=axis)
        return whole.reshape(shape) * total + low + part * (high - low)

    span = 1.0 / scale
    return ((integral(at + span) - integral(at)) / span).astype(np.float32)


def _sample_peak_bytes(panel: np.ndarray, height: int, width: int) -> int:
    """What :py:func:`_sample_axis` holds at its peak over a ``height`` x ``width`` viewport."""
    channels = panel.shape[2]
    pass_pixels = min(panel.shape[0] * width, height * panel.shape[1])
    wide = np.dtype(np.float64).itemsize
    return (
        panel.nbytes
        + panel.size * wide * 2  # the cumulative sums and their padded copy
        + 7 * pass_pixels * channels * wide  # the first pass's integral() temporaries
        + height * width * channels * 4  # the output
        + 7 * height * width * channels * wide  # the second pass's own
        + 16 * (height + width) * wide  # the coordinates and indices along each axis
    )


def draw_solid_color_fill(
    viewport: tuple[int, int, int, int],
    color_mode: ColorMode,
    desc: Descriptor,
) -> tuple[np.ndarray, np.ndarray | None]:
    """Create a solid color fill."""
    fill = _get_color(color_mode, desc)
    height, width = viewport[3] - viewport[1], viewport[2] - viewport[0]
    color = np.full((height, width, len(fill)), fill, dtype=np.float32)
    return color, None


def draw_pattern_fill(
    viewport: tuple[int, int, int, int],
    psd: Any,
    desc: Descriptor,
    anchor: tuple[float, float, float, float] | None = None,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    r"""
    Create a pattern fill.

    The tiling starts at the top-left of ``anchor``, which defaults to
    ``viewport``, so a viewport larger than the anchor continues the same tiling.
    The anchor is rounded to whole pixels at 100% scale.

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
    pattern_id = desc[Enum.Pattern][Key.ID].value.rstrip("\x00")
    pattern = psd._get_pattern(pattern_id)
    if not pattern:
        logger.error("Pattern not found: %s", pattern_id)
        return None, None

    budget = getattr(psd, "_max_alloc_bytes", None)
    panel = numpy_io.get_pattern(pattern, budget)
    assert panel.shape[0] > 0

    height, width = viewport[3] - viewport[1], viewport[2] - viewport[0]
    scale = float(desc.get(Key.Scale, 100.0)) / 100.0
    if not math.isfinite(scale):
        raise _UnreadableDescriptor("Pattern scale is not finite.")
    # A pattern is never drawn smaller than a pixel a tile.
    scales = [max(scale, 1.0 / size) for size in panel.shape[:2]]
    if height <= 0 or width <= 0:
        pixels = np.zeros((max(height, 0), max(width, 0), panel.shape[2]), np.float32)
    else:
        # The limit is on the viewport; the sampling is sized from it, not from the scale.
        check_pixel_size(
            width,
            height,
            panel.shape[2],
            budget,
            estimated_bytes=_sample_peak_bytes(panel, height, width),
            warn=False,
            max_dimension=dimension_limit(psd.version),
        )
        anchor_x, anchor_y = (
            (viewport[0], viewport[1]) if anchor is None else (anchor[0], anchor[1])
        )
        if scale == 1.0:
            anchor_x, anchor_y = math.floor(anchor_x + 0.5), math.floor(anchor_y + 0.5)
        panel = panel.astype(np.float32, copy=False)
        if panel.shape[0] * width <= height * panel.shape[1]:
            horizontal = _sample_axis(panel, 1, viewport[0], width, anchor_x, scales[1])
            pixels = _sample_axis(
                horizontal, 0, viewport[1], height, anchor_y, scales[0]
            )
        else:
            vertical = _sample_axis(panel, 0, viewport[1], height, anchor_y, scales[0])
            pixels = _sample_axis(vertical, 1, viewport[0], width, anchor_x, scales[1])
    # Taken from the pattern's own slot layout rather than from its color mode.
    # A mode-keyed count is only ever right by coincidence -- when the mode's
    # constant happens to equal the width this pattern stored -- and
    # multichannel's is 64, the format's maximum, which no pattern can equal.
    # ``shape[2] > channels`` was therefore never true there, the alpha was
    # never split off, and the array reached the canvas one plane too wide and
    # was rejected as inconsistent with it (#741).
    channels = numpy_io.get_pattern_color_channels(pattern)
    if pixels.shape[2] > channels:
        return pixels[:, :, :channels], pixels[:, :, -1:]
    return pixels, None


def _vertical_overlay_geometry(
    layer: "Layer", desc: Descriptor
) -> tuple[float, float, bool] | None:
    """Integer endpoints for aligned RGB8 Classic or Smooth vertical overlays."""
    if (
        layer._psd.color_mode != ColorMode.RGB
        or layer._psd.depth != 8
        or layer.kind not in ("pixel", "shape")
        or desc.get(Key.Type).enum != Enum.Linear
        or desc.get(b"gs99") is None
        or desc[b"gs99"].enum not in (b"Gcls", b"Smoo")
        or not bool(desc.get(b"Algn", True))
        or bool(desc.get(b"Dthr", False))
    ):
        return None
    gradient = desc[Key.Gradient]
    smoothness = float(gradient.get(b"Intr", 4096))
    if (
        gradient[Type.GradientForm].enum != Enum.CustomStops
        or smoothness not in (0, 4096)
        or any(
            float(stop.get(Key.Midpoint, 50)) != 50
            for key in (Key.Colors, Key.Transparency)
            for stop in gradient.get(key, [])
        )
    ):
        return None
    angle = float(desc.get(Key.Angle, 0))
    if angle % 180 != 90:
        return None
    box = layer.bbox
    mask = layer.vector_mask
    if (
        layer.kind == "shape"
        and mask is not None
        and not mask.disabled
        and any(len(path) for path in mask.paths)
    ):
        sizes = (layer._psd.width, layer._psd.height) * 2
        bounds = tuple(
            value * size for value, size in zip(mask.bbox, sizes, strict=True)
        )
        # Vector coordinates are 8.24 fixed-point document fractions, so one
        # unit of error scales with the document dimension.
        if any(
            not math.isfinite(v) or abs(v - round(v)) > size / 2**24
            for v, size in zip(bounds, sizes, strict=True)
        ):
            return None
        left, top, right, bottom = (round(v) for v in bounds)
        box = left, top, right, bottom
    height = box[3] - box[1]
    scale = float(desc.get(Key.Scale, 100)) / 100
    offset = desc.get(b"Ofst", {})
    horizontal = float(offset.get(b"Hrzn", 0))
    vertical = float(offset.get(b"Vrtc", 0))
    # Smooth interpolation remains approximate; its geometry is verified only
    # without offsets. Keep Classic zero-smoothness offset support unchanged.
    if (desc[b"gs99"].enum != b"Gcls" or smoothness != 0) and (
        horizontal != 0 or vertical != 0
    ):
        return None
    length = height * scale
    start = height * (1 - scale) / 2 + height * vertical / 100
    # Fractional endpoints require Photoshop's separate quantization rules.
    if (
        box[2] <= box[0]
        or height <= 0
        or length <= 0
        or not math.isfinite(horizontal)
        or not start.is_integer()
        or not (start + length).is_integer()
    ):
        return None
    return box[1] + start, length, angle % 360 == 90


@require_scipy
def draw_gradient_overlay(
    layer: "Layer", desc: Descriptor
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Draw a gradient overlay without changing fill or stroke geometry."""
    _check_gradient_size(layer, layer.bbox)
    try:
        geometry = _vertical_overlay_geometry(layer, desc)
    except (AttributeError, KeyError, TypeError, ValueError):
        geometry = None
    if geometry is None:
        return draw_gradient_fill(layer.bbox, layer._psd.color_mode, desc)
    start, length, descending = geometry
    coordinates = np.arange(layer.top, layer.bottom, dtype=np.float64)
    ramp = np.clip((coordinates - start) / length, 0, 1)
    if descending != bool(desc.get(Key.Reverse, False)):
        ramp = 1 - ramp
    ramp = np.broadcast_to(ramp[:, None], (layer.height, layer.width))
    color, alpha = _make_gradient_color(layer._psd.color_mode, desc[Key.Gradient])
    return (
        color(ramp) if color is not None else None,
        alpha(ramp)[..., None] if alpha is not None else None,
    )


@require_scipy
def draw_gradient_fill(
    viewport: tuple[int, int, int, int],
    color_mode: ColorMode,
    desc: Descriptor,
    anchor: tuple[int, int, int, int] | None = None,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """
    Create a gradient fill image.

    The ramp is laid out across ``anchor``, which defaults to ``viewport``; a
    viewport larger than the anchor continues the ramp past its ends.

    Requires scipy for gradient color interpolation.
    """
    height, width = viewport[3] - viewport[1], viewport[2] - viewport[0]
    box = viewport if anchor is None else anchor
    # A path with no extent along an axis ramps as a single pixel there.
    box_height, box_width = max(box[3] - box[1], 1), max(box[2] - box[0], 1)

    angle = float(desc.get(Key.Angle, 0))
    scale = float(desc.get(Key.Scale, 100.0)) / 100.0
    ratio = angle % 90
    scale *= (90.0 - ratio) / 90.0 * box_width + (ratio / 90.0) * box_height
    X, Y = np.meshgrid(
        _ramp_axis(viewport[0] - box[0], width, box_width, scale),
        _ramp_axis(viewport[1] - box[1], height, box_height, scale),
    )

    gradient_kind = _enum_of(desc, Key.Type)
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
        logger.warning("Unknown gradient style: %s.", gradient_kind)
        Z = np.full((height, width), 0.5, dtype=np.float32)

    Z = np.maximum(0.0, np.minimum(1.0, Z))
    if bool(desc.get(Key.Reverse, False)):
        Z = 1.0 - Z

    G, Ga = _make_gradient_color(color_mode, desc.get(Key.Gradient))
    color = G(Z) if G is not None else None
    shape = np.expand_dims(Ga(Z), 2) if Ga is not None else None
    return color, shape


def _ramp_axis(start: int, count: int, extent: int, scale: float) -> np.ndarray:
    """``count`` ramp coordinates from pixel ``start``, ``extent`` pixels spanning -1 to 1."""
    step = 2.0 * extent / scale / (extent - 1) if extent > 1 else 0.0
    return (-extent / scale + (start + np.arange(count)) * step).astype(np.float32)


def _make_linear_gradient(X: np.ndarray, Y: np.ndarray, angle: float) -> np.ndarray:
    """Generate index map for linear gradients."""
    theta = np.radians(angle % 360)
    Z = 0.5 * (np.cos(theta) * X - np.sin(theta) * Y + 1)
    return Z


def _make_radial_gradient(X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """Generate index map for radial gradients."""
    Z = np.sqrt(np.power(X, 2) + np.power(Y, 2))
    return Z


def _make_angle_gradient(X: np.ndarray, Y: np.ndarray, angle: float) -> np.ndarray:
    """Generate index map for angle gradients."""
    Z = (((180 * np.arctan2(Y, X) / np.pi) + angle) % 360) / 360
    return Z


def _make_reflected_gradient(X: np.ndarray, Y: np.ndarray, angle: float) -> np.ndarray:
    """Generate index map for reflected gradients."""
    theta = np.radians(angle % 360)
    Z = np.abs(np.cos(theta) * X - np.sin(theta) * Y)
    return Z


def _make_diamond_gradient(X: np.ndarray, Y: np.ndarray, angle: float) -> np.ndarray:
    """Generate index map for diamond gradients."""
    theta = np.radians(angle % 360)
    Z = np.abs(np.cos(theta) * X - np.sin(theta) * Y) + np.abs(
        np.sin(theta) * X + np.cos(theta) * Y
    )
    return Z


def _enum_of(desc: Descriptor, key: bytes) -> bytes:
    """The enum value under *key*, or ``ValueError`` if it is absent or not an enum."""
    value = desc.get(key)
    if not hasattr(value, "enum"):
        raise _UnreadableDescriptor(f"Missing enum {key!r} in {desc.classID!r}")
    return value.enum


def _make_gradient_color(
    color_mode: ColorMode, grad: Descriptor
) -> tuple[Any | None, Any | None]:
    gradient_form = _enum_of(grad, Type.GradientForm)
    if gradient_form == Enum.ColorNoise:
        return _make_noise_gradient_color(color_mode, grad)
    elif gradient_form == Enum.CustomStops:
        return _make_linear_gradient_color(color_mode, grad)

    logger.error("Unknown gradient form: %s", gradient_form)
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
        raise _UnreadableDescriptor("Gradient has no stops.")
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
    r"""
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
    from scipy.ndimage import (  # type: ignore[import-untyped]  # noqa: PLC0415
        maximum_filter1d,
        uniform_filter1d,
    )

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
