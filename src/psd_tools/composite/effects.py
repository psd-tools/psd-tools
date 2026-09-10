# mypy: disable-error-code="assignment"
"""
Layer effects rendering.

This module implements rendering for Photoshop layer effects (also known as
layer styles). Effects are non-destructive visual enhancements applied to layers
such as strokes, shadows, glows, and overlays.

**Note**: Effects rendering requires scikit-image. Install with::

    pip install 'psd-tools[composite]'

Currently supported effects:

- **Stroke**: Outline around layer shape or pixels
  - Supports solid color, gradient, and pattern fills
  - Position: inside, outside, or centered
  - Limited compared to Photoshop's full implementation

Partially supported or limited effects:

- Drop shadow, inner shadow, outer glow, inner glow
- These may render but with reduced accuracy

The main function :py:func:`draw_stroke_effect` handles stroke rendering by:

1. Extracting the layer's alpha channel or shape mask
2. Placing the stroke relative to that shape according to its size and position
3. Filling the stroke region with the specified paint (solid color, gradient, pattern)
4. Returning the rendered stroke as a NumPy array

Implementation notes:

- Effects are image-based rather than vector-based, which may differ from Photoshop
- For layers with vector paths, ideally strokes should be drawn geometrically
- Some effect parameters may not be fully supported
- Complex effect combinations may not render identically to Photoshop

Example usage (internal)::

    from psd_tools.composite.effects import draw_stroke_effect

    # Called during layer compositing
    viewport = (0, 0, 100, 100)  # Region to render
    shape = layer_alpha_channel    # NumPy array
    desc = stroke_descriptor       # Effect parameters

    color, alpha = draw_stroke_effect(viewport, shape, desc, psd)

The effects system integrates with the main compositing pipeline and is
automatically applied when rendering layers that have effects enabled.
"""

import logging
import math
from typing import TYPE_CHECKING

import numpy as np

from psd_tools.composite import paint, utils
from psd_tools.composite._compat import require_skimage
from psd_tools.psd.descriptor import Descriptor
from psd_tools.terminology import Enum, Key

if TYPE_CHECKING:
    from psd_tools.api.protocols import PSDProtocol

logger = logging.getLogger(__name__)

# How far a stroke reaches outside the layer, as a fraction of its nominal
# size. Only the inset style stays within the layer; the other two spill past
# its bounding box and need canvas of their own to be drawn on.
_OUTWARD_REACH = {
    Enum.OutsetFrame: 1.0,
    Enum.CenteredFrame: 0.5,
    Enum.InsetFrame: 0.0,
}


def stroke_bbox(
    bbox: tuple[int, int, int, int], desc: Descriptor
) -> tuple[int, int, int, int]:
    """The canvas :py:func:`draw_stroke_effect` needs to draw a stroke on.

    The stroke is drawn outward from the layer's edge, so an outset or
    centered one lands partly outside ``bbox``. Drawing it on ``bbox`` itself
    has no room for that part and silently discards it -- for a layer whose
    pixels fill its bounding box, that is the whole stroke (#792). Growing the
    box by the stroke's outward reach gives it somewhere to land.

    An empty ``bbox`` is returned untouched: there is no edge to trace, and
    growing it would place a stroke around the origin.
    """
    if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
        return bbox
    reach = _OUTWARD_REACH.get(desc.get(Key.Style).enum, 1.0)
    if reach == 0.0:
        return bbox
    # ceil() because a fractional stroke still covers the pixel it falls in.
    # The +1 is slack: a band reaches exactly ceil(size * reach), and an
    # unrecognised style falls through to the dilation path, whose edge filter
    # spreads a pixel further. Inset never gets here, its reach being 0.
    margin = math.ceil(float(desc.get(Key.SizeKey, 1.0)) * reach) + 1
    return (bbox[0] - margin, bbox[1] - margin, bbox[2] + margin, bbox[3] + margin)


