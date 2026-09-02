"""
Utility functions for the API layer.
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psd_tools.api.protocols import PSDProtocol

from psd_tools.constants import ColorMode, Resource, Tag

ColorInput = int | float | Sequence[int | float]

_DEPTH_MAX: dict[int, int] = {8: 255, 16: 65535, 32: 4294967295}

# Soft warning threshold — emit a PSDLargeImageWarning when a composite/numpy
# allocation would exceed this pixel count. Not spec-derived; chosen so that
# suspiciously large allocations are visible without blocking legitimate work.
WARN_PIXELS: int = 256 * 1024 * 1024

# Hard dimension limits derived from the PSD specification.
# PSD v1 (classic): each axis is capped at 30,000 px (spec §2: "1 to 30,000").
MAX_DIMENSION_PSD: int = 30_000
# Pixel-count product for reference (30,000 × 30,000 = 900,000,000 px).
MAX_PIXELS_PSD: int = MAX_DIMENSION_PSD * MAX_DIMENSION_PSD
# PSB v2 (large document): the spec allows up to 300,000 × 300,000 px, but
# enforcing that limit would still permit ~90-gigapixel allocations with no
# meaningful memory protection. This constant records the spec value for
# reference only; check_pixel_size applies MAX_DIMENSION_PSD to PSB files too.
MAX_PIXELS_PSB: int = 300_000 * 300_000

# Environment variable that seeds MAX_ALLOC_BYTES at import time.
MAX_ALLOC_BYTES_ENV: str = "PSD_TOOLS_MAX_ALLOC_BYTES"


def _env_alloc_budget() -> int | None:
    """Default :data:`MAX_ALLOC_BYTES` from ``$PSD_TOOLS_MAX_ALLOC_BYTES``.

    A positive integer enables the budget; unset/invalid/non-positive leaves it off.
    """
    raw = os.environ.get(MAX_ALLOC_BYTES_ENV)
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        warnings.warn(
            f"Ignoring non-integer {MAX_ALLOC_BYTES_ENV}={raw!r}.", stacklevel=2
        )
        return None
    if value <= 0:
        warnings.warn(
            f"Ignoring non-positive {MAX_ALLOC_BYTES_ENV}={value}.", stacklevel=2
        )
        return None
    return value


# Opt-in byte ceiling on the estimated float32 allocation; None = off (default).
# Seeded from $PSD_TOOLS_MAX_ALLOC_BYTES; per-document override via open(max_alloc_bytes=...).
MAX_ALLOC_BYTES: int | None = _env_alloc_budget()


class PSDLargeImageWarning(UserWarning):
    """Issued when a PSD canvas exceeds the soft pixel limit (:data:`WARN_PIXELS`)."""


def check_pixel_size(
    width: int,
    height: int,
    channels: int = 1,
    max_alloc_bytes: int | None = None,
    estimated_bytes: int | None = None,
) -> None:
    """Warn and/or raise when canvas dimensions exceed safe thresholds.

    Raises :class:`ValueError` when either axis exceeds
    :data:`MAX_DIMENSION_PSD` (the PSD v1 spec limit of 30,000 px per axis).
    Both PSD (v1) and PSB (v2) files are checked against this limit; PSB's
    own spec limit (:data:`MAX_PIXELS_PSB`) would allow ~90-gigapixel
    allocations so it is kept as a reference constant only.

    Issues a :class:`PSDLargeImageWarning` for pixel counts above
    :data:`WARN_PIXELS` that are still within the per-axis spec limit.

    When :data:`MAX_ALLOC_BYTES` is set, also raises :class:`ValueError` if the
    estimated allocation exceeds it. That estimate is ``estimated_bytes`` when a
    caller supplies one, and ``width * height * channels * 4`` otherwise.

    The two spellings answer different questions, and the difference is the
    point. ``width * height * channels * 4`` sizes the float32 array a path
    *returns*; a caller that also holds intermediates -- and both image-data
    paths hold several -- passes what it really peaks at instead, because a
    budget the peak exceeds is a budget that did not do its job (#767). See
    :func:`~psd_tools.api.numpy_io._image_data_peak_bytes` and
    :func:`~psd_tools.api.pil_io._image_data_peak_bytes` for the two models, and
    :func:`~psd_tools.composite.composite.composite` for the caller that keeps
    the returned-size spelling deliberately: its peak grows with the layer count,
    so no expression of this shape bounds it.

    :param width: canvas width in pixels.
    :param height: canvas height in pixels.
    :param channels: number of float32 planes. Sizes the default estimate
        (``width * height * channels * 4``), and names the shape in the error
        message either way. Defaults to 1. Callers may pass a count that differs
        from the header's channels, because for some colour modes and depths the
        array is not one plane per stored channel: see
        :func:`~psd_tools.api.numpy_io._image_data_planes`, which triples an
        indexed document for its palette.
    :param max_alloc_bytes: per-call budget in bytes; overrides the module-level
        :data:`MAX_ALLOC_BYTES` default when not ``None``.
    :param estimated_bytes: bytes this call is expected to allocate at its peak,
        replacing the default estimate when given. Callers whose peak is not a
        multiple of the returned array -- one holding a flat transient, say, that
        does not scale with the channel count -- cannot express it through
        ``channels`` alone, which is why this takes a byte count rather than a
        multiplier.
    """
    if width < 1 or height < 1:
        raise ValueError(f"Image dimensions must be positive, got {width}x{height}.")
    if width > MAX_DIMENSION_PSD or height > MAX_DIMENSION_PSD:
        raise ValueError(
            f"Image {width}x{height} exceeds the PSD maximum of "
            f"{MAX_DIMENSION_PSD} px per axis."
        )
    pixels = width * height
    if pixels > WARN_PIXELS:
        warnings.warn(
            f"Image {width}x{height} ({pixels:,} px) exceeds the soft pixel "
            f"limit ({WARN_PIXELS:,} px). Processing may require significant memory.",
            PSDLargeImageWarning,
            stacklevel=3,
        )
    budget = max_alloc_bytes if max_alloc_bytes is not None else MAX_ALLOC_BYTES
    if budget is not None:
        estimated = (
            estimated_bytes
            if estimated_bytes is not None
            else pixels * max(1, channels) * 4
        )
        if estimated > budget:
            # Naming which estimate this is matters: with a model the number is
            # not `width * height * channels * 4` and a reader trying to derive
            # it from the dimensions would not get there.
            kind = (
                "Peak allocation"
                if estimated_bytes is not None
                else "Estimated allocation"
            )
            raise ValueError(
                f"{kind} {estimated:,} bytes for "
                f"{width}x{height}x{channels} is over the configured budget "
                f"({budget:,} bytes). Raise or clear it via "
                f"PSDImage.open(max_alloc_bytes=...), ${MAX_ALLOC_BYTES_ENV}, or "
                f"psd_tools.api.utils.MAX_ALLOC_BYTES to allow it."
            )


# Mapping of expected number of channels for each color mode.
#
# This is not the only such table: :py:meth:`psd_tools.constants.ColorMode.channels`
# carries a second one, read by ``pil_io._check_channels()`` and
# ``PSDImage._make_header()``. The two still disagree for MULTICHANNEL -- 64
# here, 1 there -- where neither is any document's real count, which only the
# file header carries, and for INDEXED -- 3 here, 1 there -- where each is right
# about a different thing, one stored channel expanding to three through the
# palette. ``get_color_channels()`` below is the one that asks the header.
EXPECTED_CHANNELS = {
    ColorMode.BITMAP: 1,
    ColorMode.GRAYSCALE: 1,
    ColorMode.INDEXED: 3,
    ColorMode.RGB: 3,
    ColorMode.CMYK: 4,
    ColorMode.MULTICHANNEL: 64,
    # Duotone stores a single grayscale channel; its one to four inks live in
    # the color mode data section, not in the image data, so no ink count is a
    # channel count. This read 2 until #733.
    ColorMode.DUOTONE: 1,
    ColorMode.LAB: 3,
}


def get_color_channels(psdimage: "PSDProtocol") -> int:
    """Number of color channels a document's pixel arrays carry.

    Use this, rather than :data:`EXPECTED_CHANNELS`, wherever a caller must
    *allocate* a canvas as wide as the document's own arrays or validate a
    color against one. The constant is right for every mode whose channel count
    the mode itself fixes, but its multichannel entry is 64 -- the format's
    maximum, not any document's count -- so only the document can say.

    That 64 is left in place on purpose: ``numpy_io._find_channel()`` uses it as
    a defensive cap, where never truncating is what keeps a layer record
    declaring more channels than the header visible to the compositor.

    Args:
        psdimage: The PSD image protocol object
    Returns:
        The width of the document's color array. For every mode but multichannel
        that is the mode's own color components, with any alpha excluded; for
        multichannel it is the header's count, whose channels are spot channels.
        Layer arrays drop their transparency channel and so can be narrower than
        this in a malformed file -- deliberately, so that the compositor's width
        assertion still sees the mismatch.
    """
    return color_channels(psdimage.color_mode, psdimage.channels)


def color_channels(color_mode: ColorMode, channels: int) -> int:
    """The same rule as :func:`get_color_channels`, for a bare header.

    :py:meth:`PSDImage.new` has to answer this question before a document
    exists -- it holds only the :py:class:`~psd_tools.psd.header.FileHeader` it
    has just built -- so the rule lives here rather than inside the
    document-taking form.

    Args:
        color_mode: The document's color mode.
        channels: The header's channel count, alpha included.
    Returns:
        The width of the document's color array.
    """
    if color_mode == ColorMode.MULTICHANNEL:
        return channels
    return EXPECTED_CHANNELS[color_mode]


def has_transparency(psdimage: "PSDProtocol") -> bool:
    """Check if the PSD image has transparency information.

    Args:
        psdimage: The PSD image protocol object
    Returns:
        True if the image has transparency, False otherwise
    """
    keys = (
        Tag.SAVING_MERGED_TRANSPARENCY,
        Tag.SAVING_MERGED_TRANSPARENCY16,
        Tag.SAVING_MERGED_TRANSPARENCY32,
    )
    if psdimage.tagged_blocks and any(key in psdimage.tagged_blocks for key in keys):
        return True
    # Per the PSD spec, a negative layer_count means the first alpha channel
    # in the merged image data contains transparency for the composite.
    layer_info = psdimage._record.layer_and_mask_information.layer_info
    expected = EXPECTED_CHANNELS.get(psdimage.color_mode)
    if (
        layer_info is not None
        and layer_info.layer_count < 0
        and expected is not None
        and psdimage.channels > expected
    ):
        return True
    if expected is not None and psdimage.channels > expected:
        alpha_ids = psdimage.image_resources.get_data(Resource.ALPHA_IDENTIFIERS)
        if alpha_ids and all(x > 0 for x in alpha_ids):
            return False
        if layer_info is not None and layer_info.layer_count > 0:
            return False
        return True
    return False


def get_transparency_index(psdimage: "PSDProtocol") -> int:
    """Get the index of the transparency channel in the PSD image.

    Args:
        psdimage: The PSD image protocol object
    Returns:
        The index of the transparency channel, or -1 if not found
    """
    # When layer_count is negative, the first alpha channel is transparency.
    layer_info = psdimage._record.layer_and_mask_information.layer_info
    if layer_info is not None and layer_info.layer_count < 0:
        expected = EXPECTED_CHANNELS.get(psdimage.color_mode)
        if expected is not None and psdimage.channels > expected:
            return expected
    alpha_ids = psdimage.image_resources.get_data(Resource.ALPHA_IDENTIFIERS)
    if alpha_ids:
        try:
            offset = alpha_ids.index(0)
            return psdimage.channels - len(alpha_ids) + offset
        except ValueError:
            pass
    return -1


# ---------------------------------------------------------------------------
# Color normalization helpers
# ---------------------------------------------------------------------------


def _validate_color_input(
    color: ColorInput,
    depth: int,
    color_mode: ColorMode | None = None,
    channels: int | None = None,
) -> int:
    """Validate common preconditions and return max pixel value for *depth*.

    Raises :class:`TypeError` for ``bool``, ``str``, or other unsupported
    types.  Raises :class:`ValueError` for unsupported *depth*, empty
    sequences, or wrong number of channels for *color_mode*.

    *channels* overrides the per-mode count :data:`EXPECTED_CHANNELS` would
    supply. Multichannel is why it exists: that entry is 64, the format's
    maximum rather than any document's own count, so validating a sequence
    against it rejects every sequence a caller could sensibly pass. A caller
    that knows the real width -- from a document via
    :func:`get_color_channels`, or from a header via :func:`color_channels` --
    passes it here.
    """
    if isinstance(color, bool):
        raise TypeError(f"Bool color {color!r} is not supported. Use int or float.")
    if isinstance(color, str):
        raise TypeError(f"String color {color!r} is not supported. Use int or float.")
    try:
        max_val = _DEPTH_MAX[depth]
    except KeyError:
        raise ValueError(
            f"Unsupported bit depth {depth}. Expected one of {sorted(_DEPTH_MAX)}."
        ) from None
    if isinstance(color, Sequence):
        if len(color) == 0:
            raise ValueError("Color sequence must not be empty.")
        expected: int | None = None
        if channels is not None:
            expected = channels
        elif color_mode is not None:
            expected = EXPECTED_CHANNELS.get(color_mode)
        if expected is not None and len(color) != expected:
            mode_name = color_mode.name if color_mode is not None else "the document"
            raise ValueError(
                f"Expected {expected} color channel(s) for {mode_name}, "
                f"got {len(color)}."
            )
    return max_val


def _normalize_scalar(
    value: int | float,
    max_val: int,
    index: int | None = None,
) -> float:
    """Convert a single color component to a normalized ``[0.0, 1.0]`` float.

    *int* values are treated as raw pixel values in ``[0, max_val]``.
    *float* values are expected to already be in ``[0.0, 1.0]``.
    """
    ctx = f" at index {index}" if index is not None else ""
    if isinstance(value, bool):
        raise TypeError(f"Bool color component{ctx} {value!r} is not supported.")
    if isinstance(value, float):
        if not 0.0 <= value <= 1.0:
            raise ValueError(
                f"Float color{ctx} {value!r} out of range. Expected [0.0, 1.0]."
            )
        return value
    if isinstance(value, int):
        if not 0 <= value <= max_val:
            raise ValueError(
                f"Integer color{ctx} {value!r} out of range. Expected [0, {max_val}]."
            )
        return value / max_val
    raise TypeError(
        f"Color component{ctx} must be int or float, got {type(value).__name__}."
    )


def _denormalize_scalar(
    value: int | float,
    max_val: int,
    index: int | None = None,
) -> int:
    """Convert a single color component to a raw pixel integer.

    *float* values in ``[0.0, 1.0]`` are scaled to ``[0, max_val]``.
    *int* values are expected to already be in ``[0, max_val]``.
    """
    ctx = f" at index {index}" if index is not None else ""
    if isinstance(value, bool):
        raise TypeError(f"Bool color component{ctx} {value!r} is not supported.")
    if isinstance(value, float):
        if not 0.0 <= value <= 1.0:
            raise ValueError(
                f"Float color{ctx} {value!r} out of range. Expected [0.0, 1.0]."
            )
        return round(value * max_val)
    if isinstance(value, int):
        if not 0 <= value <= max_val:
            raise ValueError(
                f"Integer color{ctx} {value!r} out of range. Expected [0, {max_val}]."
            )
        return value
    raise TypeError(
        f"Color component{ctx} must be int or float, got {type(value).__name__}."
    )


def normalize_color(
    color: ColorInput,
    depth: int,
    color_mode: ColorMode | None = None,
    channels: int | None = None,
) -> float | tuple[float, ...]:
    """Convert *color* to normalized ``[0.0, 1.0]`` float(s).

    Each element is individually dispatched by type:

    * **int** — treated as a raw pixel value in ``[0, max]`` for *depth*
    * **float** — treated as already normalized in ``[0.0, 1.0]``

    Scalar input returns a single ``float``.  Sequence input (``tuple``,
    ``list``, or any :class:`~collections.abc.Sequence`) returns a
    ``tuple[float, ...]``.  Mixed int/float sequences are supported.
    """
    max_val = _validate_color_input(color, depth, color_mode, channels)
    if isinstance(color, (int, float)):
        return _normalize_scalar(color, max_val)
    return tuple(_normalize_scalar(c, max_val, i) for i, c in enumerate(color))


def denormalize_color(
    color: ColorInput,
    depth: int,
    color_mode: ColorMode | None = None,
    channels: int | None = None,
) -> int | tuple[int, ...]:
    """Convert *color* to raw pixel integer(s).

    Each element is individually dispatched by type:

    * **float** — scaled from ``[0.0, 1.0]`` to ``[0, max]`` for *depth*
    * **int** — treated as already a raw pixel value in ``[0, max]``

    Scalar input returns a single ``int``.  Sequence input (``tuple``,
    ``list``, or any :class:`~collections.abc.Sequence`) returns a
    ``tuple[int, ...]``.  Mixed int/float sequences are supported.
    """
    max_val = _validate_color_input(color, depth, color_mode, channels)
    if isinstance(color, (int, float)):
        return _denormalize_scalar(color, max_val)
    return tuple(_denormalize_scalar(c, max_val, i) for i, c in enumerate(color))
