"""Regression tests for GHSA-8q6g-vjhf-jp8m.

A crafted PSD can declare arbitrarily large dimensions in its header and
trigger multi-GB memory allocations when composite() or numpy() is called.
The fix emits PSDLargeImageWarning above WARN_PIXELS and raises ValueError
above MAX_PIXELS_PSD instead of committing the buffer silently.
"""

import base64
import io
import struct
import warnings

import pytest

from typing import Any

from psd_tools import PSDImage, PSDLargeImageWarning
from psd_tools import compression as _compression
from psd_tools.api import utils as _utils
from psd_tools.constants import ColorMode
from psd_tools.api.utils import (
    MAX_DIMENSION_PSD,
    MAX_PIXELS_PSD,
    MAX_PIXELS_PSB,
    WARN_PIXELS,
)

from .utils import full_name


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
    # PSD v1 spec max: 30,000 px per axis
    assert MAX_DIMENSION_PSD == 30_000
    assert MAX_PIXELS_PSD == MAX_DIMENSION_PSD * MAX_DIMENSION_PSD
    # PSB v2 spec reference — not enforced; check_pixel_size uses MAX_DIMENSION_PSD.
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


def test_pil_raises_when_psd_v1_exceeds_spec() -> None:
    """PSD v1 topil() must raise ValueError when dimensions exceed the spec."""
    psd = PSDImage.open(_build_psd(_OVER_SPEC_W, _OVER_SPEC_H))
    with pytest.raises(ValueError, match="exceeds"):
        psd.topil()


def test_per_axis_limit_catches_non_square_oversized() -> None:
    """A non-square canvas that exceeds one axis but not the pixel count must raise."""
    # 40,000 × 1 = 40,000 px total — well below MAX_PIXELS_PSD, but 40,000 > MAX_DIMENSION_PSD.
    psd = PSDImage.open(_build_psd(40_000, 1))
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


# 49-byte PoC declaring 5964 x 10296, 6 channels, 8-bit (~3.35 GB before the fix).
_POC_B64 = "OEJQUwABAAAAAAAAAAYAACg4AAAXTAAIAAMAAAAAAAAAAAAAAAAAAUNIUIFU+yQtDw=="


def test_data_aware_guard_rejects_tiny_file_huge_canvas() -> None:
    """The 49-byte PoC must raise instead of silently allocating gigabytes."""
    psd = PSDImage.open(io.BytesIO(base64.b64decode(_POC_B64)))
    assert psd.width == 5964 and psd.height == 10296 and psd.channels == 6
    with pytest.raises(ValueError, match="failed to decode"):
        psd.numpy()


def test_data_aware_guard_rejects_tiny_file_huge_canvas_composite() -> None:
    """The advisory names both numpy() and composite(); guard the latter too."""
    pytest.importorskip("aggdraw")
    pytest.importorskip("scipy")
    pytest.importorskip("skimage")
    psd = PSDImage.open(io.BytesIO(base64.b64decode(_POC_B64)))
    with pytest.raises(ValueError, match="failed to decode"):
        psd.composite()


