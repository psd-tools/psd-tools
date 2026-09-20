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

Coverage is read under the **even-odd** rule, which is the one PSD uses: a
region enclosed an even number of times is outside. The prefix sum gives the
winding number, and folding it into ``[0, 1]`` rather than clamping it there
is what makes the rule even-odd rather than non-zero. The two differ only
where a pixel is wound more than once -- which Photoshop does not author for
itself, since it cuts a hole by reversing the subpath that makes it, but
which a file from elsewhere can carry, and which Photoshop renders as a hole
either way (see ``tests/psd_files/path-operations/nested-subpath-winding``).

Where a single pixel holds more than one winding at once -- a contour
crossing itself inside it, or two contours overlapping within it -- the
answer is approximate, because a prefix sum carries the area-weighted mean
winding of the pixel and not the distribution it came from. Aligned to the
pixel grid the same overlap is exact; it is the part of it that falls inside
one pixel that is not. Over every multi-subpath component in the test corpus
the error stays under 0.002, and the union aggdraw was asked for instead is
off by a full 1.0 on the same shapes. Measured in #858.
"""

import numpy as np

# Accumulator cells, and segment pieces, held at once. Rows are split and
# summed a band at a time, and the pieces of a band are cut into columns a
# span at a time, so these bound peak working memory whatever the canvas is
# and however far the path wanders across it. The result array is separate,
# and is the size the caller asked for.
_BAND_CELLS = 1 << 22
_BAND_PIECES = 1 << 19

# Flatness of the polyline that stands in for a cubic, in pixels. A chord that
# strays this far from its curve moves the coverage of the pixel it crosses by
# as much, so the bound is set below the 1/255 a channel can hold.
_FLATNESS = 0.002

# Ceiling on the steps one cubic is cut into, for a knot pair whose control
# points sit far enough out to ask for more than its visible arc could use.
_MAX_STEPS = 1000


def _cuts(
    c0: np.ndarray, c1: np.ndarray, lo: float, hi: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Where, and how often, each segment crosses an integer in ``[lo, hi]``.

    Outside that range the pixel a piece lands in is clamped or dropped
    anyway, so cutting there would multiply the pieces without changing the
    coverage -- which is also what keeps a path with far-off coordinates from
    exploding: a segment is monotone, so it can cross the range at most
    ``hi - lo`` times however large its coordinates are.
    """
    first = np.maximum(np.ceil(np.minimum(c0, c1)), lo)
    last = np.minimum(np.floor(np.maximum(c0, c1)), hi)
    counts = np.maximum(0.0, last - first + 1.0).astype(np.int64)
    counts[c0 == c1] = 0
    return first, last, counts


def _chunks(sizes: np.ndarray, budget: int) -> list[tuple[int, int]]:
    """Split a run of items into spans whose ``sizes`` sum to about ``budget``.

    One span whenever the whole run fits, which is the ordinary case.
    """
    running = np.cumsum(sizes)
    if not len(running) or running[-1] <= budget:
        return [(0, len(sizes))]
    spans, start = [], 0
    while start < len(sizes):
        base = running[start - 1] if start else 0
        stop = max(
            int(np.searchsorted(running, base + budget, side="right")), start + 1
        )
        spans.append((start, stop))
        start = stop
    return spans


