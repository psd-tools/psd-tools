# mypy: disable-error-code="assignment"
"""
Layer effects rendering.

This module implements rendering for Photoshop layer effects (also known as
layer styles). Effects are non-destructive visual enhancements applied to layers
such as strokes, shadows, glows, and overlays.

**Note**: Effects rendering requires scipy. Install it with::

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
- A shape layer's stroke follows its path interior but traces the stored coverage
  at the path's edge
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
from itertools import chain, pairwise
from typing import TYPE_CHECKING

import numpy as np

from psd_tools.api.utils import AllocBudget, check_pixel_size
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

# The widest stroke Photoshop writes; a larger size can only be a forged one.
_MAX_STROKE_SIZE = 250.0

# What a stroke canvas costs per pixel at its peak: the signed-distance
# transients (the transform's float64 planes and the seed index) dwarf the
# float32 canvas and colour planes, so a budget is checked against this, not
# 4 bytes. It is the peak RSS of the widest stroke on a thick ring and on a
# fully feathered mask, with headroom: tracemalloc misses the transform's own
# buffers.
_STROKE_BYTES = 128

# Candidate seeds :py:func:`_nearest_boundary` holds at once, which bounds the
# memory of its queries whatever the reach (#897).
_BATCH_CANDIDATES = 1 << 18


def _enum(desc: Descriptor, key: bytes) -> bytes:
    """The enum ``key`` names, or ``b""`` if the descriptor does not carry one.

    A missing or non-``Enumerated`` value joins the unrecognised enums the
    callers already handle, instead of raising ``AttributeError`` (#826).
    ``b""`` rather than None so it takes that fallback without a branch; no real
    enum collides with it, being four bytes.
    """
    return getattr(desc.get(key), "enum", b"")


def _stroke_size(desc: Descriptor) -> float:
    """The descriptor's stroke size, held to what Photoshop can write."""
    size = float(desc.get(Key.SizeKey, 1.0))
    if not math.isfinite(size):
        raise ValueError("Stroke size is not finite.")
    return min(size, _MAX_STROKE_SIZE)


def stroke_bbox(
    bbox: tuple[int, int, int, int],
    desc: Descriptor,
    max_alloc_bytes: AllocBudget | None = None,
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

    A size above what Photoshop writes is drawn at that limit. Raises
    :class:`ValueError` when the size is not finite or the grown box is over
    the per-axis limit or ``max_alloc_bytes``, which the callers read as an
    unreadable stroke.
    """
    if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
        return bbox
    limits = _BANDS.get(_enum(desc, Key.Style), _UNRECOGNISED)
    reach = limits[1]
    # ceil() because a fractional stroke still covers the pixel it falls in.
    # The +1 is the uncovered pixel the edge is measured against.
    size = _stroke_size(desc)
    margin = math.ceil(size * reach) + 1
    grown = (bbox[0] - margin, bbox[1] - margin, bbox[2] + margin, bbox[3] + margin)
    # The size is the file's, so the box it grows is checked before anything is
    # allocated on it. A box that fails is an unreadable stroke to both callers.
    if grown[0] < grown[2] and grown[1] < grown[3]:
        # A gradient paint peaks above the distance field it is drawn under.
        per_pixel = _STROKE_BYTES
        if _enum(desc, Key.PaintType) == Enum.GradientFill:
            per_pixel = max(per_pixel, paint.GRADIENT_FILL_BYTES)
        width, height = grown[2] - grown[0], grown[3] - grown[1]
        check_pixel_size(
            width,
            height,
            max_alloc_bytes=max_alloc_bytes,
            estimated_bytes=width * height * per_pixel,
            warn=False,
        )
    return grown


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
    value it renders. The dual, the nearest boundary from *inside*, is the
    same minimum over ``|x - p| - near[p]``, negated.

    A seed farther than ``d0 + spread`` from a pixel, ``d0`` being the
    distance to its nearest seed and ``spread`` the range of ``near``, costs
    more than that nearest seed does, so only the seeds in that annulus are
    evaluated, found with a k-d tree. Cost and memory follow the seeds in it
    rather than ``radius`` squared, and the batches below bound the lists a
    query returns.

    The result is the float32 arithmetic of a full search over every offset
    within ``radius``: the lengths are rounded before the cutoff, which is why
    the query is widened by a margin and the cutoff is applied again to what
    it returns.
    """
    from scipy.ndimage import (  # type: ignore[import-untyped]  # noqa: PLC0415
        distance_transform_edt,
    )
    from scipy.spatial import cKDTree  # type: ignore[import-untyped]  # noqa: PLC0415

    field = np.where(partial, near, np.where(alpha >= 1, -np.inf, np.inf)).astype(
        np.float32
    )
    distance = distance_transform_edt(~partial)
    active = (distance <= radius) & ~partial
    if not active.any():
        return field

    width = alpha.shape[1]
    pixels = np.flatnonzero(active)
    del active
    spread = float(near[partial].max()) - float(near[partial].min())
    # Lengths are float32 and compared with ``radius`` as such, so a seed can
    # pass at a true length a rounding above it.
    cutoff = max(radius, float(np.float32(radius)))
    margin = max(1e-3, 8.0 * float(np.spacing(np.float32(cutoff + 1.0))))
    queried = np.minimum(distance.ravel()[pixels] + spread, cutoff) + margin
    del distance
    # An annulus one pixel wide holds at most 4 * (2r + 3) + pi * (2r + 1)
    # lattice points, under 12 * (r + 2).
    ends = np.cumsum(12.0 * (queried + 2.0), dtype=np.float32)
    steps = np.arange(0.0, ends[-1] + _BATCH_CANDIDATES, _BATCH_CANDIDATES)
    bounds = np.unique(np.append(np.searchsorted(ends, steps), pixels.size))
    del ends

    seed_pixels = np.flatnonzero(partial)
    seeds = np.empty((seed_pixels.size, 2), dtype=np.float64)
    seeds[:, 0], seeds[:, 1] = np.divmod(seed_pixels, width)
    del seed_pixels
    weights = near[partial]
    tree = cKDTree(seeds, balanced_tree=False, compact_nodes=False, copy_data=False)

    for lo, hi in pairwise(bounds):
        rows, cols = np.divmod(pixels[lo:hi], width)
        inside = alpha[rows, cols] >= 1
        points = np.column_stack([rows, cols]).astype(np.float64)
        found = tree.query_ball_point(points, queried[lo:hi])
        counts = np.fromiter(map(len, found), np.intp, count=hi - lo)
        flat = np.fromiter(chain.from_iterable(found), np.intp, count=counts.sum())
        del found
        owner = np.repeat(np.arange(hi - lo), counts)
        length = np.hypot(*(seeds[flat] - points[owner]).T).astype(np.float32)
        weight = weights[flat]
        # The inward minimum runs over ``length - near`` and is negated below.
        stated = np.where(inside[owner], length - weight, weight + length)
        stated = np.where(length <= radius, stated, np.inf)
        best = np.full(hi - lo, np.inf, dtype=np.float32)
        found_any = counts > 0
        starts = (np.cumsum(counts) - counts)[found_any]
        best[found_any] = np.minimum.reduceat(stated, starts)
        field[rows, cols] = np.where(inside, -best, best)
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
    from scipy.ndimage import (  # type: ignore[import-untyped]  # noqa: PLC0415
        distance_transform_edt,
    )

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

    A distance field has unit gradient, so a linear ramp across one pixel is the
    exact area of a pixel cut by a straight edge, and a fractional width is not
    quantized. Where the band's edge curves, the ramp only approximates it.
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
    size = _stroke_size(desc)

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