def test_data_aware_guard_keeps_small_corrupt_channels_lenient() -> None:
    """A small undecodable channel must still warn + black-fill, not raise."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = _compression.decompress(
            b"\x00", _compression.Compression.RLE, width=4, height=1, depth=8, version=1
        )
    assert out == b"\x00" * 4
    assert any(
        issubclass(w.category, _compression.PSDDecompressionWarning) for w in caught
    )


def test_opt_in_byte_budget_raises_when_set() -> None:
    """Setting MAX_ALLOC_BYTES bounds even a small, otherwise-allowed canvas."""
    psd = PSDImage.open(_build_psd(_NORMAL_W, _NORMAL_H))  # 64x64x3 -> ~49 KB est
    saved = _utils.MAX_ALLOC_BYTES
    _utils.MAX_ALLOC_BYTES = 1024
    try:
        with pytest.raises(ValueError, match="MAX_ALLOC_BYTES"):
            psd.numpy()
    finally:
        _utils.MAX_ALLOC_BYTES = saved


def test_opt_in_byte_budget_disabled_by_default() -> None:
    """With the default (None) budget, a within-spec canvas is not budget-rejected."""
    assert _utils.MAX_ALLOC_BYTES is None
    psd = PSDImage.open(_build_psd(_NORMAL_W, _NORMAL_H))
    try:
        psd.numpy()
    except ValueError as exc:
        assert "MAX_ALLOC_BYTES" not in str(exc)
    except Exception:
        pass  # other errors (e.g. empty pixel data) are fine


def test_open_max_alloc_bytes_kwarg_bounds_within_spec_canvas() -> None:
    """open(max_alloc_bytes=...) caps a within-spec canvas without touching globals."""
    assert _utils.MAX_ALLOC_BYTES is None  # global default stays off
    psd = PSDImage.open(_build_psd(_NORMAL_W, _NORMAL_H), max_alloc_bytes=1024)
    assert psd._max_alloc_bytes == 1024
    with pytest.raises(ValueError, match="1,024 bytes"):
        psd.numpy()


def test_open_max_alloc_bytes_is_per_instance() -> None:
    """The limit travels with the object; a second document is unaffected."""
    bounded = PSDImage.open(_build_psd(_NORMAL_W, _NORMAL_H), max_alloc_bytes=1024)
    unbounded = PSDImage.open(_build_psd(_NORMAL_W, _NORMAL_H))
    assert unbounded._max_alloc_bytes is None
    with pytest.raises(ValueError, match="configured budget"):
        bounded.numpy()
    try:
        unbounded.numpy()
    except ValueError as exc:
        assert "configured budget" not in str(exc)
    except Exception:
        pass  # other errors (e.g. empty pixel data) are fine


def test_env_var_seeds_default_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """A positive integer in the env var becomes the default budget."""
    monkeypatch.setenv(_utils.MAX_ALLOC_BYTES_ENV, "1024")
    assert _utils._env_alloc_budget() == 1024


def test_env_var_invalid_is_ignored_with_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-integer and non-positive values are ignored (budget stays off)."""
    monkeypatch.setenv(_utils.MAX_ALLOC_BYTES_ENV, "not-an-int")
    with pytest.warns(UserWarning, match=_utils.MAX_ALLOC_BYTES_ENV):
        assert _utils._env_alloc_budget() is None
    monkeypatch.setenv(_utils.MAX_ALLOC_BYTES_ENV, "-5")
    with pytest.warns(UserWarning, match=_utils.MAX_ALLOC_BYTES_ENV):
        assert _utils._env_alloc_budget() is None


def test_explicit_kwarg_overrides_env_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """A per-document budget takes precedence over the module/env default."""
    # Simulate the env-seeded default being large; the per-call limit is smaller.
    monkeypatch.setattr(_utils, "MAX_ALLOC_BYTES", 10**12)
    psd = PSDImage.open(_build_psd(_NORMAL_W, _NORMAL_H), max_alloc_bytes=1024)
    with pytest.raises(ValueError, match="1,024 bytes"):
        psd.numpy()


# ---------------------------------------------------------------------------
# The estimate must match the allocation it guards (#732)
# ---------------------------------------------------------------------------
#
# `get_image_data()` reads the header's channel count but does not always
# allocate that many planes, so these pin the estimate against the array that
# is actually produced rather than against a hard-coded byte count. A budget
# equal to the real allocation must admit the document and one byte less must
# reject it: that brackets the estimate from both sides at once, which a test
# asserting only "raises" would not.
#
# Both directions matter. The guard is a security control, so an estimate below
# the allocation defeats it -- but one above it rejects a file that would have
# been fine, and a guard that refuses sound documents is its own bug. The
# estimate is exact for every colour mode, depth and channel count below.
#
# Note the scope: it bounds the array that is *returned*, which is what
# `check_pixel_size()` estimates by construction. The transient peak is a small
# multiple of it for every mode -- `_parse_array()` holds the raw bytes and two
# float32 arrays at once -- and that is pre-existing, not colour-mode-specific.

_COLORMODE_FIXTURES = [
    "4x4_8bit_index_color.psd",
    "4x4_8bit_rgba.psd",
    "4x4_8bit_rgb.psd",
    "4x4_8bit_grayscale.psd",
    "4x4_8bit_duotone.psd",
    "4x4_8bit_cmyk.psd",
    "4x4_8bit_lab.psd",
    "4x4_16bit_multichannel.psd",
    "4x4_16bit_cmyk.psd",
    "4x4_16bit_lab.psd",
    "4x4_32bit_rgb.psd",
    "4x4_32bit_grayscale.psd",
    "4x4_1bit_bitmap.psd",
]


def _colormode(filename: str, max_alloc_bytes: int | None = None) -> PSDImage:
    return PSDImage.open(
        full_name("colormodes/" + filename), max_alloc_bytes=max_alloc_bytes
    )


