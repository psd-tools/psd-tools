"""
Blending module.

Check Blending_ section of W3C recommendation for blending mode definitions.

.. _Blending: https://www.w3.org/TR/compositing/#blending
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools.utils import new_registry
from psd_tools.constants import BlendMode
from psd_tools.terminology import Enum

logger = logging.getLogger(__name__)

BLEND_FUNCTIONS, register = new_registry()


def blend(backdrop, image, offset, mode=None):
    from PIL import Image

    # Align the canvas size.
    if offset[0] < 0:
        if image.width <= -offset[0]:
            return backdrop
        image = image.crop((-offset[0], 0, image.width, image.height))
        offset = (0, offset[1])

    if offset[1] < 0:
        if image.height <= -offset[1]:
            return backdrop
        image = image.crop((0, -offset[1], image.width, image.height))
        offset = (offset[0], 0)

    # Operations must happen in RGBA in Pillow.
    image_ = Image.new(image.mode, backdrop.size)
    image_.paste(image, offset)
    image = image_.convert('RGBA')

    target_mode = backdrop.mode
    if target_mode != 'RGBA':
        backdrop = backdrop.convert('RGBA')

    # Composite blended image.
    if mode not in (BlendMode.NORMAL, Enum.Normal, None):
        blend_func = BLEND_FUNCTIONS.get(mode, _normal)
        image = _blend_image(backdrop, image, blend_func)
    backdrop = Image.alpha_composite(backdrop, image)

    if target_mode != 'RGBA':
        backdrop = backdrop.convert(target_mode)
    return backdrop


def _blend_image(backdrop, source, blend_fn):
    from PIL import Image
    import numpy as np
    Cb = np.asarray(backdrop.convert('RGB')).astype(np.float) / 255.
    Cs = np.asarray(source.convert('RGB')).astype(np.float) / 255.
    Ab = np.asarray(backdrop.getchannel('A')).astype(np.float) / 255.
    Ab = np.expand_dims(Ab, axis=2)
    Cr = (1. - Ab) * Cs + Ab * blend_fn(Cs, Cb)
    result = Image.fromarray((Cr * 255).round().astype(np.uint8), mode='RGB')
    result.putalpha(source.getchannel('A'))
    return result


@register(BlendMode.NORMAL)
@register(Enum.Normal)
def _normal(Cs, Cb):
    return Cs


@register(BlendMode.MULTIPLY)
@register(Enum.Multiply)
def _multiply(Cs, Cb):
    return Cs * Cb


@register(BlendMode.SCREEN)
@register(Enum.Screen)
def _screen(Cs, Cb):
    return Cb + Cs - (Cb * Cs)


@register(BlendMode.OVERLAY)
@register(Enum.Overlay)
def _overlay(Cs, Cb):
    return _hard_light(Cb, Cs)


@register(BlendMode.DARKEN)
@register(Enum.Darken)
def _darken(Cs, Cb):
    import numpy as np
    return np.minimum(Cb, Cs)


@register(BlendMode.LIGHTEN)
@register(Enum.Lighten)
def _lighten(Cs, Cb):
    import numpy as np
    return np.maximum(Cb, Cs)


@register(BlendMode.COLOR_DODGE)
@register(Enum.ColorDodge)
def _color_dodge(Cs, Cb, s=1.0):
    import numpy as np
    B = np.zeros_like(Cs)
    B[Cs == 1] = 1
    B[Cb == 0] = 0
    index = (Cs != 1) & (Cb != 0)
    B[index] = np.minimum(1, Cb[index] / (s * (1 - Cs[index])))
    return B


@register(BlendMode.LINEAR_DODGE)
@register(b'linearDodge')
def _linear_dodge(Cs, Cb):
    import numpy as np
    return np.minimum(1, Cb + Cs)


@register(BlendMode.COLOR_BURN)
@register(Enum.ColorBurn)
def _color_burn(Cs, Cb, s=1.0):
    import numpy as np
    B = np.zeros_like(Cb)
    B[Cb == 1] = 1
    index = (Cb != 1) & (Cs != 0)
    B[index] = 1 - np.minimum(1, (1 - Cb[index]) / (s * Cs[index]))
    return B


@register(BlendMode.LINEAR_BURN)
@register(b'linearBurn')
def _linear_burn(Cs, Cb):
    import numpy as np
    return np.maximum(0, Cb + Cs - 1)


@register(BlendMode.HARD_LIGHT)
@register(Enum.HardLight)
def _hard_light(Cs, Cb):
    index = Cs > 0.5
    B = _multiply(Cs, Cb)
    B[index] = _screen(Cs, Cb)[index]
    return B


@register(BlendMode.SOFT_LIGHT)
@register(Enum.SoftLight)
def _soft_light(Cs, Cb):
    import numpy as np
    index = Cs <= 0.25
    D = np.sqrt(Cb)
    D[index] = ((16 * Cb[index] - 12) * Cb[index] + 4) * Cb[index]
    index = Cs <= 0.5
    B = Cb + (2 * Cs - 1) * (D - Cb)
    B[index] = Cb[index] - (1 - 2 * Cs[index]) * Cb[index] * (1 - Cb[index])
    return B


@register(BlendMode.VIVID_LIGHT)
@register(b'vividLight')
def _vivid_light(Cs, Cb):
    """
    Burns or dodges the colors by increasing or decreasing the contrast,
    depending on the blend color. If the blend color (light source) is lighter
    than 50% gray, the image is lightened by decreasing the contrast. If the
    blend color is darker than 50% gray, the image is darkened by increasing
    the contrast.
    """
    # TODO: Still inaccurate.
    index = Cs > 0.5
    B = _color_dodge(Cs, Cb, 128)
    B[index] = _color_burn(Cs, Cb, 128)[index]
    return B


@register(BlendMode.LINEAR_LIGHT)
@register(b'linearLight')
def _linear_light(Cs, Cb):
    index = Cs > 0.5
    B = _linear_burn(Cs, Cb)
    B[index] = _linear_dodge(Cs, Cb)[index]
    return B


@register(BlendMode.PIN_LIGHT)
@register(b'pinLight')
def _pin_light(Cs, Cb):
    index = Cs > 0.5
    B = _darken(Cs, Cb)
    B[index] = _lighten(Cs, Cb)[index]
    return B


@register(BlendMode.DIFFERENCE)
@register(Enum.Difference)
def _difference(Cs, Cb):
    import numpy as np
    return np.abs(Cb - Cs)


@register(BlendMode.EXCLUSION)
@register(Enum.Exclusion)
def _exclusion(Cs, Cb):
    return Cb + Cs - 2 * Cb * Cs


@register(BlendMode.SUBTRACT)
@register(b'blendSubtraction')
def _subtract(Cs, Cb):
    import numpy as np
    return np.maximum(0, Cb - Cs)


@register(BlendMode.HARD_MIX)
@register(b'hardMix')
def _hard_mix(Cs, Cb):
    B = Cb.copy()
    B[(Cs + Cb) < 1] = 0
    return B


@register(BlendMode.DIVIDE)
@register(b'blendDivide')
def _divide(Cs, Cb):
    B = Cb.copy()
    index = Cs > 0
    B[index] = Cb[index] / Cs[index]  # Seems incorrect...
    return B


@register(BlendMode.HUE)
@register(Enum.Hue)
def _hue(Cs, Cb):
    hs, ls, ss = rgb_to_hls(Cs)
    hb, lb, sb = rgb_to_hls(Cb)
    return hls_to_rgb(hs, lb, sb)


@register(BlendMode.SATURATION)
@register(Enum.Saturation)
def _saturation(Cs, Cb):
    hs, ls, ss = rgb_to_hls(Cs)
    hb, lb, sb = rgb_to_hls(Cb)
    return hls_to_rgb(hb, lb, ss)


@register(BlendMode.COLOR)
@register(Enum.Color)
def _color(Cs, Cb):
    hs, ls, ss = rgb_to_hls(Cs)
    hb, lb, sb = rgb_to_hls(Cb)
    return hls_to_rgb(hs, lb, ss)


@register(BlendMode.LUMINOSITY)
@register(Enum.Luminosity)
def _luminosity(Cs, Cb):
    hs, ls, ss = rgb_to_hls(Cs)
    hb, lb, sb = rgb_to_hls(Cb)
    return hls_to_rgb(hb, ls, sb)


# BlendMode.DISSOLVE: _dissolve,
# BlendMode.DARKER_COLOR: _darker_color,
# BlendMode.LIGHTER_COLOR: _lighter_color,

# Enum.Dissolve: _dissolve,
# b'darkerColor': _darker_color,
# b'lighterColor': _lighter_color,


def rgb_to_hls(rgb):
    """RGB to HSL conversion.

    See colorsys module.
    """
    import numpy as np

    maxc = np.max(rgb, axis=2)
    minc = np.min(rgb, axis=2)
    nonzero_index = (minc < maxc)
    c_diff = maxc - minc

    l = (minc + maxc) / 2.0
    s = np.zeros_like(l)
    h = np.zeros_like(l)

    index = nonzero_index
    s[index] = c_diff[index] / (2.0 - maxc[index] - minc[index])
    index = (l <= 0.5) & nonzero_index
    s[index] = c_diff[index] / (maxc[index] + minc[index])

    rc, gc, bc = (
        maxc[nonzero_index] -
        rgb[:, :, i][nonzero_index] / c_diff[nonzero_index] for i in range(3)
    )
    hc = 4.0 + gc - rc  # 4 + gc - rc
    index = (rgb[:, :, 1][nonzero_index] == maxc[nonzero_index])
    hc[index] = 2.0 + rc[index] - bc[index]  # 2 + rc - bc
    index = (rgb[:, :, 0][nonzero_index] == maxc[nonzero_index])
    hc[index] = bc[index] - gc[index]  # bc - gc
    h[nonzero_index] = (hc / 6.0) % 1.0
    return h, l, s


def hls_to_rgb(h, l, s):
    """HSL to RGB conversion.

    See colorsys module.
    """
    import numpy as np
    ONE_THIRD = 1. / 3.
    TWO_THIRD = 2. / 3.
    ONE_SIXTH = 1. / 6.
    r, g, b = np.copy(l), np.copy(l), np.copy(l)
    nonzero_index = (s != 0.)

    m2 = l + s - (l * s)
    index = l <= 0.5
    m2[index] = l[index] * (1.0 + s[index])
    m1 = 2.0 * l - m2

    def _v(m1, m2, hue):
        hue = hue % 1.0
        c = np.copy(m1)
        index = hue < TWO_THIRD
        c[index] = m1[index] + (m2[index] -
                                m1[index]) * (TWO_THIRD - hue[index]) * 6.0
        index = hue < 0.5
        c[index] = m2[index]
        index = hue < ONE_SIXTH
        c[index] = m1[index] + (m2[index] - m1[index]) * hue[index] * 6.0
        return c

    r[nonzero_index] = _v(m1, m2, h + ONE_THIRD)[nonzero_index]
    g[nonzero_index] = _v(m1, m2, h)[nonzero_index]
    b[nonzero_index] = _v(m1, m2, h - ONE_THIRD)[nonzero_index]
    return np.stack((r, g, b), axis=2)
