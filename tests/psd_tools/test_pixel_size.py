"""Regression tests for GHSA-8q6g-vjhf-jp8m.

A crafted PSD can declare arbitrarily large dimensions in its header and
trigger multi-GB memory allocations when composite() or numpy() is called.
The fix emits PSDLargeImageWarning above WARN_PIXELS and raises ValueError
above MAX_PIXELS_PSD instead of committing the buffer silently.
"""

import io
import struct
import warnings

import pytest

from psd_tools import PSDImage, PSDLargeImageWarning
from psd_tools.api.utils import MAX_PIXELS_PSD, MAX_PIXELS_PSB, WARN_PIXELS


def _build_psd(width: int, height: int, channels: int = 3) -> io.BytesIO:
    """Return a BytesIO containing a minimal structurally valid PSD.

    The image data section is empty; the pixel budget check must fire before
    any decompression is attempted.
    """
    buf = io.BytesIO()
    # File header: signature, version, 6-byte reserved, channels, height,
    # width, depth, color_mode (RGB = 3)
    buf.write(struct.pack(">4sH6xHIIHH", b"8BPS", 1, channels, height, width, 8, 3))
    buf.write(struct.pack(">I", 0))  # color mode data length
    buf.write(struct.pack(">I", 0))  # image resources length
    buf.write(struct.pack(">I", 0))  # layer and mask info length
    buf.write(struct.pack(">H", 0))  # image data: compression = raw, no data
    buf.seek(0)
    return buf


def test_constants() -> None:
    """Spec-derived constants must be consistent and sensible."""
    # PSD v1 spec max: 30,000 × 30,000
    assert MAX_PIXELS_PSD == 30_000 * 30_000
    # PSB v2 spec reference — not enforced; check_pixel_size uses MAX_PIXELS_PSD.
    assert MAX_PIXELS_PSB == 300_000 * 300_000
    # Soft warning threshold must not block legitimate 16 k × 16 k canvases.
    assert WARN_PIXELS >= 16_000 * 16_000


# Dimensions that exceed the PSD v1 spec limit (30,000 × 30,000 = 900 M px).
# Using 30,001 × 30,001 triggers the hard limit without needing a huge file.
_OVER_SPEC_W = 30_001
_OVER_SPEC_H = 30_001

# Dimensions below WARN_PIXELS and well within spec.
_NORMAL_W = 64
_NORMAL_H = 64


def test_composite_raises_when_psd_v1_exceeds_spec() -> None:
    """PSD v1 composite() must raise ValueError when dimensions exceed the spec."""
    psd = PSDImage.open(_build_psd(_OVER_SPEC_W, _OVER_SPEC_H))
    with pytest.raises(ValueError, match="exceeds"):
        psd.composite(ignore_preview=True)


def test_numpy_raises_when_psd_v1_exceeds_spec() -> None:
    """PSD v1 numpy() must raise ValueError when dimensions exceed the spec."""
    psd = PSDImage.open(_build_psd(_OVER_SPEC_W, _OVER_SPEC_H))
    with pytest.raises(ValueError, match="exceeds"):
        psd.numpy()


def test_open_does_not_raise_for_out_of_spec_dimensions() -> None:
    """Parsing the file structure must succeed; the guard only fires on render."""
    psd = PSDImage.open(_build_psd(_OVER_SPEC_W, _OVER_SPEC_H))
    assert psd.width == _OVER_SPEC_W
    assert psd.height == _OVER_SPEC_H


def test_large_within_spec_psd_warns_but_does_not_raise() -> None:
    """20 k × 20 k is within spec (< 900 M px) — must warn but not hard-raise."""
    psd = PSDImage.open(_build_psd(20_000, 20_000))
    assert psd.width == 20_000
    with pytest.warns(PSDLargeImageWarning):
        try:
            psd.composite(ignore_preview=True)
        except ValueError as exc:
            assert "exceeds" not in str(exc), (
                f"hard pixel-limit guard fired for a within-spec PSD: {exc}"
            )
        except Exception as exc:
            if isinstance(exc, AssertionError):
                raise
            pass  # other errors (e.g. empty pixel data) are fine


def test_normal_sized_psd_does_not_warn() -> None:
    """Small PSDs must not trigger any pixel-limit warning."""
    psd = PSDImage.open(_build_psd(_NORMAL_W, _NORMAL_H))
    with warnings.catch_warnings():
        warnings.simplefilter("error", PSDLargeImageWarning)
        try:
            psd.composite(ignore_preview=True)
        except PSDLargeImageWarning:
            pytest.fail("PSDLargeImageWarning fired for a normal-sized PSD")
        except Exception as exc:
            if isinstance(exc, AssertionError):
                raise
            pass  # other errors (e.g. empty pixel data) are fine