def _forge(
    width: int,
    height: int,
    channels: int,
    depth: int,
    color_mode: int,
    max_alloc_bytes: int | None = None,
) -> PSDImage:
    """A structurally valid PSD with an arbitrary header/mode combination.

    `_build_psd()` above is RGB-only and empty-bodied. These tests need headers
    that no fixture provides -- an indexed document with more than one stored
    channel, an indexed document at a depth where the palette is not applied --
    and need the image data to actually parse, so the estimate can be compared
    against a real array.
    """
    buf = io.BytesIO()
    buf.write(
        struct.pack(
            ">4sH6xHIIHH", b"8BPS", 1, channels, height, width, depth, color_mode
        )
    )
    buf.write(struct.pack(">I", 768))  # colour mode data: a 256x3 palette
    buf.write(bytes(768))
    buf.write(struct.pack(">I", 0))  # image resources
    buf.write(struct.pack(">I", 0))  # layer and mask info
    buf.write(struct.pack(">H", 0))  # image data: raw, uncompressed
    buf.write(bytes(width * height * channels * max(1, depth // 8)))
    buf.seek(0)
    return PSDImage.open(buf, max_alloc_bytes=max_alloc_bytes)


def _assert_estimate_is_exact(open_doc: Any) -> int:
    """A budget equal to the allocation admits; one byte less rejects.

    Returns the allocation, so a caller can additionally pin its width.
    """
    allocated = open_doc().numpy().nbytes
    open_doc(allocated).numpy()
    with pytest.raises(ValueError, match="configured budget"):
        open_doc(allocated - 1).numpy()
    return allocated


def test_numpy_guard_estimate_covers_the_palette_expansion() -> None:
    """Indexed at depth 8 allocates three planes per stored channel.

    ``_parse_array()`` applies the palette to the whole buffer rather than to a
    single plane, so the array comes back ``3 * channels`` wide and the header's
    own count under-counted it threefold. Indexed is also the mode Photoshop
    writes for a flattened document, so this was the common shape rather than a
    corner.
    """
    allocated = _assert_estimate_is_exact(
        lambda budget=None: _colormode("4x4_8bit_index_color.psd", budget)
    )
    assert _colormode("4x4_8bit_index_color.psd").channels == 1  # header says 1...
    assert allocated == 4 * 4 * 3 * 4  # ...the array is 3 planes wide


@pytest.mark.parametrize("channels", [1, 2, 4, 8])
def test_numpy_guard_estimate_scales_the_palette_expansion(channels: int) -> None:
    """The expansion is ``3 * channels``, not a flat 3.

    ``FileHeader.channels`` is an attacker-controlled uint16 with no cross-check
    against the colour mode, and this guard exists for hostile headers
    (GHSA-8q6g-vjhf-jp8m) -- so "Photoshop never writes multi-channel indexed"
    is the threat model rather than a defence. Taking the *wider* of the header
    count and 3, instead of their product, left the estimate a flat third of the
    array for any header declaring three channels or more.
    """
    allocated = _assert_estimate_is_exact(
        lambda budget=None: _forge(4, 4, channels, 8, ColorMode.INDEXED, budget)
    )
    assert allocated == 4 * 4 * (3 * channels) * 4


@pytest.mark.parametrize("depth", [16, 32])
def test_numpy_guard_estimate_does_not_expand_indexed_at_other_depths(
    depth: int,
) -> None:
    """The palette is applied only in ``_parse_array()``'s depth-8 branch.

    Indexed is an 8-bit mode, so such a document is malformed -- but it parses,
    and it keeps its stored width. Tripling it would reject a file three times
    smaller than the estimate claimed, which is the false-positive direction.
    """
    allocated = _assert_estimate_is_exact(
        lambda budget=None: _forge(4, 4, 1, depth, ColorMode.INDEXED, budget)
    )
    assert allocated == 4 * 4 * 1 * 4  # not tripled


@pytest.mark.parametrize(
    ("color_mode", "channels"),
    [
        (ColorMode.RGB, 1),
        (ColorMode.RGB, 2),
        (ColorMode.RGB, 4),  # RGBA: the header is wider than the mode
        (ColorMode.CMYK, 1),
        (ColorMode.LAB, 2),
        (ColorMode.GRAYSCALE, 2),  # grayscale + alpha
    ],
)
def test_numpy_guard_estimate_follows_the_header_for_every_other_mode(
    color_mode: int, channels: int
) -> None:
    """Outside the palette expansion, the stored count *is* the allocation.

    Including where the header disagrees with its colour mode. Such files parse
    fine and produce a narrow array -- a one-channel RGB document returns
    ``(h, w, 1)`` -- so resolving the width from the colour mode instead would
    reject them at up to four times their real size.
    """
    allocated = _assert_estimate_is_exact(
        lambda budget=None: _forge(4, 4, channels, 8, color_mode, budget)
    )
    assert allocated == 4 * 4 * channels * 4


@pytest.mark.parametrize("filename", _COLORMODE_FIXTURES)
def test_numpy_guard_estimate_never_exceeds_the_allocation(filename: str) -> None:
    """No shipped fixture may be rejected at a budget it actually fits inside.

    The same invariant as above swept over the real corpus, covering every
    colour mode and all four depths. (Bitmap has slack in the other direction:
    a 1-bit document unpacks to more values than the byte count this estimate
    assumes, which has no depth term. That is a separate gap, not something this
    assertion claims is absent.)
    """
    allocated = _colormode(filename).numpy().nbytes
    _colormode(filename, allocated).numpy()
