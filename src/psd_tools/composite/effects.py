import logging

import numpy as np
from skimage import filters
from skimage.morphology import disk

import psd_tools.composite
from psd_tools.terminology import Enum, Key

from .vector import draw_gradient_fill, draw_pattern_fill, draw_solid_color_fill

logger = logging.getLogger(__name__)


def draw_stroke_effect(viewport, shape, desc, psd):
    logger.debug("Stroke effect has limited support")
    height, width = viewport[3] - viewport[1], viewport[2] - viewport[0]
    if not isinstance(shape, np.ndarray):
        shape = np.full((height, width, 1), shape, dtype=np.float32)

    paint = desc.get(Key.PaintType).enum
    if paint == Enum.SolidColor:
        color, _ = draw_solid_color_fill(viewport, psd.color_mode, desc)
    elif paint == Enum.Pattern:
        color, _ = draw_pattern_fill(viewport, psd, desc)
    elif paint == Enum.GradientFill:
        color, _ = draw_gradient_fill(viewport, psd.color_mode, desc)
    else:
        logger.warning("No fill specification found.")
        color = np.ones((height, width, 1))

    # Note: current implementation is purely image-based.
    # For layers with path objects, this should be based on drawing.

    style = desc.get(Key.Style).enum
    size = float(desc.get(Key.SizeKey, 1.0))
    if style in (Enum.OutsetFrame, Enum.InsetFrame):
        size *= 2

    edges = filters.scharr(shape[:, :, 0])
    pen = disk(int(size / 2.0 - 1))
    mask = (
        filters.rank.maximum((255 * edges).astype(np.uint8), pen).astype(np.float32)
        / 255.0
    )
    mask = psd_tools.composite._divide(mask - np.min(mask), np.max(mask) - np.min(mask))
    mask = np.expand_dims(mask, 2)

    if style == Enum.OutsetFrame:
        mask = np.maximum(0, mask - shape)
    elif style == Enum.InsetFrame:
        mask = np.maximum(0, mask * shape)

    return color, mask
