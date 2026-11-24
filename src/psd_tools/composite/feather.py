"""Layer-mask feather.

Photoshop renders a feathered mask as the hard mask blurred by three box
passes, each ``2 * feather`` wide, along both axes.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

# Photoshop's own limit on the Feather property.
MAX_FEATHER = 1000.0

# Per grown pixel: the float64 area and cumulative sum, the interpolated window
# ends and their differences, and the vector mask drawn beside them.
BLUR_BYTES = 72

Box = tuple[int, int, int, int]


def feather_radius(value: float | None) -> float:
    """The feather to render, ``0.0`` for none.

    A value that is unset, not finite or not positive draws no blur; the file
    supplies it, so it is bounded rather than trusted.
    """
    if value is None or not math.isfinite(value) or value <= 0.0:
        return 0.0
    return min(float(value), MAX_FEATHER)


def grown_viewport(viewport: Box, feather: float) -> Box:
    """``viewport`` grown by what ``feather`` reaches, the box a blur reads from."""
    reach = 3 * math.ceil(feather)
    return (
        viewport[0] - reach,
        viewport[1] - reach,
        viewport[2] + reach,
        viewport[3] + reach,
    )


def _pass_half_width(feather: float) -> float:
    """The half-width of each box pass, for three passes of variance ``feather ** 2``.

    A pass averages whole pixels, which widens it past the continuous box it
    is named for, and by more the smaller the feather is; the half-width that
    cancels this is found by bisection, as the pass's variance only grows with
    it.
    """
    reach = math.ceil(feather)
    cells = np.arange(-reach - 1, reach + 2, dtype=np.float64)

    def variance(half: float) -> float:
        overlap = np.clip(
            np.minimum(cells + 0.5, half) - np.maximum(cells - 0.5, -half), 0.0, None
        )
        return float((overlap * cells**2).sum() / overlap.sum())

    low, high = 0.5, float(reach)
    if 3.0 * variance(low) >= feather**2:
        return low
    for _ in range(40):
        middle = (low + high) / 2.0
        if 3.0 * variance(middle) < feather**2:
            low = middle
        else:
            high = middle
    return high


def _box_pass(
    values: np.ndarray, start: int, target: tuple[int, int], half: float
) -> np.ndarray:
    """Average ``values`` over a window ``2 * half`` wide, along the last axis.

    ``values`` starts at ``start`` and is zero beyond its ends; ``target`` is
    the ``(first, last)`` range of the result. Each sample is a unit-wide cell,
    so the window integrates the cumulative sum exactly, partial cells at both
    ends included.
    """
    first, last = target[0], target[1]
    count = values.shape[-1]
    cumulative = np.zeros((*values.shape[:-1], count + 1), dtype=np.float64)
    np.cumsum(values, axis=-1, out=cumulative[..., 1:], dtype=np.float64)
    centers = np.arange(first, last, dtype=np.float64) + 0.5 - start

    def integral(position: np.ndarray) -> np.ndarray:
        position = np.clip(position, 0.0, float(count))
        cell = np.minimum(np.floor(position).astype(np.intp), count - 1)
        fraction = position - cell
        low = np.take(cumulative, cell, axis=-1)
        high = np.take(cumulative, cell + 1, axis=-1)
        return low + fraction * (high - low)

    return (integral(centers + half) - integral(centers - half)) / (2.0 * half)


def blurred_coverage(
    viewport: Box,
    bbox: Box,
    values: np.ndarray,
    background: float,
    feather: float,
    domain: Box | None = None,
    check: Callable[[int, int], None] | None = None,
) -> np.ndarray:
    """A mask feathered by ``feather``, on ``viewport``.

    ``values`` is the mask over ``bbox``; elsewhere it is ``background``. With a
    ``domain``, the mask is that box and the edge pixel continues past it, as
    the blur of a canvas does; without, the plane is ``background`` all round.
    The blur reaches past ``bbox``. ``check`` is called with the width and
    height of the working array before it is allocated.
    """
    box = grown_viewport(viewport, feather)
    if check is not None:
        check(box[2] - box[0], box[3] - box[1])

    columns = np.arange(box[0], box[2])
    rows = np.arange(box[1], box[3])
    if domain is not None:
        columns = np.clip(columns, domain[0], domain[2] - 1)
        rows = np.clip(rows, domain[1], domain[3] - 1)
    inside_x = np.flatnonzero((columns >= bbox[0]) & (columns < bbox[2]))
    inside_y = np.flatnonzero((rows >= bbox[1]) & (rows < bbox[3]))

    result = np.full(
        (viewport[3] - viewport[1], viewport[2] - viewport[0], 1),
        background,
        dtype=np.float32,
    )
    if not len(inside_x) or not len(inside_y):
        return result
    area = np.zeros((len(rows), len(columns)), dtype=np.float64)
    area[np.ix_(inside_y, inside_x)] = (
        values[:, :, 0][np.ix_(rows[inside_y] - bbox[1], columns[inside_x] - bbox[0])]
        - background
    )
    if not area.any():
        return result

    # Each pass needs one reach of input either side of what it returns, so
    # three passes shrink the grown box back to the viewport.
    step = math.ceil(feather)
    half = _pass_half_width(feather)
    for pass_number in range(1, 4):
        area = _box_pass(
            area,
            box[0] + (pass_number - 1) * step,
            (box[0] + pass_number * step, box[2] - pass_number * step),
            half,
        )
    area = np.ascontiguousarray(area.T)
    for pass_number in range(1, 4):
        area = _box_pass(
            area,
            box[1] + (pass_number - 1) * step,
            (box[1] + pass_number * step, box[3] - pass_number * step),
            half,
        )
    result[:, :, 0] += area.T.astype(np.float32)
    return result
