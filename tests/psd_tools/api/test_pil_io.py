import logging
import os
import zlib

import pytest

from psd_tools.api import pil_io, utils
from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import ColorMode, Compression
from psd_tools.psd.patterns import Pattern

from ..utils import TEST_ROOT, full_name
from .test_numpy_io import _forged_pattern

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "mode",
    [
        "L",
        "LA",
        "RGB",
        "RGBA",
        "CMYK",
        "CMYKA",
        "LAB",
        "1",
    ],
)
def test_get_color_mode(mode: str) -> None:
    assert isinstance(pil_io.get_color_mode(mode), ColorMode)


@pytest.mark.parametrize(
    "mode, alpha, expected",
    [
        (ColorMode.BITMAP, False, "1"),
        (ColorMode.GRAYSCALE, False, "L"),
        (ColorMode.GRAYSCALE, True, "LA"),
        (ColorMode.RGB, False, "RGB"),
        (ColorMode.RGB, True, "RGBA"),
        (ColorMode.CMYK, False, "CMYK"),
        (ColorMode.CMYK, True, "CMYK"),  # CMYK with alpha is not supported.
        (ColorMode.LAB, False, "LAB"),
    ],
)
def test_get_pil_mode(mode: ColorMode, alpha: bool, expected: str) -> None:
    assert pil_io.get_pil_mode(mode, alpha) == expected


def test_convert_pattern_to_pil() -> None:
    filepath = os.path.join(TEST_ROOT, "tagged_blocks", "Patt_1.dat")
    with open(filepath, "rb") as f:
        pattern = Pattern.read(f)

    assert pil_io.convert_pattern_to_pil(pattern)


def _pattern_with_declared_size(side: int, depth: int = 8) -> Pattern:
    """A pattern whose channels hold 8x8 of real data under a ``side`` square."""
    pattern = _forged_pattern(8, Compression.RAW)
    for c in pattern.data.channels:
        if c.is_written:
            c.depth = c.pixel_depth = depth
            c.data = b"\x00" * (8 * 8 * depth // 8)
    pattern.data.rectangle = (0, 0, side, side)
    return pattern


def test_a_declared_pattern_size_is_checked_before_the_allocation() -> None:
    pattern = _pattern_with_declared_size(20000)
    with pytest.raises(ValueError, match="over the configured budget"):
        pil_io.convert_pattern_to_pil(pattern, max_alloc_bytes=1 << 20)


def test_a_declared_pattern_axis_past_the_limit_is_rejected() -> None:
    pattern = _pattern_with_declared_size(utils.MAX_DIMENSION_PSD + 1)
    with pytest.raises(ValueError, match="per axis"):
        pil_io.convert_pattern_to_pil(pattern)


def test_the_pattern_budget_is_the_modelled_peak() -> None:
    pattern = _pattern_with_declared_size(8)
    written = sum(1 for c in pattern.data.channels if c.is_written)
    peak = pil_io._pattern_peak_bytes(64, written, 8)

    assert pil_io.convert_pattern_to_pil(pattern, max_alloc_bytes=peak)
    with pytest.raises(ValueError, match="over the configured budget"):
        pil_io.convert_pattern_to_pil(pattern, max_alloc_bytes=peak - 1)


def test_a_deep_pattern_is_charged_its_conversion_transient() -> None:
    # Past three channels the merge dominates, so only a narrow pattern shows it.
    assert pil_io._pattern_peak_bytes(64, 1, 16) > pil_io._pattern_peak_bytes(64, 1, 8)


def test_a_declared_channel_size_is_checked_before_the_decompress() -> None:
    pattern = _pattern_with_declared_size(8)
    for c in pattern.data.channels:
        if c.is_written:
            c.rectangle = (0, 0, 20000, 20000)
            c.compression = Compression.ZIP
            c.data = zlib.compress(b"\x00" * 20000 * 20000)
    with pytest.raises(ValueError, match="over the configured budget"):
        pil_io.convert_pattern_to_pil(pattern, max_alloc_bytes=1 << 20)


def test_apply_icc_profile() -> None:
    filepath = full_name("colorprofiles/north_america_newspaper.psd")
    psd = PSDImage.open(filepath)
    no_icc = psd.topil(apply_icc=False)
    with_icc = psd.topil(apply_icc=True)
    assert no_icc is not None
    assert with_icc is not None
    assert no_icc.getextrema() != with_icc.getextrema()
