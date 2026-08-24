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
- **Drop shadow**: Offset, choked and blurred silhouette painted behind the layer
  - Solid color fill; honors distance, angle (incl. global light), size, choke,
    opacity, blend mode and "layer knocks out drop shadow"
  - The falloff is a gaussian approximation of Photoshop's proprietary blur, so the
    placement is faithful but the shadow intensity can differ — large, soft shadows
    tend to render somewhat darker than Photoshop

Partially supported or limited effects:

- Inner shadow, outer glow, inner glow
- These may render but with reduced accuracy

The main function :py:func:`draw_stroke_effect` handles stroke rendering by:

1. Extracting the layer's alpha channel or shape mask
2. Applying morphological operations (dilation/erosion) based on stroke size and position
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
from psd_tools.composite._compat import require_scipy, require_skimage
from psd_tools.psd.descriptor import Descriptor
from psd_tools.terminology import Enum, Key

if TYPE_CHECKING:
    from psd_tools.api.protocols import PSDProtocol

logger = logging.getLogger(__name__)

# Maps Photoshop's "Size" parameter to a gaussian blur sigma. Photoshop's blur is a
# proprietary approximation; sigma = size / 3 is a close, widely-used heuristic.
_SIGMA_PER_SIZE = 1.0 / 3.0


@require_scipy
def draw_drop_shadow(
    viewport: tuple[int, int, int, int],
    shape: np.ndarray,
    *,
    distance: float,
    angle: float,
    size: float,
    choke: float,
) -> np.ndarray:
    """Synthesize a drop-shadow coverage mask from a layer silhouette.

    The layer's ``shape`` (silhouette) is offset along the cast direction of a light
    at ``angle`` degrees. Returns an ``(H, W, 1)`` float32 coverage mask in the same
    ``viewport`` as ``shape``; the caller tints and blends it behind the layer.
    """
    from scipy import ndimage  # type: ignore[import-untyped]  # noqa: PLC0415

    a = shape[:, :, 0].astype(np.float32)
    # Choke contracts the matte before blurring. In Photoshop's UI choke is a percentage
    # of size, even though the descriptor stores both in pixels.
    choke_px = max(0, int(round(choke / 100.0 * size)))
    if choke_px > 0:
        a = ndimage.grey_erosion(a, size=2 * choke_px + 1)
    # Blur. Photoshop "Size" is a soft falloff radius; sigma ~= size / 3 places ~3 sigma
    # of the gaussian within the stated size (heuristic, see module notes).
    sigma = max(0.0, size * _SIGMA_PER_SIZE)
    if sigma > 1e-3:
        a = ndimage.gaussian_filter(a, sigma)
    # Photoshop angle is the light direction; the shadow casts in the opposite
    # direction. Image coordinates are y-down, so a positive sin moves the shadow down.
    theta = math.radians(angle)
    dx = -distance * math.cos(theta)
    dy = +distance * math.sin(theta)
    a = ndimage.shift(a, (dy, dx), order=1, mode="constant", cval=0.0)
    return np.clip(a, 0.0, 1.0)[:, :, None]


@require_skimage
def draw_stroke_effect(
    viewport: tuple[int, int, int, int],
    shape: np.ndarray,
    desc: Descriptor,
    psd: "PSDProtocol",
) -> tuple[np.ndarray, np.ndarray]:
    # Import here after checking dependencies
    from skimage import filters  # noqa: PLC0415
    from skimage.morphology import disk  # noqa: PLC0415

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
