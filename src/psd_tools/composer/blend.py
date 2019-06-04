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

# BlendMode.PASS_THROUGH: _normal,
# BlendMode.NORMAL: _normal,
# BlendMode.DISSOLVE: _dissolve,
# BlendMode.DARKEN: _darken,
# BlendMode.MULTIPLY: _multiply,
# BlendMode.COLOR_BURN: _color_burn,
# BlendMode.LINEAR_BURN: _linear_burn,
# BlendMode.DARKER_COLOR: _darker_color,
# BlendMode.LIGHTEN: _lighten,
# BlendMode.SCREEN: _screen,
# BlendMode.COLOR_DODGE: _color_dodge,
# BlendMode.LINEAR_DODGE: _linear_dodge,
# BlendMode.LIGHTER_COLOR: _lighter_color,
# BlendMode.OVERLAY: _overlay,
# BlendMode.SOFT_LIGHT: _soft_light,
# BlendMode.HARD_LIGHT: _hard_light,
# BlendMode.VIVID_LIGHT: _vivid_light,
# BlendMode.LINEAR_LIGHT: _linear_light,
# BlendMode.PIN_LIGHT: _pin_light,
# BlendMode.HARD_MIX: _hard_mix,
# BlendMode.DIFFERENCE: _difference,
# BlendMode.EXCLUSION: _exclusion,
# BlendMode.SUBTRACT: _subtract,
# BlendMode.DIVIDE: _divide,
# BlendMode.HUE: _hue,
# BlendMode.SATURATION: _saturation,
# BlendMode.COLOR: _color,
# BlendMode.LUMINOSITY: _luminosity,


def blend(target, image, offset, mode=None):
    from PIL import Image, ImageChops, ImageMath

    # Align the canvas size.
    if offset[0] < 0:
        if image.width <= -offset[0]:
            return target
        image = image.crop((-offset[0], 0, image.width, image.height))
        offset = (0, offset[1])

    if offset[1] < 0:
        if image.height <= -offset[1]:
            return target
        image = image.crop((0, -offset[1], image.width, image.height))
        offset = (offset[0], 0)

    # Operations must happen in RGBA in Pillow.
    image_ = Image.new(image.mode, target.size)
    image_.paste(image, offset)
    image = image_.convert('RGBA')

    target_mode = target.mode
    if target_mode != 'RGBA':
        target = target.convert('RGBA')

    # Composite blended image.
    blend_func = BLEND_FUNCTIONS.get(mode, _normal)
    _alpha_composite(target, image, blend_func)

    if target_mode != 'RGBA':
        target = target.convert(target_mode)
    return target


def _alpha_composite(backdrop, source, blend_fn):
    from PIL import Image
    import numpy as np
    Cb = np.asarray(backdrop.convert('RGB')).astype(np.float) / 255.
    Cs = np.asarray(source.convert('RGB')).astype(np.float) / 255.
    Ab = np.asarray(backdrop.getchannel('A')).astype(np.float) / 255.
    Ab = np.expand_dims(Ab, axis=2)
    Cr = (1. - Ab) * Cs + Ab * blend_fn(Cs, Cb)
    result = Image.fromarray((Cr * 255.).astype(np.uint8), mode='RGB')
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
    return Cb.minimum(Cs)


@register(BlendMode.LIGHTEN)
def _lighten(Cs, Cb):
    return Cb.maximum(Cs)


@register(BlendMode.COLOR_DODGE)
def _color_dodge(Cs, Cb):
    import numpy as np
    B = np.zeros_like(Cs)
    B[Cb == 0] = 0
    B[Cs == 1] = 1
    index = (Cb != 0) & (Cs != 1)
    B[index] = np.minimum(1, Cb[index] / (1 - Cs[index]))
    return B


@register(BlendMode.COLOR_BURN)
def _color_burn(Cs, Cb):
    import numpy as np
    B = np.zeros_like(Cs)
    B[Cb == 1] = 1
    B[Cs == 0] = 0
    index = (Cb != 1) & (Cs != 0)
    B[index] = 1 - np.minimum(1, (1 - Cb[index]) / Cs[index])
    return B


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


@register(BlendMode.DIFFERENCE)
def _difference(Cs, Cb):
    import numpy as np
    return np.abs(Cb - Cs)


@register(BlendMode.EXCLUSION)
def _exclusion(Cs, Cb):
    return Cb + Cs - 2 * Cb * Cs
