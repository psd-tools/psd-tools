# mypy: disable-error-code="assignment"
import logging
from typing import Tuple

import numpy as np

from psd_tools.composite import paint, utils
from psd_tools.composite._compat import require_skimage
from psd_tools.psd.descriptor import Descriptor
from psd_tools.terminology import Enum, Key

logger = logging.getLogger(__name__)


@require_skimage
def draw_stroke_effect(
    viewport: Tuple[int, int, int, int], shape: np.ndarray, desc: Descriptor, psd
) -> Tuple[np.ndarray, np.ndarray]:
    # Import here after checking dependencies
    from skimage import filters
    from skimage.morphology import disk

    logger.debug("Stroke effect has limited support")
    height, width = viewport[3] - viewport[1], viewport[2] - viewport[0]
    if not isinstance(shape, np.ndarray):
        shape = np.full((height, width, 1), shape, dtype=np.float32)

    paint_type = desc.get(Key.PaintType).enum
    if paint_type == Enum.SolidColor:
        color, _ = paint.draw_solid_color_fill(viewport, psd.color_mode, desc)
        if color is None:
            color = np.ones((height, width, 1))
    elif paint_type == Enum.Pattern:
        color, _ = paint.draw_pattern_fill(viewport, psd, desc)
        if color is None:
            color = np.ones((height, width, 1))
    elif paint_type == Enum.GradientFill:
        color, _ = paint.draw_gradient_fill(viewport, psd.color_mode, desc)
        if color is None:
            color = np.ones((height, width, 1))
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
    mask = utils.divide(mask - np.min(mask), np.max(mask) - np.min(mask))
    mask = np.expand_dims(mask, 2)

    if style == Enum.OutsetFrame:
        mask = np.maximum(0, mask - shape)
    elif style == Enum.InsetFrame:
        mask = np.maximum(0, mask * shape)

    return color, mask
