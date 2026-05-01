import functools
import logging
from typing import Literal, Callable, TypeVar, cast

import numpy as np
from numpy.typing import NDArray

from psd_tools.api.layers import Layer
from psd_tools.constants import ColorMode
from psd_tools.composite._compat import require_scipy
from psd_tools.composite.blend import _lum, rgb2hsl, hsl2rgb, hsl2hsv, hsv2hsl
from psd_tools.api.adjustments import (
    BrightnessContrast,
    Levels,
    Curves,
    Exposure,
    HueSaturation,
    Invert,
    Posterize,
    Threshold,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable)

# Contrast cubic spline control points (Photoshop empirical values, 0–255 scale).
# Inner midpoints move ±_CONTRAST_INNER_DELTA per unit of contrast.
_CONTRAST_CONTROL_X = np.array([0.0, 63.0, 191.0, 255.0]) / 255.0
_CONTRAST_INNER_DELTA = 25.0 / 255.0

# Brightness polynomial coefficients (reverse-engineered from Photoshop).
# See: https://www.desmos.com/calculator/4fg6glxzqj
_BRIGHTNESS_POLY_A: tuple[float, float, float, float, float] = (
    1.65,
    -1.0,
    1.96,
    1.0,
    1.00,
)
_BRIGHTNESS_POLY_R: tuple[float, float, float, float, float] = (
    0.35,
    10.0,
    0.4,
    4.0,
    1.25,
)

# ICC profile gamma approximations for the exposure adjustment.
# Dot Gray 20% (Photoshop default grayscale profile) ≈ 1.75.
# sRGB (simplified power-law approximation) ≈ 2.2.
_GRAY_COLOR_GAMMA: float = 1.75
_SRGB_COLOR_GAMMA: float = 2.2


# LUT of the f(x,y) function that blends two color range saturation vectors x, y to a new saturation vector
# Uses empirical values tested using the regular grid (-100, -90, ... , 90, 100)^2
# See: https://colab.research.google.com/drive/1CGU4kxaVgv01vAMdNKbdTlLAhhQeOEOy?usp=sharing
# fmt: off
_SATURATION_RANGE_INTERPOLATION_GRID = np.array([
    [100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100,100],
    [100, 94, 92, 91, 91, 90, 90, 90, 90, 90, 90, 89, 89, 89, 89, 89, 89, 89, 88, 88, 88],
    [100, 92, 89, 86, 84, 83, 82, 81, 81, 80, 80, 79, 79, 78, 78, 77, 77, 76, 76, 75, 74],
    [100, 91, 86, 82, 79, 77, 74, 73, 71, 70, 70, 68, 67, 66, 65, 64, 62, 61, 59, 58, 56],
    [100, 91, 84, 79, 75, 71, 68, 65, 63, 61, 60, 58, 56, 54, 52, 49, 47, 44, 41, 36, 32],
    [100, 90, 83, 77, 71, 66, 62, 59, 55, 52, 50, 47, 44, 41, 37, 33, 28, 22, 17,  9, -1],
    [100, 90, 82, 74, 68, 62, 57, 52, 47, 43, 40, 36, 31, 26, 21, 13,  5, -5,-15,-25,-35],
    [100, 90, 81, 73, 65, 59, 52, 46, 39, 35, 30, 24, 19, 11,  2, -8,-18,-28,-38,-48,-58],
    [100, 90, 81, 71, 63, 55, 47, 39, 33, 26, 20, 13,  4, -6,-16,-26,-36,-46,-56,-66,-76],
    [100, 90, 80, 70, 61, 52, 43, 35, 26, 17, 10,  1, -9,-19,-29,-39,-49,-59,-69,-79,-89],
    [100, 90, 80, 70, 60, 50, 40, 30, 20, 10,  0,-10,-20,-30,-40,-49,-60,-70,-80,-90,-100],
    [100, 89, 79, 68, 58, 47, 36, 24, 13,  1,-10,-19,-30,-40,-50,-60,-70,-79,-89,-99,-100],
    [100, 89, 79, 67, 56, 44, 31, 19,  4, -9,-20,-30,-40,-50,-60,-70,-79,-90,-99,-100,-100],
    [100, 89, 78, 66, 54, 41, 26, 11, -6,-19,-30,-40,-50,-59,-70,-79,-89,-99,-100,-100,-100],
    [100, 89, 78, 65, 52, 37, 21,  2,-16,-29,-40,-50,-60,-70,-79,-90,-99,-100,-100,-100,-100],
    [100, 89, 77, 64, 49, 33, 13, -8,-26,-39,-49,-60,-70,-79,-90,-99,-100,-100,-100,-100,-100],
    [100, 89, 77, 62, 47, 28,  5,-18,-36,-49,-60,-70,-79,-89,-99,-100,-100,-100,-100,-100,-100],
    [100, 89, 76, 61, 44, 22, -5,-28,-46,-59,-70,-79,-90,-99,-100,-100,-100,-100,-100,-100,-100],
    [100, 88, 76, 59, 41, 17,-15,-38,-56,-69,-80,-89,-99,-100,-100,-100,-100,-100,-100,-100,-100],
    [100, 88, 75, 58, 36,  9,-25,-48,-66,-79,-90,-99,-100,-100,-100,-100,-100,-100,-100,-100,-100],
    [100, 88, 74, 56, 32, -1,-35,-58,-76,-89,-100,-100,-100,-100,-100,-100,-100,-100,-100,-100,-100],
], dtype=np.float32)[::-1,::-1] / 100.0
# fmt: on


