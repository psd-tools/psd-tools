"""
Blend mode implementations.
"""
import numpy as np
import functools
from psd_tools.constants import BlendMode
from psd_tools.terminology import Enum
import logging

logger = logging.getLogger(__name__)


# Separable blend functions
def normal(Cb, Cs):
    return Cs


def multiply(Cb, Cs):
    return Cb * Cs


def screen(Cb, Cs):
    return Cb + Cs - (Cb * Cs)


def overlay(Cb, Cs):
    return hard_light(Cs, Cb)


def darken(Cb, Cs):
    return np.minimum(Cb, Cs)


def lighten(Cb, Cs):
    return np.maximum(Cb, Cs)


def color_dodge(Cb, Cs, s=1.0):
    B = np.zeros_like(Cb, dtype=np.float32)
    B[Cs == 1] = 1
    B[Cb == 0] = 0
    index = (Cs != 1) & (Cb != 0)
    B[index] = np.minimum(1, Cb[index] / (s * (1 - Cs[index])))
    return B


def color_burn(Cb, Cs, s=1.0):
    B = np.zeros_like(Cb, dtype=np.float32)
    B[Cb == 1] = 1
    index = (Cb != 1) & (Cs != 0)
    B[index] = 1 - np.minimum(1, (1 - Cb[index]) / (s * Cs[index]))
    return B


def linear_dodge(Cb, Cs):
    return np.minimum(1, Cb + Cs)


def linear_burn(Cb, Cs):
    return np.maximum(0, Cb + Cs - 1)


def hard_light(Cb, Cs):
    index = Cs > 0.5
    B = multiply(Cb, 2 * Cs)
    B[index] = screen(Cb, 2 * Cs - 1)[index]
    return B


def soft_light(Cb, Cs):
    index = Cs <= 0.25
    index_not = ~index
    D = np.zeros_like(Cb, dtype=np.float32)
    D[index] = ((16 * Cb[index] - 12) * Cb[index] + 4) * Cb[index]
    D[index_not] = np.sqrt(Cb[index_not])

    index = Cs <= 0.5
    index_not = ~index
    B = np.zeros_like(Cb, dtype=np.float32)
    B[index] = Cb[index] - (1 - 2 * Cs[index]) * Cb[index] * (1 - Cb[index])
    B[index_not] = Cb[index_not] + \
        (2 * Cs[index_not] - 1) * (D[index_not] - Cb[index_not])
    return B


def vivid_light(Cb, Cs):
    """
    Burns or dodges the colors by increasing or decreasing the contrast,
    depending on the blend color. If the blend color (light source) is lighter
    than 50% gray, the image is lightened by decreasing the contrast. If the
    blend color is darker than 50% gray, the image is darkened by increasing
    the contrast.
    """

    # index = Cs > 0.5
    # B = color_dodge(Cb, Cs)
    # B[index] = color_burn(Cb, Cs)[index]
    # return B

    # On contrary to what the document says, Photoshop generates the inverse of
    # hard_mix
    return hard_mix(Cs, Cb)


def linear_light(Cb, Cs):
    """
    Burns or dodges the colors by decreasing or increasing the brightness,
    depending on the blend color. If the blend color (light source) is lighter
    than 50% gray, the image is lightened by increasing the brightness. If the
    blend color is darker than 50% gray, the image is darkened by decreasing
    the brightness.
    """
    index = Cs > 0.5
    B = linear_burn(Cb, 2 * Cs)
    B[index] = linear_dodge(Cb, 2 * Cs - 1)[index]
    return B


def pin_light(Cb, Cs):
    """
    Replaces the colors, depending on the blend color. If the blend color
    (light source) is lighter than 50% gray, pixels darker than the blend color
    are replaced, and pixels lighter than the blend color do not change. If the
    blend color is darker than 50% gray, pixels lighter than the blend color
    are replaced, and pixels darker than the blend color do not change. This is
    useful for adding special effects to an image.
    """
    index = Cs > 0.5
    B = darken(Cb, 2 * Cs)
    B[index] = lighten(Cb, 2 * Cs - 1)[index]
    return B


