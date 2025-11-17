"""Utility functions for composite operations."""

from typing import Union, overload

import numpy as np
from numpy.typing import NDArray

from psd_tools.api.layers import Layer
from psd_tools.constants import Tag


def divide(a: NDArray[np.floating], b: NDArray[np.floating]) -> NDArray[np.floating]:
    """Safe division for color ops."""
    with np.errstate(divide="ignore", invalid="ignore"):
        c = np.true_divide(a, b)
        c[~np.isfinite(c)] = 1.0
    return c


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
    backdrop: Union[float, NDArray[np.floating]],
    source: Union[float, NDArray[np.floating]],
) -> Union[float, NDArray[np.floating]]:
    """Generalized union of shape."""
    return backdrop + source - (backdrop * source)


def clip(x: NDArray[np.floating]) -> NDArray[np.floating]:
    """Clip between [0, 1]."""
    return np.clip(x, 0.0, 1.0)
