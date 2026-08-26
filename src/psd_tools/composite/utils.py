"""Utility functions for composite operations."""

from typing import Any, overload

import numpy as np
from numpy.typing import NDArray

from psd_tools.api.layers import Layer
from psd_tools.constants import Tag


# A divisor or a fill is usually a canvas, but ``draw_stroke_effect()``
# normalizes by a NumPy scalar and every caller may pass a plain float.
_Scalable = NDArray[np.floating] | np.floating[Any] | float


def divide(
    a: NDArray[np.floating],
    b: _Scalable,
    fill: _Scalable = 1.0,
) -> NDArray[np.floating]:
    """Divide ``a`` by ``b``, substituting ``fill`` where ``b`` is not positive.

    Every divisor in the compositor is an alpha or a coverage, so a zero one
    means "nothing here" rather than an arithmetic accident, and the quotient
    is undefined at exactly those pixels. What belongs there instead is the
    caller's to say: un-premultiplying a color wants a color to fall back to,
    while a ratio of two alphas wants an opacity. The default 1.0 reads as
    white in normalized color space and as fully opaque in alpha, which is what
    every caller that does not pass ``fill`` relies on.

    ``fill`` may be a full canvas as well as a scalar, so a caller can fall
    back per pixel to something it already has in hand.

    Skipping those pixels via ``where=`` also avoids computing an invalid
    quotient only to overwrite it -- the divisor is never negative here, so
    ``b > 0`` and "b is nonzero" are the same test.
    """
    out = np.full(
        np.broadcast_shapes(np.shape(a), np.shape(b)),
        fill,
        dtype=np.result_type(a, b),
    )
    return np.divide(a, b, out=out, where=np.asarray(b) > 0)


def intersect(
    a: tuple[int, int, int, int], b: tuple[int, int, int, int]
) -> tuple[int, int, int, int]:
    """Calculate intersection of two bounding boxes."""
    inter = (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
    if inter[0] >= inter[2] or inter[1] >= inter[3]:
        return (0, 0, 0, 0)
    return inter


def has_fill(layer: Layer) -> bool:
    """Check if layer has fill settings."""
    FILL_TAGS = (
        Tag.SOLID_COLOR_SHEET_SETTING,
        Tag.PATTERN_FILL_SETTING,
        Tag.GRADIENT_FILL_SETTING,
        Tag.VECTOR_STROKE_CONTENT_DATA,
    )
    return any(tag in layer.tagged_blocks for tag in FILL_TAGS)


@overload
def union(backdrop: float, source: float) -> float: ...


@overload
def union(
    backdrop: NDArray[np.floating], source: NDArray[np.floating]
) -> NDArray[np.floating]: ...


@overload
def union(backdrop: float, source: NDArray[np.floating]) -> NDArray[np.floating]: ...


@overload
def union(backdrop: NDArray[np.floating], source: float) -> NDArray[np.floating]: ...


def union(
    backdrop: float | NDArray[np.floating],
    source: float | NDArray[np.floating],
) -> float | NDArray[np.floating]:
    """Generalized union of shape."""
    return backdrop + source - (backdrop * source)


def clip(x: NDArray[np.floating]) -> NDArray[np.floating]:
    """Clip between [0, 1]."""
    return np.clip(x, 0.0, 1.0)
