"""Exact-coverage rasterization of filled paths.

The fill of a vector path is rasterized here rather than by aggdraw, which
offsets filled geometry outward by a quarter pixel with a miter contour before
it rasterizes, and so reports a quarter pixel of coverage on every side that
is not there (#844). A stroke is still drawn by aggdraw: its pen is exact -- a
line of width w covers exactly w -- and its joins and caps are work of their
own.

The scheme is the signed-area accumulation used by font rasterizers. Every
segment is cut where it crosses a pixel boundary, so each piece lies in one
cell; a piece rising ``dy`` at mean abscissa ``x`` covers ``dy * (1 - x)`` of
its own cell and the whole of ``dy`` for every cell to its right. Accumulating
both parts and running a prefix sum along each row gives the signed area of
the path in every pixel, exactly -- no sampling, and the same answer wherever
on the grid the path happens to sit.

The one place the area is not the answer is a contour that crosses itself, or
two contours of opposite winding overlapping inside a single pixel: their
signed areas cancel there, and the pixel comes out emptier than the region
really is. Every rasterizer of this family shares that, aggdraw included, and
by a wider margin.
"""

import numpy as np

# Accumulator cells, and segment pieces, held at once. Each band of rows is
# split and summed on its own, so these bound peak memory independently of the
# canvas and of how far the path wanders across it.
_BAND_CELLS = 1 << 22
_BAND_PIECES = 1 << 20

# Flatness of the polyline that stands in for a cubic, in pixels. A chord that
# strays this far from its curve moves the coverage of the pixel it crosses by
# as much, so the bound is set below the 1/255 a channel can hold.
_FLATNESS = 0.002

# Ceiling on the steps one cubic is cut into, for a knot pair whose control
# points sit far enough out to ask for more than its visible arc could use.
_MAX_STEPS = 1000


def _split(
    p0: np.ndarray, p1: np.ndarray, axis: int, lo: float, hi: float
) -> tuple[np.ndarray, np.ndarray]:
    """Cut every segment where coordinate ``axis`` crosses an integer.

    Only the integers in ``[lo, hi]`` are cut at. Outside that range the pixel
    a piece lands in is clamped or dropped anyway, so cutting there would
    multiply the pieces without changing the coverage -- which is also what
    keeps a path with far-off coordinates from exploding: a segment is
    monotone, so it can cross the range at most ``hi - lo`` times.
    """
    c0, c1 = p0[:, axis], p1[:, axis]
    first = np.maximum(np.ceil(np.minimum(c0, c1)), lo)
    last = np.minimum(np.floor(np.maximum(c0, c1)), hi)
    cuts = np.maximum(0.0, last - first + 1.0).astype(np.int64)
    cuts[c0 == c1] = 0

    total_cuts = int(cuts.sum())
    at = np.cumsum(cuts) - cuts
    owner = np.repeat(np.arange(len(p0)), cuts)
    rank = np.arange(total_cuts) - at[owner]
    # The cut coordinates ascend, so a descending segment takes them in
    # reverse to keep the parameters sorted along it.
    descending = c1[owner] < c0[owner]
    crossed = np.where(descending, last[owner] - rank, first[owner] + rank)
    t_cut = (crossed - c0[owner]) / (c1[owner] - c0[owner])
    # One slot of padding, so both ends of a piece can be looked up
    # unconditionally -- including when nothing was cut at all and the lookup
    # is masked away entirely.
    t_cut = np.concatenate([t_cut, np.zeros(1)])

    pieces = cuts + 1
    at_piece = np.cumsum(pieces) - pieces
    owner = np.repeat(np.arange(len(p0)), pieces)
    rank = np.arange(int(pieces.sum())) - at_piece[owner]
    base = at[owner]
    t0 = np.where(rank == 0, 0.0, t_cut[np.clip(base + rank - 1, 0, total_cuts)])
    t1 = np.where(
        rank == pieces[owner] - 1, 1.0, t_cut[np.clip(base + rank, 0, total_cuts)]
    )

    step = (p1 - p0)[owner]
    return p0[owner] + t0[:, None] * step, p0[owner] + t1[:, None] * step


