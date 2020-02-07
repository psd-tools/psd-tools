"""
Effects module.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools.composer.vector import (
    draw_pattern_fill, draw_gradient_fill, draw_solid_color_fill
)
from psd_tools.terminology import Enum, Key

logger = logging.getLogger(__name__)


def create_stroke_effect(alpha, setting, psd, mask_given=False):
    offset = alpha.info['offset']
    if mask_given:
        mask = alpha
    else:
        mask = create_stroke_mask(alpha, setting)
    paint = setting.get(Key.PaintType).enum
    if paint == Enum.SolidColor:
        result = draw_solid_color_fill(mask.size, setting)
    elif paint == Enum.GradientFill:
        result = draw_gradient_fill(mask.size, setting)
    elif paint == Enum.Pattern:
        result = draw_pattern_fill(mask.size, psd, setting)
    result.putalpha(mask)
    result.info['offset'] = offset
    return result


def create_stroke_mask(alpha, setting):
    """
    Create a mask image for the given alpha image.

    TODO: MaxFilter is square, but the desired region is circle.
    """
    from PIL import ImageFilter, ImageChops, ImageMath

    mask = ImageMath.eval('255 * (x > 0)', x=alpha).convert('L')
    edge = alpha.filter(ImageFilter.FIND_EDGES)
    size = int(setting.get(Key.SizeKey))
    style = setting.get(Key.Style).enum
    odd_size = 2 * int(size / 2.) + 1
    if style == Enum.OutsetFrame:
        result = ImageChops.subtract(
            edge.filter(ImageFilter.MaxFilter(2 * size + 1)), mask
        )
    elif style == Enum.InsetFrame:
        result = ImageChops.subtract(
            edge.filter(ImageFilter.MaxFilter(2 * size - 1)),
            ImageChops.invert(mask)
        )
    else:
        result = edge.filter(ImageFilter.MaxFilter(odd_size))

    inverse_alpha = ImageChops.darker(ImageChops.invert(alpha), mask)
    return ImageChops.lighter(result, inverse_alpha)