def difference(Cb, Cs):
    return np.abs(Cb - Cs)


def exclusion(Cb, Cs):
    return Cb + Cs - 2 * Cb * Cs


def subtract(Cb, Cs):
    return np.maximum(0, Cb - Cs)


def hard_mix(Cb, Cs):
    """
    Adds the red, green and blue channel values of the blend color to the RGB
    values of the base color. If the resulting sum for a channel is 255 or
    greater, it receives a value of 255; if less than 255, a value of 0.
    Therefore, all blended pixels have red, green, and blue channel values of
    either 0 or 255. This changes all pixels to primary additive colors (red,
    green, or blue), white, or black.
    """
    B = np.zeros_like(Cb, dtype=np.float32)
    B[(Cb + .999999 * Cs) >= 1] = 1  # There seems a weird numerical issue.
    return B


def divide(Cb, Cs):
    """
    Looks at the color information in each channel and divides the blend color
    from the base color.
    """
    B = Cb / (Cs + 1e-6)
    B[B > 1] = 1
    return B


# Non-separable blending must be in RGB. CMYK should be first converted to RGB,
# blended, then CMY components should be retrieved from RGB results. K
# component is K of Cb for hue, saturation, and color blending, and K of Cs for
# luminosity.
def non_separable(k='s'):
    """Wrap non-separable blending function for CMYK handling.

    .. note: This implementation is still inaccurate.
    """
    def decorator(func):
        @functools.wraps(func)
        def _blend_fn(Cb, Cs):
            if Cs.shape[2] == 4:
                K = Cs[:, :, 3:4] if k == 's' else Cb[:, :, 3:4]
                Cb, Cs = _cmyk2rgb(Cb), _cmyk2rgb(Cs)
                return np.concatenate((_rgb2cmy(func(Cb, Cs), K), K), axis=2)
            return func(Cb, Cs)

        return _blend_fn

    return decorator


def _cmyk2rgb(C):
    return np.stack([(1. - C[:, :, i]) * (1. - C[:, :, 3]) for i in range(3)],
                    axis=2)


def _rgb2cmy(C, K):
    K = np.repeat(K, 3, axis=2)
    color = np.zeros((C.shape[0], C.shape[1], 3))
    index = K < 1.
    color[index] = (1. - C[index] - K[index]) / (1. - K[index])
    return color


@non_separable()
def hue(Cb, Cs):
    return _set_lum(_set_sat(Cs, _sat(Cb)), _lum(Cb))


@non_separable()
def saturation(Cb, Cs):
    return _set_lum(_set_sat(Cb, _sat(Cs)), _lum(Cb))


@non_separable()
def color(Cb, Cs):
    return _set_lum(Cs, _lum(Cb))


@non_separable('s')
def luminosity(Cb, Cs):
    return _set_lum(Cb, _lum(Cs))


@non_separable()
def darker_color(Cb, Cs):
    index = np.repeat(_lum(Cs) < _lum(Cb), 3, axis=2)
    B = Cb.copy()
    B[index] = Cs[index]
    return B


@non_separable()
def lighter_color(Cb, Cs):
    index = np.repeat(_lum(Cs) > _lum(Cb), 3, axis=2)
    B = Cb.copy()
    B[index] = Cs[index]
    return B


def dissolve(Cb, Cs):
    # TODO: Implement me!
    logger.debug('Dissolve blend is not implemented')
    return normal(Cb, Cs)


# Helper functions from PDF reference.
def _lum(C):
    return 0.3 * C[:, :, 0:1] + 0.59 * C[:, :, 1:2] + 0.11 * C[:, :, 2:3]


def _set_lum(C, l):
    d = l - _lum(C)
    return _clip_color(C + d)