def _signed_distance(alpha: np.ndarray) -> np.ndarray:
    """Euclidean distance from each pixel to the mask boundary, negative inside.

    ``distance_transform_edt`` measures to the nearest pixel of the other
    class, so the two pixels straddling the boundary both come back 1.0 rather
    than the 0.5 their centres really sit at. The magnitude is shrunk to put
    the boundary back between them; subtracting 0.5 outright would be right
    outside and a full pixel wrong inside, where the sign is negative.

    A pixel that straddles the boundary knows better than the 0.5 iso-contour
    does where within itself the boundary falls, so those pixels -- and only
    those -- are reseeded from their own coverage. Reseeding every partial
    pixel would drag the far side of a feathered mask to within half a pixel
    of a boundary it is nowhere near, and paint a stroke across all of it.
    """
    from scipy.ndimage import distance_transform_edt  # type: ignore[import-untyped]  # noqa: PLC0415

    inside = alpha >= 0.5
    # With no boundary in view there is nothing to measure a stroke from, and
    # ``distance_transform_edt`` is undefined on an input with no zeros: it
    # reports distances to a phantom feature off the array corner, which a band
    # would paint as a wedge in the corner of the canvas. Being uniformly
    # infinitely far from the boundary leaves every band empty, which is right.
    if inside.all():
        return np.full(alpha.shape, -np.inf, dtype=np.float32)
    if not inside.any():
        return np.full(alpha.shape, np.inf, dtype=np.float32)

    distance = distance_transform_edt(~inside).astype(np.float32)
    distance -= distance_transform_edt(inside).astype(np.float32)
    distance = np.sign(distance) * np.maximum(np.abs(distance) - 0.5, 0.0)
    straddles = (alpha > 0) & (alpha < 1) & (np.abs(distance) <= 0.5)
    distance[straddles] = 0.5 - alpha[straddles]
    return distance


def _distance_band(distance: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Coverage of the band between ``lo`` and ``hi``, antialiased.

    A distance field has unit gradient, so one pixel of distance is one pixel
    of space, and a linear ramp across it is the exact area of a pixel cut by
    a straight edge. That is what lets a fractional width mean something: the
    band is never quantized to a whole number of pixels the way a dilation pen
    is. Where the band's edge curves, around a corner, the ramp approximates
    that area rather than matching it.
    """
    return np.clip(hi - distance + 0.5, 0, 1) * np.clip(distance - lo + 0.5, 0, 1)


@require_skimage
def draw_stroke_effect(
    viewport: tuple[int, int, int, int],
    shape: np.ndarray,
    desc: Descriptor,
    psd: "PSDProtocol",
) -> tuple[np.ndarray, np.ndarray]:
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

    # An outset or centered stroke is a band in the layer's signed distance
    # field, which is exact on a hard-edged mask and needs no pen to quantize
    # the radius to a whole pixel. Inset keeps the dilation below: it is
    # anchored differently, and a symmetric band misses it by about a pixel
    # (#799). Any style this does not name keeps the dilation too.
    if style in (Enum.OutsetFrame, Enum.CenteredFrame):
        limits = (0.0, size) if style == Enum.OutsetFrame else (-size / 2.0, size / 2.0)
        distance = _signed_distance(shape[:, :, 0])
        return color, np.expand_dims(_distance_band(distance, *limits), 2)

    if style == Enum.InsetFrame:
        size *= 2

    # Only the dilation path needs skimage, which is why @require_skimage
    # still guards a function whose main path is scipy's alone.
    from skimage import filters  # noqa: PLC0415
    from skimage.morphology import disk  # noqa: PLC0415

    edges = filters.scharr(shape[:, :, 0])
    # Rounded up rather than truncated, which drew every odd stroke a pixel
    # short per side (#792). Only inset reaches this now, so the doubling
    # above always leaves the radius whole, but the ceil() still guards the
    # unrecognised styles that fall through here undoubled.
    pen = disk(math.ceil(size / 2.0 - 1))
    mask = (
        filters.rank.maximum((255 * edges).astype(np.uint8), pen).astype(np.float32)
        / 255.0
    )
    mask = utils.divide(mask - np.min(mask), np.max(mask) - np.min(mask))
    mask = np.expand_dims(mask, 2)

    if style == Enum.InsetFrame:
        mask = np.maximum(0, mask * shape)

    return color, mask
