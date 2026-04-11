import logging
from typing import Literal
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


def _apply_luts(
    luts: dict[int, NDArray[np.float32]], 
    img: np.ndarray, 
    colormode: ColorMode
) -> np.ndarray:
    assert img.ndim == 3
    out = img.copy()
    n_channels = ColorMode.channels(colormode)
    channels = range(1, n_channels+1)

    # individual adjustments get applied independently of each other, then the master lut its applied if exists
    for channel_id in channels:
        if channel_id in luts:
            lut = luts[channel_id]
            out[:, :, channel_id-1] = _apply_lut(img[:, :, channel_id-1], lut)

    if not colormode == ColorMode.GRAYSCALE and 0 in luts:
        out = _apply_lut(out, luts[0])
  
    return out


def _apply_lut(values: np.ndarray, lut: np.ndarray) -> np.ndarray:
    lut_size = lut.shape[0]

    if lut_size <= 2**16:
        depth = lut_size
        values = (np.floor(values * depth) / depth).clip(0.0, 1.0)

    xp = np.linspace(0.0, 1.0, lut_size, dtype=np.float32)
    return np.interp(values, xp, lut).astype(np.float32)
    

def _get_lut_size(layer: Layer) -> Literal[256, 65536]:
    bits = layer._psd.depth
    lut_size = min(2**bits, 65536) 
    logger.debug(f"Lut size: {lut_size}")
    return lut_size 


def _get_luminance(
    img: np.ndarray, 
    colormode: Literal[ColorMode.CMYK, ColorMode.GRAYSCALE, ColorMode.RGB]
) -> np.ndarray:
    if colormode == ColorMode.RGB:
        return _lum(img)
    elif colormode == ColorMode.GRAYSCALE:
        return img[..., 0:1]
    else: # CMYK requires accurate luminance conversion
        return img 


@require_scipy
def apply_brightnesscontrast(
    img: np.ndarray,
    colormode: Literal[ColorMode.CMYK, ColorMode.GRAYSCALE, ColorMode.RGB],
    layer: BrightnessContrast, 
) -> np.ndarray:
    """
    Applies a brightness & contrast adjustment to an image.

    Requires scipy for cubic spline interpolation.
    """
    from scipy.interpolate import CubicSpline

    use_legacy: bool  = layer.use_legacy
    b: float = layer.brightness / 150.0 
    c: float   = layer.contrast / 100.0
        
    lut_size = _get_lut_size(layer)
    t = np.linspace(0, 1, lut_size, dtype=np.float32)
        
    if use_legacy: # these layers are skipped during composing as they are recognized as PixelLayers with no bounding box
        return img
    
    # TODO: improve brightness function accuracy
    # the non-legacy adjustment was determined using reverse engineering and tuning parameters, might be slightly off
    # check brightness curve: https://www.desmos.com/calculator/4fg6glxzqj
    
    # contrast 
    x = np.array([0.0, 63.0, 191.0, 255.0]) / 255.0
    y = np.array([0.0, 63.0 - c * 25.0, 191.0 + c * 25.0, 255.0]) / 255.0
    contrast_spline = CubicSpline(x, y, bc_type="natural")(t)

    # brightness 
    a1, a2, a3, a4, a5 = 1.65, -1.0, 1.96, 1.0, 1.00
    r1, r2, r3, r4, r5 = 0.35, 10.0, 0.4, 4.0, 1.25

    def pol(a,x,r): return a * np.power(x, r)

    h = 0.5 * (abs(b) * (pol(a1,t,r1) +  pol(a2,t,r2)) + (1-abs(b)) * (pol(a3,t,r3) +  pol(a4,t,r4)) + pol(a5,t,r5))
    brightness_spline = b * t * (1-t) * h

    # a parametric transformation rotates the brightness spline function 45° degrees
    x_rotated = t - brightness_spline
    y_rotated = contrast_spline + brightness_spline 

    lut = np.interp(t, x_rotated, y_rotated)
    lut = lut.clip(0.0, 1.0).astype(np.float32)

    channel_id = 1 if colormode == ColorMode.GRAYSCALE else 0

    return _apply_luts({channel_id: lut}, img, colormode)


