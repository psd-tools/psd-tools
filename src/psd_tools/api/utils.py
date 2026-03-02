"""
Utility functions for the API layer.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from psd_tools.api.protocols import PSDProtocol

from psd_tools.constants import ColorMode, Resource, Tag

ColorInput = Union[int, float, Sequence[Union[int, float]]]

_DEPTH_MAX: dict[int, int] = {8: 255, 16: 65535, 32: 4294967295}

# Mapping of expected number of channels for each color mode.
EXPECTED_CHANNELS = {
    ColorMode.BITMAP: 1,
    ColorMode.GRAYSCALE: 1,
    ColorMode.INDEXED: 3,
    ColorMode.RGB: 3,
    ColorMode.CMYK: 4,
    ColorMode.MULTICHANNEL: 64,
    ColorMode.DUOTONE: 2,
    ColorMode.LAB: 3,
}


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
    expected = EXPECTED_CHANNELS.get(psdimage.color_mode)
    if expected is not None and psdimage.channels > expected:
        alpha_ids = psdimage.image_resources.get_data(Resource.ALPHA_IDENTIFIERS)
        if alpha_ids and all(x > 0 for x in alpha_ids):
            return False
        if (
            psdimage._record.layer_and_mask_information.layer_info is not None
            and psdimage._record.layer_and_mask_information.layer_info.layer_count > 0
        ):
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
    alpha_ids = psdimage.image_resources.get_data(Resource.ALPHA_IDENTIFIERS)
    if alpha_ids:
        try:
            offset = alpha_ids.index(0)
            return psdimage.channels - len(alpha_ids) + offset
        except ValueError:
            pass
    return -1  # Assume the last channel is the transparency


# ---------------------------------------------------------------------------
# Color normalization helpers
# ---------------------------------------------------------------------------


def _validate_color_input(color: ColorInput, depth: int) -> int:
    """Validate common preconditions and return max pixel value for *depth*.

    Raises :class:`TypeError` for ``bool``, ``str``, or other unsupported
    types.  Raises :class:`ValueError` for unsupported *depth* or empty
    sequences.
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
    if isinstance(color, Sequence) and len(color) == 0:
        raise ValueError("Color sequence must not be empty.")
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
) -> float | tuple[float, ...]:
    """Convert *color* to normalized ``[0.0, 1.0]`` float(s).

    Each element is individually dispatched by type:

    * **int** — treated as a raw pixel value in ``[0, max]`` for *depth*
    * **float** — treated as already normalized in ``[0.0, 1.0]``

    Scalar input returns a single ``float``.  Sequence input (``tuple``,
    ``list``, or any :class:`~collections.abc.Sequence`) returns a
    ``tuple[float, ...]``.  Mixed int/float sequences are supported.
    """
    max_val = _validate_color_input(color, depth)
    if isinstance(color, (int, float)):
        return _normalize_scalar(color, max_val)
    return tuple(_normalize_scalar(c, max_val, i) for i, c in enumerate(color))


def denormalize_color(
    color: ColorInput,
    depth: int,
) -> int | tuple[int, ...]:
    """Convert *color* to raw pixel integer(s).

    Each element is individually dispatched by type:

    * **float** — scaled from ``[0.0, 1.0]`` to ``[0, max]`` for *depth*
    * **int** — treated as already a raw pixel value in ``[0, max]``

    Scalar input returns a single ``int``.  Sequence input (``tuple``,
    ``list``, or any :class:`~collections.abc.Sequence`) returns a
    ``tuple[int, ...]``.  Mixed int/float sequences are supported.
    """
    max_val = _validate_color_input(color, depth)
    if isinstance(color, (int, float)):
        return _denormalize_scalar(color, max_val)
    return tuple(_denormalize_scalar(c, max_val, i) for i, c in enumerate(color))
