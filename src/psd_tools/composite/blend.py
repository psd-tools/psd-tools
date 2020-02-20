"""
Blend mode implementations.
"""
import numpy as np
from psd_tools.constants import BlendMode
from psd_tools.terminology import Enum
import logging

logger = logging.getLogger(__name__)


# Blend functions
def _normal(Cb, Cs):
    return Cs


def _multiply(Cb, Cs):
    return Cb * Cs


def _screen(Cb, Cs):
    return Cb + Cs - (Cb * Cs)


def _overlay(Cb, Cs):
    return _hard_light(Cs, Cb)


def _darken(Cb, Cs):
    return np.minimum(Cb, Cs)


def _lighten(Cb, Cs):
    return np.maximum(Cb, Cs)


def _color_dodge(Cb, Cs, s=1.0):
    B = np.zeros_like(Cs)
    B[Cs == 1] = 1
    B[Cb == 0] = 0
    index = (Cs != 1) & (Cb != 0)
    B[index] = np.minimum(1, Cb[index] / (s * (1 - Cs[index])))
    return B


def _color_burn(Cb, Cs, s=1.0):
    B = np.zeros_like(Cb)
    B[Cb == 1] = 1
    index = (Cb != 1) & (Cs != 0)
    B[index] = 1 - np.minimum(1, (1 - Cb[index]) / (s * Cs[index]))
    return B


def _linear_dodge(Cb, Cs):
    return np.minimum(1, Cb + Cs)


def _linear_burn(Cb, Cs):
    return np.maximum(0, Cb + Cs - 1)


def _hard_light(Cb, Cs):
    index = Cs > 0.5
    B = _multiply(Cb, 2 * Cs)
    B[index] = _screen(Cb, 2 * Cs - 1)[index]
    return B


def _soft_light(Cb, Cs):
    index = Cs <= 0.25
    index_not = ~index
    D = np.zeros_like(Cb)
    D[index] = ((16 * Cb[index] - 12) * Cb[index] + 4) * Cb[index]
    D[index_not] = np.sqrt(Cb[index_not])

    index = Cs <= 0.5
    index_not = ~index
    B = np.zeros_like(Cb)
    B[index] = Cb[index] - (1 - 2 * Cs[index]) * Cb[index] * (1 - Cb[index])
    B[index_not] = Cb[index_not] + \
        (2 * Cs[index_not] - 1) * (D[index_not] - Cb[index_not])
    return B


def _vivid_light(Cb, Cs):
    """
    Burns or dodges the colors by increasing or decreasing the contrast,
    depending on the blend color. If the blend color (light source) is lighter
    than 50% gray, the image is lightened by decreasing the contrast. If the
    blend color is darker than 50% gray, the image is darkened by increasing
    the contrast.
    """

    # index = Cs > 0.5
    # B = _color_dodge(Cb, Cs)
    # B[index] = _color_burn(Cb, Cs)[index]
    # return B

    # On contrary to what the document says, Photoshop generates the inverse of
    # _hard_mix
    return _hard_mix(Cs, Cb)


def _linear_light(Cb, Cs):
    """
    Burns or dodges the colors by decreasing or increasing the brightness,
    depending on the blend color. If the blend color (light source) is lighter
    than 50% gray, the image is lightened by increasing the brightness. If the
    blend color is darker than 50% gray, the image is darkened by decreasing the
    brightness.
    """
    index = Cs > 0.5
    B = _linear_burn(Cb, 2 * Cs)
    B[index] = _linear_dodge(Cb, 2 * Cs - 1)[index]
    return B


def _pin_light(Cb, Cs):
    """
    Replaces the colors, depending on the blend color. If the blend color (light
    source) is lighter than 50% gray, pixels darker than the blend color are
    replaced, and pixels lighter than the blend color do not change. If the
    blend color is darker than 50% gray, pixels lighter than the blend color are
    replaced, and pixels darker than the blend color do not change. This is
    useful for adding special effects to an image.
    """
    index = Cs > 0.5
    B = _darken(Cb, 2 * Cs)
    B[index] = _lighten(Cb, 2 * Cs - 1)[index]
    return B


def _difference(Cb, Cs):
    return np.abs(Cb - Cs)


def _exclusion(Cb, Cs):
    return Cb + Cs - 2 * Cb * Cs


def _subtract(Cb, Cs):
    return np.maximum(0, Cb - Cs)


