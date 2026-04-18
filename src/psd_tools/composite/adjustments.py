import functools
import logging
from typing import Literal, Callable, TypeVar

import numpy as np
from numpy.typing import NDArray

from psd_tools.api.layers import Layer
from psd_tools.constants import ColorMode
from psd_tools.composite._compat import require_scipy
from psd_tools.composite.blend import _lum
from psd_tools.api.adjustments import (
    BrightnessContrast,
    Levels,
    Curves,
    Exposure,
    Invert,
    Posterize,
    Threshold,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable)


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
            assert out.shape[2] == color_channels
            return np.concatenate([out, alpha], axis=2)

        assert img.shape[2] == color_channels
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
    assert img.ndim == 3
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
    from scipy import interpolate  # type: ignore[import-untyped]

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
    x = np.array([0.0, 63.0, 191.0, 255.0]) / 255.0
    y = np.array([0.0, 63.0 - c * 25.0, 191.0 + c * 25.0, 255.0]) / 255.0
    contrast_spline = interpolate.CubicSpline(x, y, bc_type="natural")(t)

    # brightness
    a1, a2, a3, a4, a5 = 1.65, -1.0, 1.96, 1.0, 1.00
    r1, r2, r3, r4, r5 = 0.35, 10.0, 0.4, 4.0, 1.25

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
    from scipy import interpolate  # type: ignore[import-untyped]

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
    color_gamma = 1.75 if colormode == ColorMode.GRAYSCALE else 2.2

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
    "invert": apply_invert,
    "posterize": apply_posterize,
    "threshold": apply_threshold,
}