def apply_levels(
    img: np.ndarray,
    colormode: Literal[ColorMode.CMYK, ColorMode.GRAYSCALE, ColorMode.RGB],
    layer: Levels, 
) -> np.ndarray:
    """Applies a levels adjustment to an image."""

    levels_data = layer.data
    lut_size = _get_lut_size(layer)

    luts: dict[int, NDArray[np.float32]] = {}

    for channel_id, channel_data in enumerate(levels_data):        
        in_black: float  = channel_data.input_floor / 255.0
        in_white: float  = channel_data.input_ceiling / 255.0
        gamma: float     = channel_data.gamma / 100.0
        out_black: float = channel_data.output_floor / 255.0
        out_white: float = channel_data.output_ceiling / 255.0

        t = np.linspace(0, 1, lut_size, dtype=np.float32)

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
def apply_curves(
    img: np.ndarray,
    colormode: Literal[ColorMode.CMYK, ColorMode.GRAYSCALE, ColorMode.RGB],
    layer: Curves, 
) -> np.ndarray:
    """
    Applies a curves adjustment to an image.

    Requires scipy for cubic spline interpolation.
    """
    from scipy.interpolate import CubicSpline

    curves_data = layer.extra
    info_dict = {data.channel_id: data.points for data in curves_data}

    lut_size = _get_lut_size(layer)

    luts: dict[int, NDArray[np.float32]] = {}

    for channel_id, points in info_dict.items():
        if len(points) < 2: continue
        
        x = np.array([p[1] for p in points]) / 255.0
        y = np.array([p[0] for p in points]) / 255.0

        cs = CubicSpline(x, y, bc_type="natural")
        
        x_min, x_max = x[0], x[-1]
        t = np.linspace(0.0, 1.0, lut_size, dtype=np.float32)
        t_clamped = np.clip(t, x_min, x_max)

        lut = cs(t_clamped).clip(0.0, 1.0).astype(np.float32)
        luts[channel_id] = lut

    return _apply_luts(luts, img, colormode)


def apply_exposure(
    img: np.ndarray, 
    colormode: Literal[ColorMode.CMYK, ColorMode.GRAYSCALE, ColorMode.RGB],
    layer: Exposure, 
) -> np.ndarray:
    """Applies an exposure adjustment to an image."""

    exposure: float = layer.exposure
    offset: float   = layer.exposure_offset
    gamma: float    = layer.gamma

    lut_size = _get_lut_size(layer)
    color_gamma = 1.8 if colormode == ColorMode.GRAYSCALE else 2.2
    values = np.linspace(0.0, 1.0, lut_size, dtype=np.float32)

    factor = np.pow(2.0, exposure/color_gamma)
    lut = (values * factor).clip(0.0, 1.0)

    lut = (np.power(lut, color_gamma) + offset).clip(0.0, 1.0)
    lut = np.power(lut, 1.0/(color_gamma * gamma))

    lut = lut.clip(0.0, 1.0).astype(np.float32)

    channel_id = 1 if colormode == ColorMode.GRAYSCALE else 0

    return _apply_luts({channel_id: lut}, img, colormode)


def apply_invert(
    img: np.ndarray, 
    colormode: Literal[ColorMode.CMYK, ColorMode.GRAYSCALE, ColorMode.RGB],
    layer: Invert, 
) -> np.ndarray:
    """Applies an invert adjustment to an image."""

    return 1.0 - img


def apply_posterize(
    img: np.ndarray, 
    colormode: Literal[ColorMode.CMYK, ColorMode.GRAYSCALE, ColorMode.RGB],
    layer: Posterize, 
) -> np.ndarray:

    lut_size = _get_lut_size(layer)
    levels = layer.posterize

    values = np.linspace(0.0, 1.0, lut_size, dtype=np.float32)

    lut = (np.floor(levels * values) / (levels-1)).astype(np.float32)
    channel_id = 1 if colormode == ColorMode.GRAYSCALE else 0

    return _apply_luts({channel_id: lut}, img, colormode)


def apply_threshold(
    img: np.ndarray, 
    colormode: Literal[ColorMode.CMYK, ColorMode.GRAYSCALE, ColorMode.RGB],
    layer: Threshold, 
) -> np.ndarray:
    # CMYK requires accurate luminance conversion
    if colormode == ColorMode.CMYK:
        logger.info("Threshold isn't currently supported for CMYK.")
        return img
    
    lut_size = _get_lut_size(layer) - 1 
    trunc_function = np.round if lut_size < 256 else np.floor
    threshold = (layer.threshold-0.01) / 255.0 * lut_size

    luminance = trunc_function(_get_luminance(img, colormode) * lut_size)
    filtered = (luminance > threshold).astype(np.float32) 

    if colormode == ColorMode.RGB:
        out = np.repeat(filtered, 3, axis=2)
        return out
    
    return filtered


"""Adjustment function table."""
ADJUSTMENT_FUNC = {
    "brightnesscontrast": apply_brightnesscontrast,
    "levels": apply_levels,
    "curves": apply_curves,
    "exposure": apply_exposure,
    "invert": apply_invert,
    "posterize": apply_posterize,
    "threshold": apply_threshold,
}