def _hard_mix(Cb, Cs):
    """
    Adds the red, green and blue channel values of the blend color to the RGB
    values of the base color. If the resulting sum for a channel is 255 or
    greater, it receives a value of 255; if less than 255, a value of 0.
    Therefore, all blended pixels have red, green, and blue channel values of
    either 0 or 255. This changes all pixels to primary additive colors (red,
    green, or blue), white, or black.
    """
    B = np.zeros_like(Cb)
    B[(Cb + .999999 * Cs) >= 1] = 1  # There seems a weird numerical issue.
    return B


def _divide(Cb, Cs):
    """
    Looks at the color information in each channel and divides the blend color
    from the base color.
    """
    B = Cb / (Cs + 1e-6)
    B[B > 1] = 1
    return B


def _hue(Cb, Cs):
    return _set_lum(_set_sat(Cs, _sat(Cb)), _lum(Cb))


def _saturation(Cb, Cs):
    return _set_lum(_set_sat(Cb, _sat(Cs)), _lum(Cb))


def _color(Cb, Cs):
    return _set_lum(Cs, _lum(Cb))


def _luminosity(Cb, Cs):
    return _set_lum(Cb, _lum(Cs))


def _darker_color(Cb, Cs):
    index = np.repeat(_lum(Cs) < _lum(Cb), 3, axis=2)
    B = Cb.copy()
    B[index] = Cs[index]
    return B


def _lighter_color(Cb, Cs):
    index = np.repeat(_lum(Cs) > _lum(Cb), 3, axis=2)
    B = Cb.copy()
    B[index] = Cs[index]
    return B


def _dissolve(Cb, Cs):
    # TODO: Implement me!
    logger.debug('Dissolve blend is not implemented')
    return _normal(Cb, Cs)


# Helper functions
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

    B = np.zeros_like(C)

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
    BlendMode.NORMAL: _normal,
    BlendMode.MULTIPLY: _multiply,
    BlendMode.SCREEN: _screen,
    BlendMode.OVERLAY: _overlay,
    BlendMode.DARKEN: _darken,
    BlendMode.LIGHTEN: _lighten,
    BlendMode.COLOR_DODGE: _color_dodge,
    BlendMode.COLOR_BURN: _color_burn,
    BlendMode.LINEAR_DODGE: _linear_dodge,
    BlendMode.LINEAR_BURN: _linear_burn,
    BlendMode.HARD_LIGHT: _hard_light,
    BlendMode.SOFT_LIGHT: _soft_light,
    BlendMode.VIVID_LIGHT: _vivid_light,
    BlendMode.LINEAR_LIGHT: _linear_light,
    BlendMode.PIN_LIGHT: _pin_light,
    BlendMode.HARD_MIX: _hard_mix,
    BlendMode.DIVIDE: _divide,
    BlendMode.DIFFERENCE: _difference,
    BlendMode.EXCLUSION: _exclusion,
    BlendMode.SUBTRACT: _subtract,
    BlendMode.HUE: _hue,
    BlendMode.SATURATION: _saturation,
    BlendMode.COLOR: _color,
    BlendMode.LUMINOSITY: _luminosity,
    BlendMode.DARKER_COLOR: _darker_color,
    BlendMode.LIGHTER_COLOR: _lighter_color,
    BlendMode.DISSOLVE: _dissolve,
    # Descriptor keys
    Enum.Normal: _normal,
    Enum.Multiply: _multiply,
    Enum.Screen: _screen,
    Enum.Overlay: _overlay,
    Enum.Darken: _darken,
    Enum.Lighten: _lighten,
    Enum.ColorDodge: _color_dodge,
    Enum.ColorBurn: _color_burn,
    b'linearDodge': _linear_dodge,
    b'linearBurn': _linear_burn,
    Enum.HardLight: _hard_light,
    Enum.SoftLight: _soft_light,
    b'vividLight': _vivid_light,
    b'linearLight': _linear_light,
    b'pinLight': _pin_light,
    b'hardMix': _hard_mix,
    b'blendDivide': _divide,
    Enum.Difference: _difference,
    Enum.Exclusion: _exclusion,
    Enum.Subtract: _subtract,
    Enum.Hue: _hue,
    Enum.Saturation: _saturation,
    Enum.Color: _color,
    Enum.Luminosity: _luminosity,
    b'darkerColor': _darker_color,
    b'ligherColor': _lighter_color,
    Enum.Dissolve: _dissolve,
}