def _preserve_alpha(func: F) -> F:
    """
    Decorator to apply adjustments only on color channels, leaving the alpha channel intact.

    If `n_channels == color_channels + 1`, the last channel is assumed to be alpha.
    If `n_channels == color_channels`, it is assumed no alpha channel exists.
    In any other case, a value error is raised.

    Raises:
        ValueError: If the number of channels of the image doesn't align with the colormode attribute.
    """

    @functools.wraps(func)
    def wrapper(img: np.ndarray, colormode: ColorMode, *args, **kwargs):
        color_channels = ColorMode.channels(colormode)
        n_channels = img.shape[2]

        if not (n_channels == color_channels or n_channels == color_channels + 1):
            raise ValueError("Channel count does not match colormode.")

        if n_channels > color_channels:
            color = img[..., :color_channels]
            alpha = img[..., color_channels:]

            out = func(color, colormode, *args, **kwargs)
            if out.shape[2] != color_channels:
                raise ValueError(
                    f"Adjustment function returned {out.shape[2]} channels, "
                    f"expected {color_channels}."
                )
            return np.concatenate([out, alpha], axis=2)

        return func(img, colormode, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def _get_lut_size(layer: Layer) -> Literal[256, 65536]:
    bits = layer._psd.depth
    lut_size = min(2**bits, 65536)
    logger.debug(f"Lut size: {lut_size}")
    return lut_size


@functools.lru_cache(maxsize=2)
def _lut_domain(lut_size: int) -> np.ndarray:
    """
    Returns the normalized domain [0, 1] used for LUT interpolation,
    with `lut_size` evenly spaced samples. Cached per size.
    """
    return np.linspace(0.0, 1.0, lut_size, dtype=np.float32)


def _apply_luts(
    luts: dict[int, NDArray[np.float32]], img: np.ndarray, colormode: ColorMode
) -> np.ndarray:
    if img.ndim != 3:
        raise ValueError(f"Expected 3D array (H, W, C), got ndim={img.ndim}.")
    out = img.copy()
    n_channels = ColorMode.channels(colormode)
    channels = range(1, n_channels + 1)

    # individual adjustments get applied independently of each other, then the master lut its applied if exists
    for channel_id in channels:
        if channel_id in luts:
            lut = luts[channel_id]
            out[:, :, channel_id - 1] = _apply_lut(img[:, :, channel_id - 1], lut)

    if colormode != ColorMode.GRAYSCALE and 0 in luts:
        out = _apply_lut(out, luts[0])

    return out


def _apply_lut(values: np.ndarray, lut: np.ndarray) -> np.ndarray:
    lut_size = lut.shape[0]

    if lut_size <= 2**16:
        depth = lut_size - 1
        values = (np.floor(values * depth) / depth).clip(0.0, 1.0)

    xp = _lut_domain(lut_size)
    return np.interp(values, xp, lut).astype(np.float32)


def _get_luminance(
    img: np.ndarray,
    colormode: Literal[ColorMode.CMYK, ColorMode.GRAYSCALE, ColorMode.RGB],
) -> np.ndarray:
    if colormode == ColorMode.RGB:
        return _lum(img)
    elif colormode == ColorMode.GRAYSCALE:
        return img[..., 0:1]
    else:  # CMYK requires accurate luminance conversion
        return img


@require_scipy
@_preserve_alpha
def apply_brightnesscontrast(
    img: np.ndarray,
    colormode: Literal[ColorMode.CMYK, ColorMode.GRAYSCALE, ColorMode.RGB],
    layer: BrightnessContrast,
) -> np.ndarray:
    """
    Applies a brightness & contrast adjustment to an image.

    Requires scipy for cubic spline interpolation.
    """
    from scipy import interpolate  # type: ignore[import-untyped]  # noqa: PLC0415

    use_legacy: bool = layer.use_legacy
    b: float = layer.brightness / 150.0
    c: float = layer.contrast / 100.0

    lut_size = _get_lut_size(layer)
    t = _lut_domain(lut_size)

    if use_legacy:  # these layers are skipped during composing as they are recognized as PixelLayers with no bounding box
        return img

    # TODO: improve brightness function accuracy
    # the non-legacy adjustment was determined using reverse engineering and tuning parameters, it can be improved
    # check brightness curve: https://www.desmos.com/calculator/4fg6glxzqj

    # contrast
    x = _CONTRAST_CONTROL_X
    y = np.array(
        [0.0, x[1] - c * _CONTRAST_INNER_DELTA, x[2] + c * _CONTRAST_INNER_DELTA, 1.0]
    )
    contrast_spline = interpolate.CubicSpline(x, y, bc_type="natural")(t)

    # brightness
    a1, a2, a3, a4, a5 = _BRIGHTNESS_POLY_A
    r1, r2, r3, r4, r5 = _BRIGHTNESS_POLY_R

    def pol(a, x, r):
        return a * np.power(x, r)

    h = 0.5 * (
        abs(b) * (pol(a1, t, r1) + pol(a2, t, r2))
        + (1 - abs(b)) * (pol(a3, t, r3) + pol(a4, t, r4))
        + pol(a5, t, r5)
    )
    brightness_spline = b * t * (1 - t) * h

    # a parametric transformation rotates the brightness spline function 45° degrees
    x_rotated = t - brightness_spline
    y_rotated = contrast_spline + brightness_spline

    lut = np.interp(t, x_rotated, y_rotated)
    lut = lut.clip(0.0, 1.0).astype(np.float32)

    channel_id = 1 if colormode == ColorMode.GRAYSCALE else 0

    return _apply_luts({channel_id: lut}, img, colormode)


@_preserve_alpha
def apply_levels(
    img: np.ndarray,
    colormode: Literal[ColorMode.CMYK, ColorMode.GRAYSCALE, ColorMode.RGB],
    layer: Levels,
) -> np.ndarray:
    """Applies a levels adjustment to an image."""

    levels_data = layer.data

    lut_size = _get_lut_size(layer)
    t = _lut_domain(lut_size)

    luts: dict[int, NDArray[np.float32]] = {}

    for channel_id, channel_data in enumerate(levels_data):
        in_black: float = channel_data.input_floor / 255.0
        in_white: float = channel_data.input_ceiling / 255.0
        gamma: float = channel_data.gamma / 100.0
        out_black: float = channel_data.output_floor / 255.0
        out_white: float = channel_data.output_ceiling / 255.0

        # input adjustments
        scale = (in_white - in_black) if in_white != in_black else 1.0
        out = (t - in_black) / scale
        out = out.clip(0.0, 1.0)

        # gamma midtone adjustment
        out = np.power(out, 1.0 / gamma)
        out = out.clip(0.0, 1.0)

        # output adjustments
        out = out * (out_white - out_black) + out_black
        lut = out.clip(0.0, 1.0).astype(np.float32)

        luts[channel_id] = lut

    return _apply_luts(luts, img, colormode)


@require_scipy
@_preserve_alpha
def apply_curves(
    img: np.ndarray,
    colormode: Literal[ColorMode.CMYK, ColorMode.GRAYSCALE, ColorMode.RGB],
    layer: Curves,
) -> np.ndarray:
    """
    Applies a curves adjustment to an image.

    Requires scipy for cubic spline interpolation.
    """
    from scipy import interpolate  # type: ignore[import-untyped]  # noqa: PLC0415

    curves_data = layer.extra
    info_dict = {data.channel_id: data.points for data in curves_data}

    lut_size = _get_lut_size(layer)
    t = _lut_domain(lut_size)

    luts: dict[int, NDArray[np.float32]] = {}

    for channel_id, points in info_dict.items():
        if len(points) < 2:
            continue

        x = np.array([p[1] for p in points]) / 255.0
        y = np.array([p[0] for p in points]) / 255.0

        cs = interpolate.CubicSpline(x, y, bc_type="natural")

        x_min, x_max = x[0], x[-1]
        t_clamped = np.clip(t, x_min, x_max)

        lut = cs(t_clamped).clip(0.0, 1.0).astype(np.float32)
        luts[channel_id] = lut

    return _apply_luts(luts, img, colormode)


@_preserve_alpha
def apply_exposure(
    img: np.ndarray,
    colormode: Literal[ColorMode.CMYK, ColorMode.GRAYSCALE, ColorMode.RGB],
    layer: Exposure,
) -> np.ndarray:
    """Applies an exposure adjustment to an image."""
    if colormode == ColorMode.CMYK:
        logger.info("Exposure doesn't support CMYK in Photoshop.")
        return img

    exposure: float = layer.exposure
    offset: float = layer.exposure_offset
    gamma: float = layer.gamma

    lut_size = _get_lut_size(layer)
    values = _lut_domain(lut_size)

    # color_gamma approximates the TRC of the ICC profile used.
    # Defaults to 2.2 for sRGB (RGB) and 1.75 for Dot Gray 20% (grayscale).
    # TODO: generalize for all ICC profiles.
    color_gamma = (
        _GRAY_COLOR_GAMMA if colormode == ColorMode.GRAYSCALE else _SRGB_COLOR_GAMMA
    )

    lut = np.power(
        values, color_gamma
    )  # image is converted to linear color space first

    # exposure operates in linear space
    lut *= np.exp2(exposure)
    lut = (lut + offset).clip(0.0, 1.0)
    lut **= 1.0 / gamma

    lut **= (
        1.0 / color_gamma
    )  # convert back to original space using inverse TRC approximation
    lut = lut.clip(0.0, 1.0).astype(np.float32)

    channel_id = 1 if colormode == ColorMode.GRAYSCALE else 0

    return _apply_luts({channel_id: lut}, img, colormode)


@require_scipy
@_preserve_alpha
def apply_huesaturation(
    img: np.ndarray,
    colormode: Literal[ColorMode.CMYK, ColorMode.GRAYSCALE, ColorMode.RGB],
    layer: HueSaturation,
) -> np.ndarray:
    """Applies a hue/saturation adjustment to an image."""
    if colormode == ColorMode.GRAYSCALE:
        logger.info("Hue/Saturation doesn't support grayscale in Photoshop.")
        return img

    # CMYK requires accurate luminance conversion
    if colormode == ColorMode.CMYK:
        logger.info("Hue/Saturation isn't currently supported for CMYK.")
        return img

    if layer.enable_colorization:
        hsl_colorize_tuple = _normalize_hsl(layer.colorization)
        return (
            _huesaturation_colorize(img, hsl_colorize_tuple)
            if hsl_colorize_tuple != (0.0, 0.0, 0.0)
            else img
        )

    color_ranges = [
        (hue_range, _normalize_hsl(hsl_tuple))
        for hue_range, hsl_tuple in layer.data
        if hsl_tuple != (0, 0, 0)
    ]
    hsl_master_tuple = _normalize_hsl(layer.master)
    return (
        _huesaturation(img, color_ranges, hsl_master_tuple)
        if color_ranges or hsl_master_tuple != (0.0, 0.0, 0.0)
        else img
    )


def _normalize_hsl(color: tuple[int, int, int]) -> tuple[float, float, float]:
    hue, saturation, lightness = color
    return (hue / 360.0), saturation / 100.0, lightness / 100.0


def _huesaturation_colorize(
    img: np.ndarray, hsl_colorize_tuple: tuple[float, float, float]
) -> np.ndarray:
    hue, saturation, lightness = hsl_colorize_tuple
    hue = hue % 1.0

    hsl = rgb2hsl(img)

    hsl[..., 0:1] = hue
    hsl[..., 1:2] = saturation
    hsl[..., 2:3] = _apply_lightness(hsl[..., 2:3], lightness)

    return hsl2rgb(hsl)


def _huesaturation(
    img: np.ndarray,
    color_ranges: list[tuple[tuple[int, int, int, int], tuple[float, float, float]]],
    master_tuple: tuple[float, float, float],
) -> np.ndarray:
    # master lightness is applied before converting to hsl
    master_hue, master_saturation, master_lightness = master_tuple
    img = _apply_lightness(img, master_lightness)

    hsl = rgb2hsl(img)
    colorrange_hue, colorrange_saturation, colorrange_lightness = (
        _get_colorrange_hsl_values(hsl, color_ranges)
    )

    # color range lightness is applied in HSV space
    hsl = hsl2hsv(hsl)
    saturation_channel, value_channel = hsl[..., 1:2], hsl[..., 2:3]

    hsl[..., 2:3] = np.where(
        colorrange_lightness >= 0,
        value_channel,
        value_channel * (1 + colorrange_lightness * saturation_channel),
    ).clip(0.0, 1.0)
    hsl[..., 1:2] = _correct_saturation(colorrange_lightness, saturation_channel)

    # hue and saturation are applied in HSL space
    # master and color range hues are applied simultaneously
    # master saturation is applied first, then color range saturation follows
    hsl = hsv2hsl(hsl)
    hsl[..., 0:1] = (hsl[..., 0:1] + colorrange_hue + master_hue) % 1.0
    hsl[..., 1:2] = _apply_saturation(
        _apply_saturation(hsl[..., 1:2], master_saturation), colorrange_saturation
    )

    return hsl2rgb(hsl)


def _apply_lightness(img: np.ndarray, lightness: float) -> np.ndarray:
    if lightness > 0:
        return (img * (1.0 - lightness) + lightness).clip(0.0, 1.0)
    if lightness < 0:
        return (img * (1.0 + lightness)).clip(0.0, 1.0)
    return img


# TODO: improve saturation algorithm accuracy when saturation nears 1.0
def _apply_saturation(img: np.ndarray, saturation: float | np.ndarray) -> np.ndarray:
    out = np.where(
        saturation > 0,
        img / (1 - saturation + 1e-2),
        img * (1 + saturation),
    )
    np.clip(out, 0.0, 1.0, out=out)
    return out


def _correct_saturation(
    colorrange_lightness: np.ndarray, saturation_channel: np.ndarray
) -> np.ndarray:
    """Correct saturation values when colorrange lightness is applied to the hsl image."""
    div = 1 / (saturation_channel + 1e-3)
    out = np.where(
        colorrange_lightness >= 0,
        saturation_channel * (1 - colorrange_lightness),
        1 + (div - 1) / (np.abs(colorrange_lightness) - div + 1e-3),
    )
    np.clip(out, 0.0, 1.0, out=out)
    return out


# TODO: find exact mapping to avoid interpolation
@functools.lru_cache(maxsize=1)
def _get_huesaturation_interpolator():
    from scipy.interpolate import RegularGridInterpolator  # type: ignore[import-untyped]  # noqa: PLC0415

    axis = np.linspace(-1.0, 1.0, 21)
    return RegularGridInterpolator(
        (axis, axis),
        _SATURATION_RANGE_INTERPOLATION_GRID,
        method="linear",
    )


def _get_colorrange_hsl_values(
    hsl_img: np.ndarray,
    color_ranges: list[tuple[tuple[int, int, int, int], tuple[float, float, float]]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute per-pixel hue, saturation, and lightness values derived from color ranges."""
    base_hue = hsl_img[..., 0:1]

    colorrange_hue = np.zeros_like(base_hue)
    colorrange_saturation = np.zeros_like(base_hue)
    colorrange_lightness = np.zeros_like(base_hue)

    interpolator = _get_huesaturation_interpolator()
    points = np.empty(
        (*colorrange_saturation.shape, 2), dtype=colorrange_saturation.dtype
    )

    # construction of the hue, saturation and lightness color range vectors depends on loop order
    for color_range_tuple, (hue, saturation, lightness) in color_ranges:
        range_mask = _get_huesaturation_range_mask(base_hue, color_range_tuple)

        colorrange_hue += hue * range_mask
        colorrange_lightness += lightness * range_mask
        np.clip(colorrange_lightness, -1.0, 1.0, out=colorrange_lightness)

        saturation_contribution = saturation * (
            (1 - (1 - range_mask) ** (1.5 / (1 - saturation**4 + 5e-2)))
            if saturation > 0
            else range_mask
        )
        # saturation values get mapped using a 3D surface
        points[..., 0] = colorrange_saturation
        points[..., 1] = saturation_contribution
        colorrange_saturation = interpolator(points.clip(-1.0, 1.0))

    return colorrange_hue, colorrange_saturation, colorrange_lightness


def _get_huesaturation_range_mask(
    hue: np.ndarray, color_range: tuple[int, int, int, int]
) -> np.ndarray:
    """
    Compute a trapezoidal hue mask for a Hue/Saturation adjustment.

    The range is defined by four hue control points (in degrees):
    BL (bottom-left), TL (top-left), TR (top-right), BR (bottom-right).

    The resulting mask:
    - is 0.0 outside [BL, BR]
    - rises linearly from 0.0->1.0 in [BL, TL]
    - is flat (1.0) in [TL, TR]
    - falls linearly from 1.0->0.0 in [TR, BR]
    """
    BL, TL, TR, BR = cast(
        tuple[float, float, float, float], np.array(color_range) / 360.0
    )

    # hue is treated circularly (mod 360)
    centered_hue = (hue - BL) % 1.0
    left_supp = (TL - BL) % 1.0
    center_supp = (TR - BL) % 1.0
    right_supp = (BR - BL) % 1.0

    # values are 0.0 outside the trapezoid support
    mask = np.zeros_like(centered_hue)

    center = (centered_hue >= left_supp) & (centered_hue <= center_supp)
    mask[center] = 1.0

    left = (centered_hue >= 0.0) & (centered_hue < left_supp)
    mask[left] = np.divide(
        centered_hue[left],
        left_supp,
        out=np.zeros_like(centered_hue[left]),
        where=left_supp > 1e-9,
    )

    right = (centered_hue > center_supp) & (centered_hue <= right_supp)
    mask[right] = np.divide(
        right_supp - centered_hue[right],
        right_supp - center_supp,
        out=np.zeros_like(centered_hue[right]),
        where=(right_supp - center_supp) > 1e-9,
    )

    return mask


@_preserve_alpha
def apply_invert(
    img: np.ndarray,
    colormode: Literal[ColorMode.CMYK, ColorMode.GRAYSCALE, ColorMode.RGB],
    layer: Invert,
) -> np.ndarray:
    """Applies an invert adjustment to an image."""

    return 1.0 - img


@_preserve_alpha
def apply_posterize(
    img: np.ndarray,
    colormode: Literal[ColorMode.CMYK, ColorMode.GRAYSCALE, ColorMode.RGB],
    layer: Posterize,
) -> np.ndarray:
    """Applies a posterize adjustment to an image."""

    lut_size = _get_lut_size(layer)
    # layer.posterize is a 1–255 integer from the PSD spec. The [2, 255] clamp is
    # intentional: PS minimum is 2. This range is correct for both 8-bit and 16-bit
    # because correction_factor below compensates for bit depth — the level count
    # itself does not change with bit depth. Do not widen the upper bound.
    levels = max(2, min(layer.posterize, 255))
    correction_factor = (
        (lut_size - 1) / lut_size
    )  # including this factor makes the output more accurate, on 8 bits and 16 bits

    out = np.floor(correction_factor * img * (levels)) / (levels - 1)
    return out.clip(0.0, 1.0).astype(np.float32)


@_preserve_alpha
def apply_threshold(
    img: np.ndarray,
    colormode: Literal[ColorMode.CMYK, ColorMode.GRAYSCALE, ColorMode.RGB],
    layer: Threshold,
) -> np.ndarray:
    """Applies a threshold adjustment to an image."""

    # CMYK requires accurate luminance conversion
    if colormode == ColorMode.CMYK:
        logger.info("Threshold isn't currently supported for CMYK.")
        return img

    lut_size = _get_lut_size(layer)

    correction_factor = (lut_size - 1) / lut_size
    bit_factor = (lut_size - 1) / 255  # constant used to compensate values on 16 bits
    bit_offset = 1 / 255  # offset used to compensate values on 16 bits
    threshold = (layer.threshold - bit_offset) * correction_factor * bit_factor

    luminance = np.round(_get_luminance(img, colormode) * (lut_size - 1))
    filtered = (luminance > threshold).astype(np.float32)

    if colormode == ColorMode.RGB:
        out = np.repeat(filtered, 3, axis=2)
        return out

    return filtered


"""Adjustment function table."""
AdjustmentFn = Callable[..., np.ndarray]
ADJUSTMENT_FUNC: dict[str, AdjustmentFn] = {
    "brightnesscontrast": apply_brightnesscontrast,
    "levels": apply_levels,
    "curves": apply_curves,
    "exposure": apply_exposure,
    "huesaturation": apply_huesaturation,
    "invert": apply_invert,
    "posterize": apply_posterize,
    "threshold": apply_threshold,
}
