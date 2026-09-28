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

:py:func:`draw_stroke_effect_split` is the same stroke with its coverage
divided at the layer's boundary, which is what the compositor takes: the two
sides of that boundary are composited differently. Compositing is the only
caller that needs the division, so the undivided spelling above stays.

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
from psd_tools.composite.utils import divide
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

# Below this fraction of active pixels within the region a bounding-box crop
# would cover, :py:func:`_nearest_boundary` skips the erosion and falls back
# to its per-offset loop (#895): a thin outline on a much bigger canvas has
# active pixels too sparse within that box for the erosion to pay for itself,
# while a filled shape's boundary band fills enough of it that it does.
_DENSE_EROSION_DENSITY = 0.15


def _enum(desc: Descriptor, key: bytes) -> bytes:
    """The enum ``key`` names, or ``b""`` if the descriptor does not carry one.

    Both keys read through this -- the stroke's position and its paint type --
    already have a defined answer for an enum neither table below knows, so a
    key that is missing or holds something other than an ``Enumerated`` costs
    nothing new to tolerate: it joins the unrecognised value it cannot be told
    apart from. Reading it straight off instead turned a descriptor psd-tools
    did not write into an ``AttributeError`` out of a composite (#826). ``b""``
    rather than None so it takes that fallback without a branch of its own; no
    real enum can collide with it, Photoshop writing every one as four bytes.
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


def _prune_offsets(
    rows: np.ndarray,
    cols: np.ndarray,
    span: int,
    offsets: np.ndarray,
    lengths: np.ndarray,
    partial_pad: np.ndarray,
    near_pad: np.ndarray,
    outward: bool,
) -> np.ndarray:
    """``min``/``max`` of ``near[p] +/- |x - p|`` over offsets, pruning early.

    ``near`` never leaves ``[-0.5, 0.5]``, so once a pixel's running best is
    at least as good as ``length - 0.5`` (``outward``) or ``0.5 - length``
    (inward), no offset from here on -- ``offsets`` sorted by ascending
    ``length`` -- can improve it: the best any of them could still state is
    exactly that bound. A pixel this true of drops out of the working set,
    so offsets past it never revisit it. This is exact, not a bound in place
    of one: what it prunes could not have changed the answer.

    Most pixels resolve within a few offsets of their own unweighted nearest
    partial pixel, so the working set thins fast on a smooth boundary --
    which is the common case, a circle or a diagonal edge on a canvas much
    bigger than the stroke. It still runs every offset within ``span`` for a
    pixel that never resolves, so this does not change the loop's worst case.
    """
    prows, pcols = rows + span, cols + span
    result = np.empty(rows.shape, dtype=np.float32)
    order = np.arange(rows.size)
    best = np.full(rows.shape, np.inf if outward else -np.inf, dtype=np.float32)

    for (down, across), length in zip(offsets, lengths):
        if order.size == 0:
            break
        row, col = prows + down, pcols + across
        states = partial_pad[row, col]
        stated = near_pad[row, col]
        if outward:
            best = np.minimum(best, np.where(states, stated + length, np.inf))
            resolved = best <= (length - 0.5)
        else:
            best = np.maximum(best, np.where(states, stated - length, -np.inf))
            resolved = best >= (0.5 - length)
        if resolved.any():
            result[order[resolved]] = best[resolved]
            keep = ~resolved
            prows, pcols, best, order = (
                prows[keep],
                pcols[keep],
                best[keep],
                order[keep],
            )

    if order.size:
        result[order] = best
    return result


def _nearest_boundary(
    alpha: np.ndarray, partial: np.ndarray, near: np.ndarray, radius: float
) -> np.ndarray:
    """The nearest boundary within ``radius``, as distance, negative inside.

    Every partial pixel states one boundary, ``near`` from its own centre and
    so up to half a pixel either side of it. A pixel with no coverage of its
    own is ``min`` over those of ``|x - p| + near[p]`` -- the nearest
    *boundary*, which is not the nearest pixel stating one: the offsets span a
    pixel, so a pixel one further away can win. Taking the nearest pixel's
    word for it leaves the answer to whichever of two equidistant pixels a
    distance transform happens to return, which is not a choice the mask
    makes; Photoshop's render of such a mask is mirror-exact, and this is the
    value it renders.

    That minimum is a grey erosion of ``near`` by a cone -- ``scipy``'s
    ``grey_erosion`` with a disc footprint and ``-length`` as the structuring
    function, which computes it without a Python-level pass per offset. The
    dual, the nearest boundary from *inside*, is the same erosion of
    ``-near``, negated.

    An erosion runs the disc footprint over every pixel of whatever it is
    given, so it only pays for itself where ``active`` -- the pixels an
    answer is wanted for -- is a healthy share of the region a crop bounding
    the partial pixels would cover: a filled shape's boundary, where the band
    the footprint runs over is close to that box already. Where the boundary
    is a thin outline on a much bigger canvas -- a circle, an ellipse, a
    diagonal edge -- that box is close to the shape's own bounding box while
    ``active`` is a sliver of it, and running the erosion there would cost
    more than it saves.

    Below :py:data:`_DENSE_EROSION_DENSITY`, :py:func:`_prune_offsets` runs
    the same minimum as a loop instead, one offset at a time in ascending
    length, dropping each pixel out as soon as no offset still to come could
    improve its answer -- exactly, per the bound in its own docstring. A
    smooth boundary resolves most pixels within a handful of offsets of their
    own nearest partial pixel, which is the common shape of this branch's
    input, but a pixel that never resolves still costs every offset within
    ``radius``: pruning cuts the constant this branch runs at, not the shape
    of its worst case, which stays the one the erosion branch exists to
    avoid.

    Both branches read and write through the same crop the density above is
    measured on, padded arrays included, rather than the whole of ``alpha``:
    everything either one needs already sits inside it, so this is memory
    tied to the shape's own extent even when the canvas around it is much
    bigger.
    """
    from scipy.ndimage import (  # type: ignore[import-untyped]  # noqa: PLC0415
        distance_transform_edt,
        grey_erosion,
    )

    # Beyond the reach of any boundary, and so of any band: infinitely far
    # out from a clear pixel and infinitely far in from an opaque one.
    field = np.where(partial, near, np.where(alpha >= 1, -np.inf, np.inf)).astype(
        np.float32
    )
    active = (distance_transform_edt(~partial) <= radius) & ~partial
    if not active.any():
        return field

    span = math.ceil(radius)
    height, width = alpha.shape
    rows_p, cols_p = np.nonzero(partial)
    r0, r1 = max(rows_p.min() - span, 0), min(rows_p.max() + span + 1, height)
    c0, c1 = max(cols_p.min() - span, 0), min(cols_p.max() + span + 1, width)
    crop = (slice(r0, r1), slice(c0, c1))
    density = active.sum() / ((r1 - r0) * (c1 - c0))

    if density >= _DENSE_EROSION_DENSITY:
        sub_partial, sub_near, sub_alpha, sub_active = (
            partial[crop],
            near[crop],
            alpha[crop],
            active[crop],
        )
        grid = np.mgrid[-span : span + 1, -span : span + 1]
        length = np.hypot(*grid).astype(np.float32)
        kwargs = {
            "footprint": length <= radius,
            "structure": -length,
            "mode": "constant",
        }
        outward = grey_erosion(
            np.where(sub_partial, sub_near, np.inf).astype(np.float32),
            cval=np.inf,
            **kwargs,
        )
        inward = -grey_erosion(
            np.where(sub_partial, -sub_near, np.inf).astype(np.float32),
            cval=np.inf,
            **kwargs,
        )
        stated = np.where(sub_alpha >= 1, inward, outward)
        field[crop] = np.where(sub_active, stated, field[crop])
        return field

    offsets = np.mgrid[-span : span + 1, -span : span + 1].reshape(2, -1).T
    lengths = np.hypot(offsets[:, 0], offsets[:, 1]).astype(np.float32)
    within = lengths <= radius
    offsets, lengths = offsets[within], lengths[within]
    ascending = np.argsort(lengths, kind="stable")
    offsets, lengths = offsets[ascending], lengths[ascending]

    # partial's own pixels sit inside `crop` by construction (it is padded out
    # to `span` around their bounding box), and so does every active pixel --
    # nothing an offset lookup needs is outside it. Padding that crop, rather
    # than the whole canvas, is what keeps this branch's own memory use tied
    # to the shape's extent instead of the much bigger canvas around it.
    sub_partial, sub_near, sub_alpha, sub_active = (
        partial[crop],
        near[crop],
        alpha[crop],
        active[crop],
    )
    flat = np.flatnonzero(sub_active)
    rows, cols = np.unravel_index(flat, sub_active.shape)
    partial_pad = np.pad(sub_partial, span, constant_values=False)
    near_pad = np.pad(sub_near, span, constant_values=0.0)
    inside = (sub_alpha >= 1).ravel()[flat]

    outward = _prune_offsets(
        rows[~inside],
        cols[~inside],
        span,
        offsets,
        lengths,
        partial_pad,
        near_pad,
        outward=True,
    )
    inward = _prune_offsets(
        rows[inside],
        cols[inside],
        span,
        offsets,
        lengths,
        partial_pad,
        near_pad,
        outward=False,
    )
    field[r0 + rows[~inside], c0 + cols[~inside]] = outward
    field[r0 + rows[inside], c0 + cols[inside]] = inward
    return field


def _signed_distance(alpha: np.ndarray, reach: float | None = None) -> np.ndarray:
    """Distance from each pixel to the mask boundary, negative inside.

    Photoshop reads that boundary off the mask's **coverage**, not off its 0.5
    iso-contour: a pixel at ``alpha`` states that the boundary runs
    ``0.5 - alpha`` from its own centre, and its neighbours measure outward
    from there. On a hard-edged mask the two readings name the same line --
    one partial pixel, and the boundary is where its coverage puts it. On a
    *feathered* one they diverge without limit: a 16 px alpha ramp runs 8 px
    from the iso-contour at either end and half a pixel from the boundary
    everywhere, so a stroke of any size covers all of it.
    ``effects/feathered-stroke.psd`` and
    ``effects/antialiased-stroke-edge.psd`` are the fixtures this is measured
    against (#799).

    Coverage says nothing about an edge that has none, so a mask stepping
    0 -> 1 keeps the exact Euclidean distance to the iso-contour, ``base``.
    One mask can carry both -- a shape antialiased along one side and butted
    against its own bounding box along another -- so the two are chosen
    between per pixel, by which boundary is nearer. Seeding a single transform
    from both instead costs the corners, where a feathered edge meets a hard
    one.

    A pixel outside the partial band takes the nearest of the boundaries the
    band states, which :py:func:`_nearest_boundary` solves for outright. What
    stays approximate is that a partial pixel's ``near`` is applied along the
    line to that pixel rather than along the boundary's own normal, which
    parts company with the truth around a curve the way
    :py:func:`_distance_band` does when it paints the arc.

    A mask that is flat at 0 or 1 has no boundary at all. That is not a case
    to fall through: ``distance_transform_edt`` is undefined on an input with
    no zeros and reports distances to a phantom feature off the array corner,
    which a band paints as a wedge in the corner of the canvas. Being
    uniformly infinitely far from the boundary leaves every band empty, which
    is right. A mask flat at a *partial* value is not one of these -- every
    pixel of it states a boundary, so it takes a stroke over all of it.
    """
    if reach is None:
        # No band named, so no bound: far enough that nothing is out of range.
        reach = float(math.hypot(*alpha.shape))
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
    # from the nearest boundary any of them states.
    near = (0.5 - alpha).astype(np.float32)
    stated = _nearest_boundary(alpha, partial, near, reach)
    if not hard.any():
        return stated

    # ``base`` is exact along a hard step, and is the better answer for any
    # pixel nearer one of them than it is to the partial band.
    distance = distance_transform_edt(~partial)
    to_hard = distance_transform_edt(~hard)
    field = np.where(partial, near, np.where(distance <= to_hard, stated, base))
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
    """The stroke's paint and the coverage it puts it on."""
    color, coverage, _ = draw_stroke_effect_split(viewport, shape, desc, psd)
    return color, coverage


def draw_stroke_effect_split(
    viewport: tuple[int, int, int, int],
    shape: np.ndarray,
    desc: Descriptor,
    psd: "PSDProtocol",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """:py:func:`draw_stroke_effect`, with the coverage split at the boundary.

    The third array is the part of the band that falls *inside* the layer,
    which is what the band's two halves are composited differently: the inside
    paints over the layer and knocks out what it covers, the rest paints beside
    it (#846). An inset band is wholly inside and an outset one wholly outside;
    only a centered stroke has both.

    The split is a share of the band rather than two bands drawn separately, so
    the two always sum to what :py:func:`draw_stroke_effect` returns. Drawn
    separately they would not: :py:func:`_distance_band` multiplies the two
    edges' ramps, which is the area of a pixel cut by a straight edge only
    while the band is at least a pixel wide, and halving a band halves both
    halves' widths.

    The two can be views of one array, since an inset band is the whole of the
    coverage; both are read and neither is written to.
    """
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
        return (
            color,
            np.zeros((height, width, 1), dtype=np.float32),
            np.zeros((height, width, 1), dtype=np.float32),
        )

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
    # all, takes the outset band (#799). That leaves it indistinguishable from
    # a stated outset stroke, which is why it says so in the log rather than
    # only in the canvas stroke_bbox() reserved for it.
    limits = _BANDS.get(style)
    if limits is None:
        logger.debug("Unrecognised stroke position %r; drawing it as outset", style)
        limits = _UNRECOGNISED
    lo, hi = limits[0] * size, limits[1] * size
    # A boundary further out than the band's widest limit, plus the half
    # pixel a partial pixel can state either side of itself, cannot show.
    distance = _signed_distance(shape[:, :, 0], max(abs(lo), abs(hi)) + 1.0)
    coverage = _distance_band(distance, lo, hi)
    if hi <= 0.0:
        inside = coverage
    elif lo >= 0.0:
        inside = np.zeros_like(coverage)
    else:
        within = _distance_band(distance, lo, 0.0)
        beyond = _distance_band(distance, 0.0, hi)
        inside = coverage * divide(within, within + beyond, fill=0.0)
    return color, np.expand_dims(coverage, 2), np.expand_dims(inside, 2)