def _split(
    p0: np.ndarray, p1: np.ndarray, axis: int, lo: float, hi: float
) -> tuple[np.ndarray, np.ndarray]:
    """Cut every segment where coordinate ``axis`` crosses an integer."""
    c0, c1 = p0[:, axis], p1[:, axis]
    first, last, cuts = _cuts(c0, c1, lo, hi)

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
        rows0, rows1 = _split(p0[reaches], p1[reaches], 1, top, bottom)

        # Cutting those at every column they cross multiplies them again, by
        # as much as the width of the canvas for a single piece that spans
        # it. Banding the rows does not bound that, so the second cut is
        # taken a span of pieces at a time, each span sized from the cuts it
        # is about to make.
        cells = (bottom - top) * stride
        acc = np.zeros(cells)
        columns = _cuts(rows0[:, 0], rows1[:, 0], 0, width)[2] + 1
        for start, stop in _chunks(columns, _BAND_PIECES):
            q0, q1 = _split(rows0[start:stop], rows1[start:stop], 0, 0, width)

            middle = 0.5 * (q0 + q1)
            row = np.floor(middle[:, 1]).astype(np.int64)
            inside = (row >= top) & (row < bottom)
            if not inside.any():
                continue
            row, middle = row[inside] - top, middle[inside]
            rise = (q1[:, 1] - q0[:, 1])[inside]

            # A piece left of the canvas still turns every pixel of its row.
            # Column -1 is where it is kept, though the ``share`` clamp just
            # below would carry it into column 0 on its own; one to the right
            # lands past the last column and falls out of the slice below.
            col = np.clip(np.floor(middle[:, 0]), -1, width).astype(np.int64)
            share = np.clip(middle[:, 0] - col, 0.0, 1.0)

            cell = row * stride + (col + 1)
            acc += np.bincount(cell, weights=rise * (1.0 - share), minlength=cells)
            acc += np.bincount(cell + 1, weights=rise * share, minlength=cells)

        rows = acc[:cells].reshape(bottom - top, stride)
        np.cumsum(rows, axis=1, out=rows)
        np.abs(rows, out=rows)
        # Even-odd: a pixel wound twice is outside again, so the winding is
        # folded into [0, 1] rather than clamped there. Clamping is the
        # non-zero rule, and Photoshop does not use it -- see the module
        # docstring.
        np.mod(rows, 2.0, out=rows)
        np.subtract(1.0, np.abs(rows - 1.0), out=rows)
        coverage[top:bottom] = rows[:, 1 : width + 1]
    return coverage


def flatten_cubics(
    p0: np.ndarray, c0: np.ndarray, c1: np.ndarray, p1: np.ndarray
) -> np.ndarray:
    """Replace a run of cubic segments by a polyline through all of them.

    Each curve is cut into as many equal steps in ``t`` as its own curvature
    asks for: subdivided uniformly into ``n`` steps a cubic stays within
    ``3 * m / (4 * n**2)`` of the curve, where ``m`` is the larger of the two
    second differences of its control points, so ``n`` follows from
    ``_FLATNESS``. Above ``_MAX_STEPS`` that bound is best-effort: a curve
    whose handles reach thousands of pixels away is cut into a thousand steps
    and no more. The second difference is measured as a length; taken per
    axis instead it understates the curvature of a diagonal bend by as much
    as a factor of root two, and the chord strays past the bound with it --
    1.26x over random cubics, and 1.40x for one written to provoke it.

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
    length = np.where(span > 0, span, 1.0)

    def across(handle: np.ndarray) -> np.ndarray:
        offset = handle - p0
        return np.abs(chord[:, 0] * offset[:, 1] - chord[:, 1] * offset[:, 0]) / length

    def along(handle: np.ndarray) -> np.ndarray:
        offset = handle - p0
        return (chord[:, 0] * offset[:, 0] + chord[:, 1] * offset[:, 1]) / length**2

    away = np.maximum(across(c0), across(c1))
    # Distance from the supporting line is not enough. A handle that lies on
    # that line but past an end point sends the curve out along it and back,
    # which is not a chord however flat it measures; requiring both handles
    # to fall between the end points puts the curve in their convex hull.
    between = (
        (along(c0) >= 0.0)
        & (along(c0) <= 1.0)
        & (along(c1) >= 0.0)
        & (along(c1) <= 1.0)
    )
    # A chord of no length is not a straight curve either: both handles
    # measure zero against it however far off they reach, so the loop a cubic
    # makes when it comes back to its own start would be discarded.
    straight = (0.75 * away <= _FLATNESS) & (span > 0) & between

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