def _clip_color(C):
    L = np.repeat(_lum(C), 3, axis=2)
    C_min = np.repeat(np.min(C, axis=2, keepdims=True), 3, axis=2)
    C_max = np.repeat(np.max(C, axis=2, keepdims=True), 3, axis=2)

    index = C_min < 0.
    L_i = L[index]
    C[index] = L_i + (C[index] - L_i) * L_i / (L_i - C_min[index])

    index = C_max > 1.
    L_i = L[index]
    C[index] = L_i + (C[index] - L_i) * (1 - L_i) / (C_max[index] - L_i)

    # For numerical stability.
    C[C < 0.] = 0
    C[C > 1] = 1
    return C


def _sat(C):
    return np.max(C, axis=2, keepdims=True) - np.min(C, axis=2, keepdims=True)


def _set_sat(C, s):
    s = np.repeat(s, 3, axis=2)

    C_max = np.repeat(np.max(C, axis=2, keepdims=True), 3, axis=2)
    C_mid = np.repeat(np.median(C, axis=2, keepdims=True), 3, axis=2)
    C_min = np.repeat(np.min(C, axis=2, keepdims=True), 3, axis=2)

    B = np.zeros_like(C, dtype=np.float32)

    index_diff = (C_max > C_min)
    index_mid = (C == C_mid)
    index_max = (C == C_max) & ~index_mid
    index_min = (C == C_min)

    index = index_mid & index_diff
    B[index] = C_mid[index] - C_min[index] * \
        s[index] / (C_max[index] - C_min[index])
    index = index_max & index_diff
    B[index] = s[index]

    B[~index_diff & index_mid] = 0
    B[~index_diff & index_max] = 0

    B[index_min] = 0

    return B


"""Blend function table."""
BLEND_FUNC = {
    # Layer attributes
    BlendMode.NORMAL: normal,
    BlendMode.MULTIPLY: multiply,
    BlendMode.SCREEN: screen,
    BlendMode.OVERLAY: overlay,
    BlendMode.DARKEN: darken,
    BlendMode.LIGHTEN: lighten,
    BlendMode.COLOR_DODGE: color_dodge,
    BlendMode.COLOR_BURN: color_burn,
    BlendMode.LINEAR_DODGE: linear_dodge,
    BlendMode.LINEAR_BURN: linear_burn,
    BlendMode.HARD_LIGHT: hard_light,
    BlendMode.SOFT_LIGHT: soft_light,
    BlendMode.VIVID_LIGHT: vivid_light,
    BlendMode.LINEAR_LIGHT: linear_light,
    BlendMode.PIN_LIGHT: pin_light,
    BlendMode.HARD_MIX: hard_mix,
    BlendMode.DIVIDE: divide,
    BlendMode.DIFFERENCE: difference,
    BlendMode.EXCLUSION: exclusion,
    BlendMode.SUBTRACT: subtract,
    BlendMode.HUE: hue,
    BlendMode.SATURATION: saturation,
    BlendMode.COLOR: color,
    BlendMode.LUMINOSITY: luminosity,
    BlendMode.DARKER_COLOR: darker_color,
    BlendMode.LIGHTER_COLOR: lighter_color,
    BlendMode.DISSOLVE: dissolve,
    # Descriptor keys
    Enum.Normal: normal,
    Enum.Multiply: multiply,
    Enum.Screen: screen,
    Enum.Overlay: overlay,
    Enum.Darken: darken,
    Enum.Lighten: lighten,
    Enum.ColorDodge: color_dodge,
    Enum.ColorBurn: color_burn,
    b'linearDodge': linear_dodge,
    b'linearBurn': linear_burn,
    Enum.HardLight: hard_light,
    Enum.SoftLight: soft_light,
    b'vividLight': vivid_light,
    b'linearLight': linear_light,
    b'pinLight': pin_light,
    b'hardMix': hard_mix,
    b'blendDivide': divide,
    Enum.Difference: difference,
    Enum.Exclusion: exclusion,
    Enum.Subtract: subtract,
    Enum.Hue: hue,
    Enum.Saturation: saturation,
    Enum.Color: color,
    Enum.Luminosity: luminosity,
    b'darkerColor': darker_color,
    b'ligherColor': lighter_color,
    Enum.Dissolve: dissolve,
}
