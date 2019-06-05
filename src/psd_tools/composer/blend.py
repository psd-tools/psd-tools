"""
Blending module.

Check Blending_ section of W3C recommendation for blending mode definitions.

.. _Blending: https://www.w3.org/TR/compositing/#blending
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools.utils import new_registry
from psd_tools.constants import BlendMode

logger = logging.getLogger(__name__)

BLEND_FUNCTIONS, register = new_registry()


def blend(backdrop, image, offset, mode=None):
    from PIL import Image, ImageChops, ImageMath

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
    if mode == BlendMode.NORMAL:
        backdrop.alpha_composite(image)
    else:
        blend_func = BLEND_FUNCTIONS.get(mode, _normal)
        _alpha_composite(backdrop, image, blend_func)

    if target_mode != 'RGBA':
        backdrop = backdrop.convert(target_mode)
    return backdrop


def _alpha_composite(backdrop, source, blend_fn):
    from PIL import Image
    import numpy as np
    Cb = np.asarray(backdrop.convert('RGB')).astype(np.float) / 255.
    Cs = np.asarray(source.convert('RGB')).astype(np.float) / 255.
    Ab = np.asarray(backdrop.getchannel('A')).astype(np.float) / 255.
    Ab = np.expand_dims(Ab, axis=2)
    Cr = (1. - Ab) * Cs + Ab * blend_fn(Cs, Cb)
    result = Image.fromarray((Cr * 255).round().astype(np.uint8), mode='RGB')
    result.putalpha(source.getchannel('A'))
    backdrop.alpha_composite(result)


@register(BlendMode.NORMAL)
def _normal(Cs, Cb):
    return Cs


@register(BlendMode.MULTIPLY)
def _multiply(Cs, Cb):
    return Cs * Cb


@register(BlendMode.SCREEN)
def _screen(Cs, Cb):
    return Cb + Cs - (Cb * Cs)


@register(BlendMode.OVERLAY)
def _overlay(Cs, Cb):
    return _hard_light(Cb, Cs)


@register(BlendMode.DARKEN)
def _darken(Cs, Cb):
    import numpy as np
    return np.minimum(Cb, Cs)


@register(BlendMode.LIGHTEN)
def _lighten(Cs, Cb):
    import numpy as np
    return np.maximum(Cb, Cs)


@register(BlendMode.COLOR_DODGE)
def _color_dodge(Cs, Cb, s=1.0):
    import numpy as np
    B = np.zeros_like(Cs)
    B[Cs == 1] = 1
    B[Cb == 0] = 0
    index = (Cs != 1) & (Cb != 0)
    B[index] = np.minimum(1, Cb[index] / (s * (1 - Cs[index])))
    return B


@register(BlendMode.LINEAR_DODGE)
def _linear_dodge(Cs, Cb):
    import numpy as np
    return np.minimum(1, Cb + Cs)


@register(BlendMode.COLOR_BURN)
def _color_burn(Cs, Cb, s=1.0):
    import numpy as np
    B = np.zeros_like(Cb)
    B[Cb == 1] = 1
    index = (Cb != 1) & (Cs != 0)
    B[index] = 1 - np.minimum(1, (1 - Cb[index]) / (s * Cs[index]))
    return B


@register(BlendMode.LINEAR_BURN)
def _linear_burn(Cs, Cb):
    import numpy as np
    return np.maximum(0, Cb + Cs - 1)


@register(BlendMode.HARD_LIGHT)
def _hard_light(Cs, Cb):
    index = Cs > 0.5
    B = _multiply(Cs, Cb)
    B[index] = _screen(Cs, Cb)[index]
    return B


@register(BlendMode.SOFT_LIGHT)
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
def _linear_light(Cs, Cb):
    index = Cs > 0.5
    B = _linear_burn(Cs, Cb)
    B[index] = _linear_dodge(Cs, Cb)[index]
    return B


@register(BlendMode.PIN_LIGHT)
def _pin_light(Cs, Cb):
    index = Cs > 0.5
    B = _darken(Cs, Cb)
    B[index] = _lighten(Cs, Cb)[index]
    return B


@register(BlendMode.DIFFERENCE)
def _difference(Cs, Cb):
    import numpy as np
    return np.abs(Cb - Cs)


@register(BlendMode.EXCLUSION)
def _exclusion(Cs, Cb):
    return Cb + Cs - 2 * Cb * Cs


@register(BlendMode.SUBTRACT)
def _subtract(Cs, Cb):
    import numpy as np
    return np.maximum(0, Cb - Cs)


@register(BlendMode.HARD_MIX)
def _hard_mix(Cs, Cb):
    B = Cb.copy()
    B[(Cs + Cb) < 1] = 0
    return B


# @register(BlendMode.DIVIDE)
# def _divide(Cs, Cb):
#     B = Cb.copy()
#     index = Cs > 0
#     B[index] = Cb[index] / Cs[index]  # Seems incorrect...
#     return B

# BlendMode.PASS_THROUGH: _normal,
# BlendMode.DISSOLVE: _dissolve,
# BlendMode.DARKER_COLOR: _darker_color,
# BlendMode.LIGHTER_COLOR: _lighter_color,
# BlendMode.DIVIDE: _divide,
# BlendMode.HUE: _hue,
# BlendMode.SATURATION: _saturation,
# BlendMode.COLOR: _color,
# BlendMode.LUMINOSITY: _luminosity,
