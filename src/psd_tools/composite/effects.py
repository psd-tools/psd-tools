# mypy: disable-error-code="assignment"
"""
Layer effects rendering.

This module implements rendering for Photoshop layer effects (also known as
layer styles). Effects are non-destructive visual enhancements applied to layers
such as strokes, shadows, glows, and overlays.

**Note**: Effects rendering requires scipy. It additionally requires
scikit-image for any pattern fill -- but for nothing else, so a solid or
gradient stroke of any position draws with scipy alone. Install both with::

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

from psd_tools.composite import paint
from psd_tools.composite._compat import HAS_SCIPY
from psd_tools.psd.descriptor import Descriptor
from psd_tools.terminology import Enum, Key

if TYPE_CHECKING:
    from psd_tools.api.protocols import PSDProtocol

logger = logging.getLogger(__name__)

# Where each style puts its band, in multiples of the stroke's nominal size,
# measured from the layer's edge and positive outward. One table because the
# outer limit is also how far the stroke reaches past the layer, which is the
# canvas :py:func:`stroke_bbox` has to reserve for it: stating the two apart
# would let a change to one shave the outside of every stroke of that style,
# or reserve canvas nobody draws on.
#
# Only the inset style stays within the layer. It still gets the fixed pixel
# stroke_bbox() adds on top, which is not room for the stroke but room for the
# edge it is measured from.
_BANDS: dict[bytes, tuple[float, float]] = {
    Enum.OutsetFrame: (0.0, 1.0),
    Enum.CenteredFrame: (-0.5, 0.5),
    Enum.InsetFrame: (-1.0, 0.0),
}
# A style no descriptor Photoshop wrote can hold is drawn, and measured, as an
# outset one -- the widest of the three, so nothing it draws is clipped by the
# canvas reserved for it, and the position Photoshop itself defaults to.
_UNRECOGNISED = _BANDS[Enum.OutsetFrame]


def _enum(desc: Descriptor, key: bytes) -> bytes:
    """The enum ``key`` names, or ``b""`` if the descriptor does not carry one.

    Both keys read through this -- the stroke's position and its paint type --
    already have a defined answer for an enum neither table below knows, so a
    key that is missing or holds something other than an ``Enumerated`` costs
    nothing new to tolerate: it joins the unrecognised value it cannot be told
    apart from. Reading it straight off instead turned a descriptor psd-tools
    did not write into an ``AttributeError`` out of a composite (#826).

    ``b""`` rather than None so the absence is literally an enum no table
    holds and takes their fallback without a branch of its own; no real one
    can collide with it, every enum Photoshop writes being four bytes.
    ``api.effects._ColorMixin.blend_mode`` reaches for its enum the same way,
    onto a default of its own.
    """
    return getattr(desc.get(key), "enum", b"")


def stroke_bbox(
    bbox: tuple[int, int, int, int], desc: Descriptor
) -> tuple[int, int, int, int]:
    """The canvas :py:func:`draw_stroke_effect` needs to draw a stroke on.

    The stroke is drawn outward from the layer's edge, so an outset or
    centered one lands partly outside ``bbox``. Drawing it on ``bbox`` itself
    has no room for that part and silently discards it -- for a layer whose
    pixels fill its bounding box, that is the whole stroke (#792). Growing the
    box by the stroke's outward reach gives it somewhere to land.

    An inset stroke lands wholly inside the layer and needs no room, but it is
    still measured from the layer's edge, and on that same layer the edge is
    not in the picture either: every pixel of ``bbox`` is covered, so there is
    nothing to locate a boundary against and no stroke is drawn at all. The
    fixed pixel every style gets on top of its reach is what puts the edge back
    in view (#799).

    An empty ``bbox`` is returned untouched: there is no edge to trace, and
    growing it would place a stroke around the origin.

    A style the descriptor does not state, or states as something other than
    an enum, is measured as the unrecognised style it cannot be told apart
    from -- an outset one, which :py:func:`draw_stroke_effect` then draws it
    as -- rather than raising out of a composite (#826).
    """
    if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
        return bbox
    reach = _BANDS.get(_enum(desc, Key.Style), _UNRECOGNISED)[1]
    # ceil() because a fractional stroke still covers the pixel it falls in.
    # The +1 is the uncovered pixel the edge is measured against.
    margin = math.ceil(float(desc.get(Key.SizeKey, 1.0)) * reach) + 1
    return (bbox[0] - margin, bbox[1] - margin, bbox[2] + margin, bbox[3] + margin)


def _grow(mask: np.ndarray) -> np.ndarray:
    """``mask`` widened by one pixel along each axis.

    Sliced rather than rolled, so the first row does not count the last one as
    its neighbour: a layer flush against one side of its viewport and
    transparent against the other would otherwise read as a boundary between
    them. No stroke effect can reach that today -- :py:func:`stroke_bbox`
    grants a pixel of clear border on every side -- so this is stated here
    rather than relied on there, because widening that margin away is the kind
    of change nothing else would notice.
    """
    grown = mask.copy()
    for axis in range(mask.ndim):
        lead: list[slice] = [slice(None)] * mask.ndim
        trail: list[slice] = [slice(None)] * mask.ndim
        lead[axis], trail[axis] = slice(1, None), slice(None, -1)
        grown[tuple(lead)] |= mask[tuple(trail)]
        grown[tuple(trail)] |= mask[tuple(lead)]
    return grown


def _signed_distance(alpha: np.ndarray) -> np.ndarray:
    """Distance from each pixel to the mask boundary, negative inside.

    Photoshop reads that boundary off the mask's **coverage**, not off its 0.5
    iso-contour: a pixel at ``alpha`` states that the boundary runs
    ``0.5 - alpha`` from its own centre, and its neighbours measure outward
    from there. On a hard-edged mask the two readings name the same line --
    one partial pixel, and the boundary is where its coverage puts it -- which
    is why this leaves every hard-edged fixture in the corpus bit for bit
    unchanged. On a *feathered* one they diverge without limit: a 16 px alpha
    ramp runs 8 px from the iso-contour at either end and half a pixel from
    the boundary everywhere, so a stroke of any size covers all of it. Measured
    against Photoshop on purpose-built masks -- linear ramps of several
    widths, a ramp onto a partial plateau, and hard edges with a single
    antialiased pixel -- which is #799's fourth tracking item, and which
    ``effects/feathered-stroke.psd`` and ``effects/antialiased-stroke-edge.psd``
    are the rendered half of.

    Coverage says nothing about an edge that has none, so a mask stepping
    0 -> 1 keeps the exact Euclidean distance to the iso-contour, ``base``.
    One mask can carry both -- a shape antialiased along one side and butted
    against its own bounding box along another -- so the two are chosen
    between per pixel, by which boundary is nearer. Seeding a single transform
    from both instead costs the corners: measured against the same masks, up
    to 0.97 coverage where a feathered edge meets a hard one, against 0.002
    for this.

    What a pixel outside the partial band gets is that band's distance plus
    the coverage its nearest partial pixel states, which offsets along the
    line to that pixel rather than along the boundary's own normal. The two
    agree on a straight edge and part company around a curve, so a feathered
    corner is approximated here in the same way :py:func:`_distance_band`
    approximates the arc it paints there.

    A mask that is flat at 0 or 1 has no boundary at all. That is not a case
    to fall through: ``distance_transform_edt`` is undefined on an input with
    no zeros and reports distances to a phantom feature off the array corner,
    which a band paints as a wedge in the corner of the canvas. Being
    uniformly infinitely far from the boundary leaves every band empty, which
    is right. A mask flat at a *partial* value is not one of these -- every
    pixel of it states a boundary, so it takes a stroke over all of it.
    """
    if not HAS_SCIPY:
        raise ImportError(
            "Stroke effects require: scipy\n\n"
            "Install with:\n"
            "    pip install 'psd-tools[composite]'\n"
            "Or:\n"
            "    pip install scipy"
        )
    from scipy.ndimage import distance_transform_edt  # type: ignore[import-untyped]  # noqa: PLC0415

    partial = (alpha > 0) & (alpha < 1)
    # The boundary segments no coverage describes: a step from opaque straight
    # to clear. Every pixel of a smoothly antialiased shape has coverage, so
    # this is usually empty and the iso-contour below is never computed --
    # which is what keeps the field to one transform rather than three.
    hard = (alpha >= 1) & _grow(alpha <= 0)
    hard |= (alpha <= 0) & _grow(alpha >= 1)

    if not partial.any() or hard.any():
        # ``distance_transform_edt`` measures to the nearest pixel of the other
        # class, so the two pixels straddling the boundary both come back 1.0
        # rather than the 0.5 their centres really sit at. The magnitude is
        # shrunk to put the boundary back between them; subtracting 0.5
        # outright would be right outside and a full pixel wrong inside, where
        # the sign is negative.
        inside = alpha >= 0.5
        if inside.all():
            base = np.full(alpha.shape, -np.inf, dtype=np.float32)
        elif not inside.any():
            base = np.full(alpha.shape, np.inf, dtype=np.float32)
        else:
            base = distance_transform_edt(~inside).astype(np.float32)
            base -= distance_transform_edt(inside).astype(np.float32)
            base = np.sign(base) * np.maximum(np.abs(base) - 0.5, 0.0)
        if not partial.any():
            return base

    # What a partial pixel states, and what a pixel with none of its own takes
    # by walking out to the nearest pixel that has some. ``alpha >= 1`` rather
    # than the iso-contour picks the sign: every pixel left to place is at 0
    # or 1.
    near = (0.5 - alpha).astype(np.float32)
    distance, index = distance_transform_edt(~partial, return_indices=True)
    reach = near[tuple(index)] + np.where(alpha >= 1, -distance, distance)
    if not hard.any():
        return np.where(partial, near, reach).astype(np.float32)

    # ``base`` is exact along a hard step, and is the better answer for any
    # pixel nearer one of them than it is to the partial band.
    to_hard = distance_transform_edt(~hard)
    field = np.where(partial, near, np.where(distance <= to_hard, reach, base))
    return field.astype(np.float32)


def _distance_band(distance: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Coverage of the band between ``lo`` and ``hi``, antialiased.

    A distance field has unit gradient, so one pixel of distance is one pixel
    of space, and a linear ramp across it is the exact area of a pixel cut by
    a straight edge. That is what lets a fractional width mean something: the
    band is never quantized to a whole number of pixels, the way it was while
    a stroke was drawn with an integer-radius pen. Where the band's edge
    curves, around a corner, the ramp approximates that area rather than
    matching it.
    """
    return np.clip(hi - distance + 0.5, 0, 1) * np.clip(distance - lo + 0.5, 0, 1)


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

    paint_type = _enum(desc, Key.PaintType)
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

    style = _enum(desc, Key.Style)
    size = float(desc.get(Key.SizeKey, 1.0))

    # A stroke of no width draws nothing, and the band has to be told so: it
    # would otherwise paint a quarter of a pixel wherever the boundary falls
    # exactly on a pixel centre. Photoshop will not author a 0 px stroke, but
    # a descriptor can carry one.
    if size <= 0.0:
        return color, np.zeros((height, width, 1), dtype=np.float32)

    # A stroke is a band in the layer's signed distance field, which is exact
    # on a hard-edged mask and needs no pen to quantize the radius to a whole
    # pixel. All three positions are the same band read off a different
    # anchor, inset included: Photoshop measures it from the same boundary as
    # the other two, and the pixel of offset that looked like a different
    # anchor was the layer's edge being clipped away before the stroke saw it
    # (#799). Nor does an inset band need clamping to the layer to stay inside
    # it: on a pixel the boundary cuts, the band already comes out equal to
    # that pixel's own coverage, feathered masks included.
    #
    # A position the descriptor states as something else, or does not state at
    # all, takes the outset band. There is no longer a separate primitive for
    # it to fall through to: the dilated scharr edge that used to draw it, and
    # the contrast stretch that lifted its gradient magnitude back to full
    # opacity, both went once the band covered every position Photoshop can
    # write (#799). That leaves it indistinguishable from a stated outset
    # stroke, which is why it says so in the log rather than only in the
    # canvas stroke_bbox() reserved for it.
    limits = _BANDS.get(style)
    if limits is None:
        logger.debug("Unrecognised stroke position %r; drawing it as outset", style)
        limits = _UNRECOGNISED
    lo, hi = limits[0] * size, limits[1] * size
    distance = _signed_distance(shape[:, :, 0])
    return color, np.expand_dims(_distance_band(distance, lo, hi), 2)