def fill_coverage(polylines: list, width: int, height: int) -> np.ndarray:
    """Area of ``polylines`` inside each pixel, under the non-zero rule.

    Each polyline is an ``(n, 2)`` array of ``(x, y)`` vertices and is closed
    implicitly. Together they describe one path: a subpath wound against its
    neighbour is a hole, which is how Photoshop reads a combined path.
    """
    coverage = np.zeros((max(height, 0), max(width, 0)), dtype=np.float32)
    if width <= 0 or height <= 0:
        return coverage

    # A vertex that is not a number indexes nothing, and cutting against it
    # would overflow the piece counts. Such a contour is dropped whole rather
    # than by the segment: dropped by the segment it would be left open, and
    # an open contour leaks its winding across the rest of every row it
    # touches instead of closing on itself.
    contours = [np.asarray(points, dtype=np.float64) for points in polylines]
    contours = [c for c in contours if len(c) >= 2 and np.isfinite(c).all()]
    if not contours:
        return coverage
    p0 = np.concatenate(contours)
    p1 = np.concatenate([np.roll(c, -1, axis=0) for c in contours])

    stride = width + 3
    band = max(1, min(_BAND_CELLS // stride, _BAND_PIECES // len(p0)))
    highest = np.minimum(p0[:, 1], p1[:, 1])
    lowest = np.maximum(p0[:, 1], p1[:, 1])

    for top in range(0, height, band):
        bottom = min(top + band, height)
        reaches = (lowest > top) & (highest < bottom)
        if not reaches.any():
            continue
        q0, q1 = _split(p0[reaches], p1[reaches], 1, top, bottom)
        q0, q1 = _split(q0, q1, 0, 0, width)

        middle = 0.5 * (q0 + q1)
        row = np.floor(middle[:, 1]).astype(np.int64)
        inside = (row >= top) & (row < bottom)
        if not inside.any():
            continue
        row, middle = row[inside] - top, middle[inside]
        rise = (q1[:, 1] - q0[:, 1])[inside]

        # A piece to the left of the canvas still turns every pixel of its
        # row, so it is kept at column -1; one to the right lands past the
        # last column and falls out of the slice below.
        col = np.clip(np.floor(middle[:, 0]), -1, width).astype(np.int64)
        share = np.clip(middle[:, 0] - col, 0.0, 1.0)

        cell = row * stride + (col + 1)
        cells = (bottom - top) * stride
        acc = np.bincount(cell, weights=rise * (1.0 - share), minlength=cells)
        acc += np.bincount(cell + 1, weights=rise * share, minlength=cells)
        acc = acc[:cells].reshape(bottom - top, stride)
        np.cumsum(acc, axis=1, out=acc)
        np.abs(acc, out=acc)
        np.clip(acc, 0.0, 1.0, out=acc)
        coverage[top:bottom] = acc[:, 1 : width + 1]
    return coverage


def flatten_cubics(
    p0: np.ndarray, c0: np.ndarray, c1: np.ndarray, p1: np.ndarray
) -> np.ndarray:
    """Replace a run of cubic segments by a polyline through all of them.

    Each curve is cut into as many equal steps in ``t`` as its own curvature
    asks for: subdivided uniformly into ``n`` steps a cubic stays within
    ``3 * m / (4 * n**2)`` of the curve, where ``m`` is the larger of the two
    second differences of its control points, so ``n`` follows from
    :py:data:`_FLATNESS`. The second difference is measured as a length; taken
    per axis instead it understates the curvature of a diagonal bend, and the
    chord then strays up to 1.26x past the bound.

    A curve whose control points lie on its own chord is already a straight
    line and takes one step, however long it is. PSD stores a straight edge as
    a cubic with both handles on the anchors, so that is most of the corpus,
    and the second difference alone would spend hundreds of points on it.

    The end point of each curve is left to the next one, which starts there;
    the caller supplies the last one, or closes the contour onto the first.
    """
    chord = p1 - p0
    span = np.linalg.norm(chord, axis=1)

    # Distance of each handle from the chord. Within the frame where the chord
    # is an axis a cubic reaches at most 3/4 of the larger of the two.
    def across(handle: np.ndarray) -> np.ndarray:
        offset = handle - p0
        return np.abs(chord[:, 0] * offset[:, 1] - chord[:, 1] * offset[:, 0])

    away = np.maximum(across(c0), across(c1)) / np.where(span > 0, span, 1.0)
    straight = 0.75 * away <= _FLATNESS

    second = np.maximum(
        np.linalg.norm(p0 - 2 * c0 + c1, axis=1),
        np.linalg.norm(c0 - 2 * c1 + p1, axis=1),
    )
    steps = np.ceil(np.sqrt(0.75 * second / _FLATNESS))
    steps = np.where(straight, 1.0, steps)
    steps = np.clip(steps, 1, _MAX_STEPS).astype(np.int64)

    curve = np.repeat(np.arange(len(p0)), steps)
    rank = np.arange(int(steps.sum())) - np.repeat(np.cumsum(steps) - steps, steps)
    t = (rank / steps[curve])[:, None]
    s = 1.0 - t
    return (
        s * s * s * p0[curve]
        + 3 * s * s * t * c0[curve]
        + 3 * s * t * t * c1[curve]
        + t * t * t * p1[curve]
    )
