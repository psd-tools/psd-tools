"""Regression tests for GHSA-8q6g-vjhf-jp8m.

A crafted PSD can declare arbitrarily large dimensions in its header and
trigger multi-GB memory allocations when composite() or numpy() is called.
The fix emits PSDLargeImageWarning above WARN_PIXELS and raises ValueError
above MAX_PIXELS_PSD instead of committing the buffer silently.
"""

import base64
import gc
import io
import struct
import tracemalloc
import warnings
import zlib

import pytest

from typing import Any, Callable, Literal, Optional

from psd_tools import PSDImage, PSDLargeImageWarning
from psd_tools import compression as _compression
from psd_tools.compression import compress
from psd_tools.api import utils as _utils
from psd_tools.api.numpy_io import _image_data_planes
from psd_tools.api.numpy_io import _image_data_peak_bytes as _numpy_peak_bytes
from psd_tools.api.pil_io import _WHITE_BACKGROUND_TRANSIENT
from psd_tools.api.pil_io import _image_data_peak_bytes as _pil_peak_bytes
from psd_tools.api.utils import check_pixel_size, has_transparency
from psd_tools.constants import ColorMode, Compression, Resource
from psd_tools.api.utils import (
    MAX_DIMENSION_PSD,
    MAX_PIXELS_PSD,
    MAX_PIXELS_PSB,
    WARN_PIXELS,
)

from .utils import full_name

_Channel = Literal["color", "shape", "alpha", "mask"]


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
# The estimate must model the peak it guards (#732, #767)
# ---------------------------------------------------------------------------
#
# `check_pixel_size()` used to be handed `width * height * channels * 4`: the
# size of the array a path *returns*. #732 fixed the channel count feeding that
# product, because `get_image_data()` reads the header's count and does not
# always allocate that many planes. What it could not fix is that the returned
# array was the wrong quantity to bound. Both image-data paths hold
# intermediates alongside their result -- `_parse_array()` two float32 arrays at
# once, `_remove_background()` several more, the decompressed buffer live across
# all of it -- so the real high-water mark ran up to 3.7x past the budget the
# caller had set, and on the PIL path the same product also ran the other way,
# turning away 8-bit documents that would have fitted several times over (#767).
#
# So each path now hands the guard a structural model of its own peak:
# `numpy_io._image_data_peak_bytes()` and `pil_io._image_data_peak_bytes()`.
# The tests below pin those models from three directions:
#
# - The model never falls below what the call really allocates. That is the
#   security property -- an allocation that walks through the guard is the bug
#   the guard exists for -- and it is asserted against `tracemalloc`, which sees
#   numpy's allocations, rather than against any restatement of the model.
# - The model is not wildly above it either. A guard that refuses sound
#   documents is its own bug, and an estimate free to drift upwards has nothing
#   left to say when it does.
# - The plane count the model is built from still follows the format. The
#   palette expansion and the depth-1 row arithmetic are facts about the file,
#   not about the code that reads it, so they are asserted directly on
#   `_image_data_planes()` and on the array's own `nbytes`. The peak model rides
#   on top of them, and the two go stale for different reasons.
#
# `_assert_budget_brackets_the_model()` below is deliberately thin: it pins
# *which* number the budget is compared against and nothing more. Left on its
# own it would be asserting that `check_pixel_size()` spells its comparison
# `>`, so no test here leans on it alone.

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


def _payload(size: int, depth: int) -> bytes:
    """``size`` bytes of body that every branch of the model can be measured on.

    The content is load-bearing rather than filler. At depth 32 the buffer is
    reinterpreted as float32, and a body of arbitrary bytes reads as mostly
    *negative* floats; `_remove_background()` then finds every alpha at or below
    zero, its `color[a > 0]` selects almost nothing, and the largest transient
    in the whole model goes unallocated and unmeasured. ``0x3f000000`` is 0.5f,
    so every plane -- alpha included -- comes out positive and in range.

    The other depths rescale into ``[0, 1]`` from unsigned integers, where any
    non-zero byte will do; ``range(1, 256)`` simply skips zero, so that an
    all-zero alpha plane cannot hide the same transient by the same route.
    """
    unit = b"\x3f\x00\x00\x00" if depth == 32 else bytes(range(1, 256))
    return (unit * (size // len(unit) + 1))[:size]


def _forge(
    width: int,
    height: int,
    channels: int,
    depth: int,
    color_mode: int,
    max_alloc_bytes: int | None = None,
    compression: Compression = Compression.RAW,
    icc: bool = False,
) -> PSDImage:
    """A structurally valid PSD with an arbitrary header/mode combination.

    `_build_psd()` above is RGB-only and empty-bodied. These tests need headers
    that no fixture provides -- an indexed document with more than one stored
    channel, an indexed document at a depth where the palette is not applied --
    and need the image data to actually parse, so the model can be compared
    against a real array and a real allocation.

    *compression* matters as much as the header does once the model is about a
    peak. `Compression.RAW` hands `get_data()` back the same bytes object that
    was read at open time, so a corpus measured only on raw bodies never
    exercises the codec's own peak at all.

    *icc* writes an ICC_PROFILE image resource. Only its presence is forged, not
    a usable profile: `pil_io._image_data_peak_bytes()` asks
    `Resource.ICC_PROFILE in psd.image_resources` and nothing more, and the one
    combination that needs this -- a document that is neither RGB nor grayscale,
    carrying both a profile and transparency -- exists in no shipped fixture.
    """
    rows = height * channels
    body = _payload(((width * depth + 7) // 8) * rows, depth)
    buf = io.BytesIO()
    buf.write(
        struct.pack(
            ">4sH6xHIIHH", b"8BPS", 1, channels, height, width, depth, color_mode
        )
    )
    buf.write(struct.pack(">I", 768))  # colour mode data: a 256x3 palette
    buf.write(bytes(768))
    if icc:
        # One 8BIM block: signature, id 1039, empty pascal name, length, body.
        resource = (
            struct.pack(">4sH2xI", b"8BIM", Resource.ICC_PROFILE, 2) + b"\x00\x00"
        )
        buf.write(struct.pack(">I", len(resource)))
        buf.write(resource)
    else:
        buf.write(struct.pack(">I", 0))  # image resources
    buf.write(struct.pack(">I", 0))  # layer and mask info
    buf.write(struct.pack(">H", compression))
    buf.write(compress(body, compression, width, rows, depth, 1))
    buf.seek(0)
    return PSDImage.open(buf, max_alloc_bytes=max_alloc_bytes)


def _assert_budget_brackets_the_model(open_doc: Any) -> int:
    """A budget equal to the model admits; one byte less rejects.

    This says only that the budget is compared against
    `_image_data_peak_bytes()` and against nothing else -- that the guard reads
    the model the path built for it, and reads the right one when a branch
    picks between two. It says nothing whatever about whether the model is
    *true*; that is the subject of the `tracemalloc` sweep below, and of the
    `nbytes` and `_image_data_planes()` assertions each caller makes alongside
    this one. A test whose only assertion were this would be testing that
    `check_pixel_size()` compares with `>`.

    Returns the model, so a caller can additionally pin its width.
    """
    model = _numpy_peak_bytes(open_doc())
    open_doc(model).numpy()
    with pytest.raises(ValueError, match="configured budget"):
        open_doc(model - 1).numpy()
    return model


def test_numpy_guard_estimate_covers_the_palette_expansion() -> None:
    """Indexed at depth 8 allocates three planes per stored channel.

    ``_parse_array()`` applies the palette to the whole buffer rather than to a
    single plane, so the array comes back ``3 * channels`` wide and the header's
    own count under-counted it threefold. Indexed is also the mode Photoshop
    writes for a flattened document, so this was the common shape rather than a
    corner.

    The plane count is asserted on `_image_data_planes()` and on the array
    itself, which is where the expansion lives; the peak model is built from
    that count and is bracketed separately.
    """
    psd = _colormode("4x4_8bit_index_color.psd")
    assert psd.channels == 1  # the header says one...
    assert _image_data_planes(psd) == 3  # ...the array is three planes wide
    assert psd.numpy().nbytes == 4 * 4 * 3 * 4
    _assert_budget_brackets_the_model(
        lambda budget=None: _colormode("4x4_8bit_index_color.psd", budget)
    )


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
    psd = _forge(4, 4, channels, 8, ColorMode.INDEXED)
    assert _image_data_planes(psd) == 3 * channels
    assert psd.numpy().nbytes == 4 * 4 * (3 * channels) * 4
    _assert_budget_brackets_the_model(
        lambda budget=None: _forge(4, 4, channels, 8, ColorMode.INDEXED, budget)
    )


@pytest.mark.parametrize("depth", [16, 32])
def test_numpy_guard_estimate_does_not_expand_indexed_at_other_depths(
    depth: int,
) -> None:
    """The palette is applied only in ``_parse_array()``'s depth-8 branch.

    Indexed is an 8-bit mode, so such a document is malformed -- but it parses,
    and it keeps its stored width. Tripling it would reject a file three times
    smaller than the estimate claimed, which is the false-positive direction.
    """
    psd = _forge(4, 4, 1, depth, ColorMode.INDEXED)
    assert _image_data_planes(psd) == 1  # not tripled
    assert psd.numpy().nbytes == 4 * 4 * 1 * 4
    _assert_budget_brackets_the_model(
        lambda budget=None: _forge(4, 4, 1, depth, ColorMode.INDEXED, budget)
    )


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
    """Outside the palette expansion, the stored count *is* the array's width.

    Including where the header disagrees with its colour mode. Such files parse
    fine and produce a narrow array -- a one-channel RGB document returns
    ``(h, w, 1)`` -- so resolving the width from the colour mode instead would
    reject them at up to four times their real size.
    """
    psd = _forge(4, 4, channels, 8, color_mode)
    assert _image_data_planes(psd) == channels
    assert psd.numpy().nbytes == 4 * 4 * channels * 4
    _assert_budget_brackets_the_model(
        lambda budget=None: _forge(4, 4, channels, 8, color_mode, budget)
    )


@pytest.mark.parametrize("channel", [None, "color", "shape", "alpha", "mask"])
@pytest.mark.parametrize("filename", _COLORMODE_FIXTURES)
def test_numpy_guard_model_covers_every_fixture_and_channel(
    filename: str, channel: Optional[_Channel]
) -> None:
    """No shipped fixture may be rejected at a budget its own model admits.

    The corpus sweep: every colour mode and all four depths -- bitmap included,
    since #737 gave the estimate a depth term; see the depth-1 section below for
    what that has to get right.

    Swept over ``channel`` as well, because the model has to describe whichever
    branch the argument selects. ``numpy("mask")``, and ``numpy("shape")`` on a
    document with no transparency, synthesise their answer without reading the
    image data at all, and are modelled `flat`; the bracket is what catches the
    guard being handed the other branch's number.

    The independent half is `nbytes`: whatever else the model counts, it may not
    come out below the buffer the call materialises. Note that this is a floor
    and no longer an equality -- ``numpy("color")`` and ``numpy("shape")`` return
    *views* into the full array, so the returned array's own ``nbytes`` is not
    what was allocated, and the peak sits above the whole buffer besides.
    """
    psd = _colormode(filename)
    flat = channel == "mask" or (channel == "shape" and not has_transparency(psd))
    model = _numpy_peak_bytes(psd, flat)
    buffered = 4 * 4 * 1 * 4 if flat else psd.numpy(None).nbytes
    assert model >= buffered
    _colormode(filename, model).numpy(channel)
    with pytest.raises(ValueError, match="configured budget"):
        _colormode(filename, model - 1).numpy(channel)


@pytest.mark.parametrize("channel", ["mask", "shape"])
@pytest.mark.parametrize(
    "filename", ["4x4_8bit_index_color.psd", "4x4_8bit_cmyk.psd", "4x4_8bit_rgb.psd"]
)
def test_numpy_guard_estimate_matches_the_synthesised_paths(
    filename: str, channel: _Channel
) -> None:
    """A mask, and a shape on a document with no transparency, allocate one plane.

    Both are returned as synthesised ``(h, w, 1)`` arrays without the image data
    being read at all, so estimating them at the stored width rejects a request
    that fits several times over -- a quarter of the header's implication on
    CMYK, a third on indexed once the palette expansion is counted.

    Raised by review on #732. The over-estimate predates it for every
    multi-channel mode; sizing indexed by its expanded width would have added a
    third case rather than introducing the problem.
    """
    one_plane = 4 * 4 * 1 * 4
    assert _colormode(filename).numpy(channel).nbytes == one_plane
    assert _image_data_planes(_colormode(filename)) > 1  # the stored width differs
    assert _numpy_peak_bytes(_colormode(filename), True) == one_plane
    _colormode(filename, one_plane).numpy(channel)


@pytest.mark.parametrize("filename", _COLORMODE_FIXTURES)
def test_the_flat_numpy_paths_are_charged_four_bytes_a_pixel(filename: str) -> None:
    """And charged for nothing else: they never read the image data.

    ``np.ones((h, w, 1))`` is the whole of what the flat branch allocates. There
    is no compressed body to inflate, no float32 pair held while a rescale runs
    and no background to remove, so the model carries no term for any of them --
    which is the difference between a peak model and a blanket multiplier over
    the returned size. Swept over the whole corpus because the document's own
    shape is exactly what this branch is entitled to ignore: a five-channel
    16-bit CMYK document and a 1-bit bitmap have to be quoted the same number.
    """
    psd = _colormode(filename)
    flat = psd.width * psd.height * 4
    assert _numpy_peak_bytes(psd, True) == flat
    # Strictly below the same document's full read, which does carry those
    # terms -- so the equality above is not a coincidence of size.
    assert _numpy_peak_bytes(psd, True) < _numpy_peak_bytes(psd, False)
    # And the guard admits the flat paths at exactly that, rejecting a byte less.
    _colormode(filename, flat).numpy("mask")
    with pytest.raises(ValueError, match="configured budget"):
        _colormode(filename, flat - 1).numpy("mask")


# ---------------------------------------------------------------------------
# The numpy model against a measured peak
# ---------------------------------------------------------------------------
#
# The section above pins what the guard compares against. This one pins that the
# thing being compared is true, which is the assertion that keeps the model
# honest as `get_image_data()` moves underneath it. numpy registers its own
# domain with `tracemalloc`, so every array the path builds is visible here.
# (PIL's are not -- they are C-side -- which is why the PIL model is asserted
# structurally further down.)

# `tracemalloc` charges its own bookkeeping to the peak it reports: measured at
# 5,737 bytes on a 300 px document, 5,737 on a 600 px one and 5,786 on a 1200 px
# one -- flat across a sixteenfold range in pixel count, so it is an artefact of
# the instrument rather than an allocation the model should carry. Hence an
# absolute tolerance rather than a proportional one.
#
# It has to stay well *below* the smallest term the sweep is meant to detect, or
# it silently absorbs one. The narrowest is the ZIP entry in `_DECOMPRESS_PEAK`,
# worth 0.27 bytes a pixel at depth 32 -- about 40 KB at `_PEAK_SIZE` -- so this
# is sized against that rather than only against the noise it corrects. At 64 KB
# and a 256 px canvas, dropping that entry from 3 to 1 left every assertion here
# passing.
_TRACE_SLACK = 16 * 1024

# How far above the measured peak the model is allowed to sit. The largest
# structural over-count is 2.0x, on a depth-32 RAW document: the model charges
# for the source buffer even where `get_data()` hands back the bytes read at
# open time (a documented exclusion -- a body longer than the declared length
# *is* copied, and this guard exists for malformed files), and depth 32 is the
# one branch with no parse transient to dwarf it.
#
# The rest of the headroom is for platform variation, which is real and was
# found by this test rather than anticipated: `_remove_background()` costs 39
# bytes a pixel on macOS and 48 on Linux and Windows, so
# `_BACKGROUND_TRANSIENT` is sized on the latter and overshoots on the former.
# 3 still fails loudly at the shape of mistake worth catching -- a term counted
# twice, or the three phases summed instead of maxed, lands at 3-4x or beyond.
_MODEL_OVERSHOOT = 3

# 384 px a side. Two constraints meet here. The thinnest model in the sweep is a
# one-channel bitmap at ~6 bytes a pixel, ~900 KB at this size and so far above
# `_TRACE_SLACK` that the tolerance is a correction rather than the assertion.
# And the narrowest per-pixel term, ZIP at depth 32, has to clear that tolerance:
# 0.27 bytes a pixel is ~40 KB here, comfortably over it, where a 256 px canvas
# left it under.
_PEAK_SIZE = 384

# Colour mode, stored channels and depth, chosen to reach every branch of the
# model rather than to enumerate the format: the palette expansion (indexed at
# depth 8, at one channel and at three), the background removal (RGB with a
# fourth plane, whose transient is the largest single term), the depth-1 row
# padding, the depth-32 branch that needs no rescale and so has no parse
# transient, and the modes that pass straight through at their stored width.
_PEAK_DOCUMENTS = [
    (ColorMode.BITMAP, 1, 1),
    (ColorMode.GRAYSCALE, 2, 1),
    (ColorMode.RGB, 4, 1),
    (ColorMode.GRAYSCALE, 1, 8),
    (ColorMode.INDEXED, 1, 8),
    (ColorMode.INDEXED, 3, 8),
    (ColorMode.RGB, 3, 8),
    (ColorMode.RGB, 4, 8),
    (ColorMode.CMYK, 5, 8),
    (ColorMode.LAB, 3, 8),
    (ColorMode.MULTICHANNEL, 2, 8),
    (ColorMode.RGB, 4, 16),
    (ColorMode.CMYK, 4, 16),
    (ColorMode.GRAYSCALE, 1, 32),
    (ColorMode.RGB, 3, 32),
    (ColorMode.RGB, 4, 32),
]


def _traced_peak(call: Callable[[], Any]) -> int:
    """Bytes *call* allocates at its high-water mark, per ``tracemalloc``.

    The document is opened *outside* the traced region deliberately. The model
    counts the compressed body among the bytes the call holds live, but for
    ``Compression.RAW`` ``get_data()`` usually hands back the very object read at
    open time and allocates nothing -- tracing the open too would credit the
    call with that allocation and hide the over-count instead of exposing it.
    """
    gc.collect()
    tracemalloc.start()
    try:
        gc.collect()
        tracemalloc.reset_peak()
        before, _ = tracemalloc.get_traced_memory()
        result = call()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    del result
    return peak - before


@pytest.mark.parametrize("compression", list(Compression))
@pytest.mark.parametrize("color_mode, channels, depth", _PEAK_DOCUMENTS)
def test_numpy_peak_model_brackets_the_measured_peak(
    color_mode: int, channels: int, depth: int, compression: Compression
) -> None:
    """The model is above what `numpy()` really allocates, and not far above.

    Swept over the compression methods as well as the header, because three of
    the four decompress into a buffer they build -- RLE joins materialised rows,
    prediction adds an ``array.array`` pass and a byte-order pass on top of the
    inflate -- and only RAW does not. A model fitted on raw bodies alone would
    have no codec term at all and would still look exact.

    Both directions are asserted for the reason the guard has two failure modes:
    a model below the peak is a guard that does not guard, and a model far above
    it is a guard that refuses files it should have passed.
    """
    if depth == 1 and compression == Compression.ZIP_WITH_PREDICTION:
        # `compress()` refuses the combination outright ("Invalid pixel size 1"),
        # and so it can never reach the reader.
        pytest.skip("prediction is not defined at depth 1")
    psd = _forge(
        _PEAK_SIZE, _PEAK_SIZE, channels, depth, color_mode, compression=compression
    )
    model = _numpy_peak_bytes(psd)
    # Without this the tolerance below could be doing all the work.
    assert model > 4 * _TRACE_SLACK
    peak = _traced_peak(psd.numpy)
    assert peak <= model + _TRACE_SLACK, (
        f"peak {peak:,} allocated past a model of {model:,}"
    )
    assert model <= _MODEL_OVERSHOOT * peak, (
        f"model {model:,} is more than {_MODEL_OVERSHOOT}x the {peak:,} measured"
    )


# ---------------------------------------------------------------------------
# Depth 1: one float32 per pixel, like every other depth (#737, #768)
# ---------------------------------------------------------------------------
#
# #737 found the array here following the *byte* count rather than the pixel
# count: `np.unpackbits` yields a value per bit, and `decompress()`'s `length`
# counted a byte per pixel, so a body written that wide was returned whole and
# unpacked to eight planes against a one-plane header. The estimate closed that
# by asking the codec how many bytes it would really produce.
#
# #768 removed both halves of the mismatch. `length` counts packed rows, so an
# oversized body is truncated (RAW) or refused (ZIP) rather than returned; and
# `_parse_array()` trims each row's padding bits, so the array is one value per
# pixel.
#
# That is still the subject here, and it is a claim about the array rather than
# about the budget: the width the header declares is the width that is
# allocated, at the widths that are not a multiple of eight above all, which is
# where the two arithmetics used to part company. The peak the guard is now
# given sits above that array -- about six bytes a pixel rather than four, the
# packed buffer and `_parse_array()`'s two uint8 temporaries riding along with
# it -- so the array is asserted on `nbytes` and the budget is bracketed
# against the model separately.


def _forge_1bit(
    width: int,
    height: int,
    channels: int,
    color_mode: int,
    compression: Compression,
    body: str = "packed",
    max_alloc_bytes: int | None = None,
) -> PSDImage:
    """A structurally valid 1-bit document with a body of the requested shape.

    ``"packed"`` is ``height * channels`` rows of ``ceil(width / 8)`` bytes:
    what a conforming writer packs, and since #768 what the codecs read. Every
    width below is exercised in both classes, a multiple of eight and not, the
    padded row being the whole of what the two arithmetics disagreed about.
    ``"padded"`` is one byte per pixel -- ``decompress()``'s own ``length`` at
    depth 1 before #768, eight times the packed size -- which is the crafted
    body that used to get eight times the allocation past the estimate.
    """
    rows = height * channels
    if body == "packed":
        payload = bytes(rows * ((width + 7) // 8))
    else:
        payload = bytes(width * rows)
    buf = io.BytesIO()
    buf.write(
        struct.pack(">4sH6xHIIHH", b"8BPS", 1, channels, height, width, 1, color_mode)
    )
    buf.write(struct.pack(">I", 0))  # colour mode data
    buf.write(struct.pack(">I", 0))  # image resources
    buf.write(struct.pack(">I", 0))  # layer and mask info
    buf.write(struct.pack(">H", compression))
    buf.write(compress(payload, compression, width, rows, 1, 1))
    buf.seek(0)
    return PSDImage.open(buf, max_alloc_bytes=max_alloc_bytes)


# Widths on both sides of the byte boundary. The last three carry padding bits
# -- 20 pixels in three bytes, 5 and 4 in one -- and before #768 none of them
# could form an array at all: 8 * ceil(w/8) values per row either did not divide
# by `width` or divided into the wrong shape.
_DEPTH_1_DOCUMENTS = [
    (64, 64, 1, ColorMode.BITMAP),
    (64, 64, 1, ColorMode.GRAYSCALE),
    (64, 64, 3, ColorMode.RGB),
    (8, 3, 1, ColorMode.BITMAP),
    (20, 3, 1, ColorMode.BITMAP),
    (5, 5, 2, ColorMode.GRAYSCALE),
    (4, 4, 1, ColorMode.BITMAP),
]


@pytest.mark.parametrize(
    "compression", [Compression.RAW, Compression.RLE, Compression.ZIP]
)
@pytest.mark.parametrize("width, height, channels, color_mode", _DEPTH_1_DOCUMENTS)
def test_the_depth_1_array_is_one_float32_per_pixel(
    width: int,
    height: int,
    channels: int,
    color_mode: int,
    compression: Compression,
) -> None:
    """Every depth-1 combination, on a conforming body.

    Exact, not merely bounded, and for ZIP too: #737 had to accept an eightfold
    over-estimate there, the inflated size being unknowable without inflating,
    but the ceiling it is bounded at is now the packed size and a conforming
    body reaches it. The budget bracket rides alongside because depth 1 is the
    one depth whose source term is not a whole number of bytes per pixel, so it
    is the one most easily got wrong in the model as well as in the array.
    """
    psd = _forge_1bit(width, height, channels, color_mode, compression)
    assert _image_data_planes(psd) == channels
    assert psd.numpy().nbytes == width * height * channels * 4
    _assert_budget_brackets_the_model(
        lambda budget=None: _forge_1bit(
            width, height, channels, color_mode, compression, "packed", budget
        )
    )


@pytest.mark.parametrize("compression", [Compression.RAW, Compression.ZIP])
def test_a_byte_per_pixel_1bit_body_no_longer_outgrows_its_header(
    compression: Compression,
) -> None:
    """#737's reproduction, which the row arithmetic closes at the source.

    A 64x64 1-bit document whose body is written a byte per pixel returned
    ``(64, 64, 8)`` -- 131,072 bytes against a 16,384-byte estimate -- because
    ``length`` was that wide too and nothing cut it back. #737 raised the
    estimate to meet it; #768 removes the eight extra planes instead. RAW
    truncates the body to the rows the header declares, and ZIP refuses a stream
    that inflates past them, so either way the array is the one plane the header
    always said it was.

    The number this used to be checked against, ``64 * 64 * 1 * 4``, is no
    longer the one the guard holds -- the depth-1 peak is nearer six bytes a
    pixel than four -- but the claim never was about that constant. It is about
    which count the constant multiplies: a float32 per *pixel*, not per *bit*.
    So the array is asserted at a pixel apiece, and the whole modelled peak --
    packed buffer, result and every transient at once -- is asserted to stay
    inside the bare eight-plane array the crafted body used to produce.
    """
    per_pixel = 64 * 64 * 1 * 4
    per_bit = 64 * 64 * 8 * 4
    model = _numpy_peak_bytes(
        _forge_1bit(64, 64, 1, ColorMode.BITMAP, compression, "padded")
    )
    assert model < per_bit
    psd = _forge_1bit(64, 64, 1, ColorMode.BITMAP, compression, "padded", model)
    assert _image_data_planes(psd) == 1
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", _compression.PSDDecompressionWarning)
        assert psd.numpy().nbytes == per_pixel


def test_numpy_guard_estimate_covers_the_shipped_bitmap_fixture() -> None:
    """``4x4_1bit_bitmap.psd``: the header's one plane, and exactly it.

    The oldest 1-bit document in the corpus, RAW with a properly packed body,
    four bytes for four rows. Its four-pixel row fills a whole byte, so it used
    to unpack to twice its pixel count -- the 2.0x reading in #737 -- and came
    back ``(4, 4, 2)``, half of it padding. Trimming the padding makes the
    header's own count the array's width.
    """
    psd = _colormode("4x4_1bit_bitmap.psd")
    assert psd._record.image_data.compression == Compression.RAW
    assert len(psd._record.image_data.data) == 4  # packed: one byte per row
    assert psd.channels == 1
    assert _image_data_planes(psd) == 1
    assert psd.numpy().nbytes == 4 * 4 * 1 * 4
    _assert_budget_brackets_the_model(
        lambda budget=None: _colormode("4x4_1bit_bitmap.psd", budget)
    )


@pytest.mark.parametrize(
    "filename, width, height",
    [("20x5_1bit_bitmap.psd", 20, 5), ("100x20_1bit_bitmap_rle.psd", 100, 20)],
)
def test_the_depth_1_array_is_exact_for_a_padded_width(
    filename: str, width: int, height: int
) -> None:
    """The same claim on the two Photoshop documents whose width pads.

    Forged headers cover the combinations no file has; these two are the real
    thing, RAW and RLE, at a width that is not a multiple of eight. Before #768
    neither could be measured at all -- ``numpy()`` raised on the reshape.
    """
    assert _colormode(filename).numpy().nbytes == width * height * 1 * 4
    _assert_budget_brackets_the_model(lambda budget=None: _colormode(filename, budget))


def test_composite_guard_model_brackets_the_bitmap_fixture() -> None:
    """The same bracket through ``composite()``, the shipped 1-bit path.

    A layerless document composites by reading its own image data, so the
    depth-1 model is what bounds it -- with ``ignore_preview=True``, since the
    default path returns the flattened preview through
    :func:`~psd_tools.api.pil_io.convert_image_data_to_pil` and is bounded by
    the PIL model instead.

    ``composite()`` keeps the returned-size spelling of its own estimate, its
    peak growing with the layer count rather than with the canvas, so the number
    that binds here is the wider of the two: the model `numpy()` was given.
    """
    pytest.importorskip("aggdraw")
    pytest.importorskip("scipy")
    pytest.importorskip("skimage")
    name = "4x4_1bit_bitmap.psd"
    model = _numpy_peak_bytes(_colormode(name))
    assert model > 4 * 4 * 1 * 4  # wider than composite()'s own estimate
    _colormode(name, model).composite(ignore_preview=True)
    with pytest.raises(ValueError, match="configured budget"):
        _colormode(name, model - 1).composite(ignore_preview=True)


def test_a_short_1bit_body_still_cannot_be_shaped() -> None:
    """A body that does not fill the header's rows has no geometry to recover.

    ``_parse_array()`` drops the part-row a truncated body ends on, and the
    reshape then fails for want of whole planes. Unchanged by #768 and
    deliberately so: raising here is what depth 8 and up already do, through the
    length-mismatch check, and the alternative would be inventing rows.
    """
    psd = _forge_1bit(20, 3, 1, ColorMode.BITMAP, Compression.RAW, "packed")
    psd._record.image_data.data = psd._record.image_data.data[:5]  # under two rows
    assert _image_data_planes(psd) == 1  # the estimate is the header's, and holds
    with pytest.raises(ValueError, match="reshape"):
        psd.numpy()


def test_a_zip_stream_one_byte_over_length_is_refused() -> None:
    """The boundary case in ``_safe_zlib_decompress``'s own ceiling.

    It asks zlib for ``max_length + 1`` bytes so an oversize stream gives a byte
    away instead of ending exactly at the limit -- and a stream inflating to
    precisely that handed the byte back: all its input consumed, no
    ``unconsumed_tail`` left to catch it. At depth 1 those eight extra bits
    became eight more float32 values than any arithmetic over ``length`` could
    reach (#737).

    The ceiling holds, so the channel is refused -- and since #768 refusing it
    yields a black channel rather than ending the read, ``length`` counting
    packed rows being what makes a 1-bit fill expressible.
    """
    psd = _forge_1bit(8, 1, 1, ColorMode.BITMAP, Compression.ZIP, "packed")
    psd._record.image_data.data = zlib.compress(bytes(1 + 1))  # `length` + 1
    with pytest.warns(_compression.PSDDecompressionWarning, match="exceeds expected"):
        array = psd.numpy()
    assert array.shape == (1, 8, 1)
    assert not array.any()  # black, which for a bitmap document is 0.0


def test_16bit_degraded_image_data_keeps_its_declared_width() -> None:
    """16-bit image data that fails to decode black-fills at its declared width.

    ``decompress()``'s substitute was a PIL image whose mode came from the depth
    -- ``"L"`` for 8, ``"RGBA"`` for anything else -- so depth 16 came back at
    four bytes per pixel against a ``length`` of two, and parsed twice as wide:
    a 4x4 RGB document read ``(4, 4, 6)``, 384 bytes, against a 192-byte
    estimate, and a budget of exactly 192 admitted it.

    Note what fails together here. :py:meth:`ImageData.get_data` decompresses
    every channel in one call, so a corrupt merged section fails as a unit; the
    same substitute serves the per-channel readers, ``ChannelData.get_data()``
    for layers and the pattern reader, which were wrong at depth 16 the same
    way.

    The estimate is unchanged; what was wrong was the array. Bracketed here
    rather than merely bounded, because the fill is now exactly ``length`` --
    a degraded read allocates what a sound one would, so the model that was
    quoted for the sound document has to hold for this one too.
    """
    corrupt = b"\x78\x9c" + b"\xff" * 20  # valid zlib header, garbage deflate

    def open_doc(budget: int | None = None) -> PSDImage:
        psd = _forge(4, 4, 3, 16, ColorMode.RGB, budget)
        psd._record.image_data.compression = Compression.ZIP
        psd._record.image_data.data = corrupt
        return psd

    with pytest.warns(_compression.PSDDecompressionWarning):
        array = open_doc().numpy()
    assert array.shape == (4, 4, 3)  # three planes, as the header declares
    assert array.nbytes == 4 * 4 * 3 * 4
    model = _numpy_peak_bytes(open_doc())
    with pytest.warns(_compression.PSDDecompressionWarning):
        open_doc(model).numpy()
    with pytest.raises(ValueError, match="configured budget"):
        open_doc(model - 1).numpy()


# ---------------------------------------------------------------------------
# The PIL model, which cannot be measured (#767)
# ---------------------------------------------------------------------------
#
# PIL's buffers are allocated C-side and `tracemalloc` never sees them, so the
# sweep above has no counterpart here. What can be asserted instead is the
# model's structure: that it stays above the image the call hands back, and that
# every term gated on a branch really is gated -- because ungating them is the
# way this model would silently become the over-estimate it replaced, and #767
# is as much about that direction as about the other. The old
# `width * height * channels * 4` was four bytes a pixel per stored channel, a
# float32 plane; `_create_image()` yields "L", "P" or "1" and PIL stores a byte
# per pixel in all three, so an 8-bit multi-band document was turned away well
# below its real footprint.
#
# A whole-call RSS delta would see some of this, and it is deliberately not
# written into the suite: RSS answers with the allocator's arena rather than the
# program's request, it cannot see a phase that reuses what the phase before it
# released, and it varies enough between platforms and Pillow builds that gating
# CI on it would buy noise rather than coverage.


@pytest.mark.parametrize("filename", _COLORMODE_FIXTURES)
def test_pil_peak_model_stays_above_the_image_it_returns(filename: str) -> None:
    """The floor no model of this path may go under.

    Whatever the branches do in between, the image handed back is still live
    when the call returns, and every mode this path yields -- "1", "L", "P",
    "RGB", "CMYK", "LAB" -- stores one byte per pixel per band. So the returned
    image's own footprint is a lower bound that owes nothing to the model's
    arithmetic, which is what makes it worth asserting. Strictly above, not
    merely at: the decompressed buffer is live alongside it in every case.
    """
    psd = _colormode(filename)
    image = psd.topil()
    assert image is not None
    returned = image.width * image.height * len(image.getbands())
    model = _pil_peak_bytes(psd, None, True)
    assert model > returned
    _colormode(filename, model).topil()
    with pytest.raises(ValueError, match="configured budget"):
        _colormode(filename, model - 1).topil()


def test_pil_peak_model_does_not_charge_for_a_merge_that_never_happens() -> None:
    """Indexed and multichannel documents keep ``channels[0]`` and assemble nothing.

    Every other mode reaches ``Image.merge()``, which builds a second image as
    wide as the mode's band count while the per-channel images are still held.
    These two never do -- one puts a palette on the first channel, the other
    takes it as-is -- so charging them for it would put the model back above the
    ``width * height * channels * 4`` it replaced on exactly the 8-bit documents
    that motivated replacing it.

    Three otherwise identical forged headers isolate the term: same dimensions,
    same stored channel count, same depth, same codec, ICC off. The whole
    difference between them is the merge, and it comes to the three bands
    ``Image.merge()`` would have produced, at PIL's byte per pixel each.
    """
    rgb = _forge(4, 4, 3, 8, ColorMode.RGB)
    indexed = _forge(4, 4, 3, 8, ColorMode.INDEXED)
    multichannel = _forge(4, 4, 3, 8, ColorMode.MULTICHANNEL)
    merge = 4 * 4 * 3  # three bands, a byte a pixel
    assert _pil_peak_bytes(indexed, None, False) + merge == _pil_peak_bytes(
        rgb, None, False
    )
    assert _pil_peak_bytes(multichannel, None, False) == _pil_peak_bytes(
        indexed, None, False
    )


def test_pil_peak_model_does_not_charge_a_single_channel_for_the_assembly() -> None:
    """``topil(channel)`` builds one image and stops.

    Nothing is merged, there is no alpha to put and ``_remove_white_background()``
    cannot fire on one band, so the whole assembly phase is gated off. Asserted
    against the same document read whole, which is the only comparison that
    makes "does not pay for it" mean anything.
    """
    psd = _forge(4, 4, 3, 8, ColorMode.RGB)
    assert _pil_peak_bytes(psd, 0, False) < _pil_peak_bytes(psd, None, False)


def test_pil_peak_model_does_not_charge_for_a_background_it_never_removes() -> None:
    """``_remove_white_background()`` only ever sees an RGBA image.

    It is the single largest term in this model -- four split bands, three
    ``ImageMath`` widenings to "I", three "L" results and a merge, some 35 bytes
    a pixel -- and it fires only when the document declares transparency for its
    merged preview. A document without it must not be quoted for the phase.

    The two documents are the controlled pair the corpus happens to provide:
    both RGB, both four stored channels, both 8-bit, differing in whether
    ``has_transparency()`` holds. ``4x4_8bit_rgba.psd`` stores a fourth channel
    but declares no merged transparency for it, so ``post_process()`` never
    calls ``putalpha()``, the image it hands on is "RGB" rather than "RGBA", and
    ``_remove_white_background()`` returns it untouched. ``fill-opacity.psd``
    declares it and goes through the phase in full.
    Compared per pixel because the two are not the same size, and with ICC off
    so the profile term does not move underneath the comparison.
    """
    opaque = _colormode("4x4_8bit_rgba.psd")
    transparent = PSDImage.open(full_name("transparency/fill-opacity.psd"))
    assert not has_transparency(opaque) and has_transparency(transparent)
    for psd in (opaque, transparent):
        assert (psd.color_mode, psd.channels, psd.depth) == (ColorMode.RGB, 4, 8)

    def per_pixel(psd: PSDImage) -> float:
        return _pil_peak_bytes(psd, None, False) / (psd.width * psd.height)

    assert per_pixel(transparent) >= _WHITE_BACKGROUND_TRANSIENT
    assert per_pixel(opaque) < _WHITE_BACKGROUND_TRANSIENT


@pytest.mark.parametrize("depth", [16, 32])
def test_pil_peak_model_charges_the_deep_conversion_pair(depth: int) -> None:
    """The transient #767 was opened about, pinned directly.

    ``_create_image()`` reads a 16- or 32-bit channel into an "I"/"F" image at
    four bytes a pixel and then allocates a second through ``.point()`` before
    narrowing to "L". Both are alive at once, and at depth 8 neither exists --
    the buffer becomes an "L" and nothing else. The old estimate charged
    ``channels * 4`` whatever the depth and so could not tell the two cases
    apart, which is the whole of the issue.

    Held against the same header at depth 8. The excess over that is *not* the
    term itself, and the assertion deliberately does not claim it is: the model
    is a maximum over phases, and raising the depth can change which phase binds
    -- at depth 8 this document is bounded by assembling the merged image, at 16
    and 32 by the conversion. What the comparison does establish is that the
    deeper document costs more than its wider source buffer alone accounts for,
    which is exactly what fails if the pair stops being counted.
    """
    pixels = 4 * 4
    shallow = _pil_peak_bytes(_forge(4, 4, 3, 8, ColorMode.RGB), None, False)
    deep = _pil_peak_bytes(_forge(4, 4, 3, depth, ColorMode.RGB), None, False)
    source_growth = pixels * 3 * (depth // 8 - 1)
    assert deep > shallow + source_growth


def test_pil_peak_model_charges_one_conversion_pair_however_many_channels() -> None:
    """The pair is flat, not per-channel: the loop converts one at a time.

    Three more stored channels buy three more source buffers and three more "L"
    images -- and not a second "I" pair.

    Multichannel at depth 16 is what makes the comparison controlled. Widening
    an RGB header from three to six would cross ``has_transparency()`` and
    switch on the white-background term, so the difference would measure that
    instead; multichannel's expected count is 64, so both widths stay opaque and
    the only thing that moves is the channel count. Depth 16 rather than 32
    because at 32 a six-channel document is bounded by its codec phase, and this
    is about the conversion phase.
    """
    pixels = 4 * 4
    narrow = _pil_peak_bytes(_forge(4, 4, 3, 16, ColorMode.MULTICHANNEL), None, False)
    wider = _pil_peak_bytes(_forge(4, 4, 6, 16, ColorMode.MULTICHANNEL), None, False)
    assert not has_transparency(_forge(4, 4, 6, 16, ColorMode.MULTICHANNEL))
    assert wider - narrow == pixels * 3 * (2 + 1)


def test_pil_peak_model_charges_a_profile_that_widens_to_rgba() -> None:
    """A profile can send a grayscale document through the background removal.

    ``_apply_icc()`` writes RGB whatever it was given, so a document that is
    neither RGB nor free of transparency still ends up "RGBA" once
    ``post_process()`` puts the alpha back -- and then
    ``_remove_white_background()`` runs in full. Gating that term on the
    document's own colour mode reads naturally and is wrong: this fixture is
    grayscale, and ``topil()`` really does return "RGBA" with the profile
    applied and "LA" without.

    So the model has to ask what the image will *become*, not what the header
    says it is. Asserted through the public ``apply_icc`` switch, which is the
    only thing separating the two answers, and per pixel against the term
    itself rather than as a difference -- the two answers are bounded by
    different phases, so subtracting them does not leave the term behind.
    """
    psd = PSDImage.open(full_name("blend-modes/gray-blend-modes.psd"))
    assert psd.color_mode == ColorMode.GRAYSCALE and has_transparency(psd)
    assert Resource.ICC_PROFILE in psd.image_resources
    with_profile, without_profile = (
        psd.topil(apply_icc=True),
        psd.topil(apply_icc=False),
    )
    assert with_profile is not None and without_profile is not None
    assert (with_profile.mode, without_profile.mode) == ("RGBA", "LA")

    pixels = psd.width * psd.height
    assert _pil_peak_bytes(psd, None, True) >= pixels * _WHITE_BACKGROUND_TRANSIENT
    assert _pil_peak_bytes(psd, None, False) < pixels * _WHITE_BACKGROUND_TRANSIENT


def test_pil_peak_model_charges_a_profile_on_a_mode_that_is_not_rgb() -> None:
    """The ``icc`` half of the widening gate, which no fixture can reach.

    ``gray-blend-modes.psd`` above proves the profile changes the *width* of
    what is widened, but not that the profile is what lets the widening happen
    at all: grayscale is already in ``("RGB", "L")``, so ``putalpha()`` would
    fire for it either way. The clause exists for the modes that are not --
    CMYK, LAB, indexed -- where nothing widens unless a profile has first
    rewritten the image to RGB.

    No shipped document is a non-RGB, non-grayscale mode carrying both a profile
    and transparency, so the header is forged. Only the profile's *presence* is
    forged with it: this asserts on the model, which asks whether the resource
    is there and never decodes it.
    """
    psd = _forge(4, 4, 5, 8, ColorMode.CMYK, icc=True)
    assert has_transparency(psd) and Resource.ICC_PROFILE in psd.image_resources
    pixels = psd.width * psd.height

    assert _pil_peak_bytes(psd, None, True) >= pixels * _WHITE_BACKGROUND_TRANSIENT
    # Same document, profile ignored: "CMYK" never becomes "RGBA", so the phase
    # does not run and must not be quoted for.
    assert _pil_peak_bytes(psd, None, False) < pixels * _WHITE_BACKGROUND_TRANSIENT


@pytest.mark.parametrize(
    (
        "color_mode",
        "channels",
        "depth",
        "icc",
        "channel",
        "compression",
        "expected",
        "binding",
    ),
    [
        # 48 source + 16 * (3 channels + 1 slack) retained, then 16 * (3 merged
        # + 1 the background removal would be handed).
        (ColorMode.RGB, 3, 8, False, None, Compression.RAW, 176, "the merged image"),
        # 64 source + 16 * (4 + 1), then 16 * (4 merged + 4 for the inversion
        # `post_process()` holds alongside it).
        (ColorMode.CMYK, 4, 8, False, None, Compression.RAW, 272, "the CMYK inversion"),
        # Same RGB document with a profile and still no alpha: `_apply_icc()`
        # holds its input beside the RGB it writes, and nothing widens after.
        (ColorMode.RGB, 3, 8, True, None, Compression.RAW, 256, "the ICC output"),
        # Grayscale with alpha: `putalpha()` holds "L" and "LA" together. No
        # background phase -- one band never becomes RGBA without a profile.
        (
            ColorMode.GRAYSCALE,
            2,
            8,
            False,
            None,
            Compression.RAW,
            144,
            "putalpha widening L to LA",
        ),
        # Eight 32-bit channels: 512 bytes of source, and twice that while the
        # codec runs, is wider than anything the assembly does.
        (
            ColorMode.MULTICHANNEL,
            8,
            32,
            False,
            None,
            Compression.RAW,
            1024,
            "the codec, raw",
        ),
        # The same document under each codec that builds its result rather than
        # handing back the bytes read at open: RLE joins materialised rows, and
        # prediction adds an `array.array` pass and a byte-order pass on top of
        # the inflate. Only here, where the codec phase is the widest, do these
        # multiples show up in a total at all.
        (
            ColorMode.MULTICHANNEL,
            8,
            32,
            False,
            None,
            Compression.RLE,
            1536,
            "the codec, RLE",
        ),
        (
            ColorMode.MULTICHANNEL,
            8,
            32,
            False,
            None,
            Compression.ZIP,
            1536,
            "the codec, ZIP",
        ),
        (
            ColorMode.MULTICHANNEL,
            8,
            32,
            False,
            None,
            Compression.ZIP_WITH_PREDICTION,
            2048,
            "the codec, ZIP with prediction",
        ),
        # A single channel asked for by index: one conversion pair and one "L",
        # and none of the assembly. At depth 16 so the pair is what binds.
        (
            ColorMode.RGB,
            3,
            16,
            False,
            0,
            Compression.RAW,
            240,
            "one conversion pair",
        ),
    ],
)
def test_pil_peak_model_adds_up_to_a_fixed_number(
    color_mode: int,
    channels: int,
    depth: int,
    icc: bool,
    channel: int | None,
    compression: Compression,
    expected: int,
    binding: str,
) -> None:
    """Whole models against literals, so no constant can quietly vanish.

    The gating tests each hold two models against each other, which pins the
    differences between them and not the constants they share -- and a test that
    rebuilt the expected figure from the module's own constants would move
    whenever they did, which is no test at all. These are written out as plain
    integers for that reason: changing any term changes a number here, and the
    change has to be deliberate.

    The rows are not a sample of the format. Each is the narrowest document that
    makes a different phase the binding one, because a term only shows up in the
    total when its phase wins the maximum -- which is why they are spread across
    depths, modes and the ``apply_icc`` switch rather than enumerating headers.
    ``_ALLOCATOR_SLACK`` in particular has nowhere else to be asserted: it covers
    what PIL's arena rounds each image up to, real enough to be why the RSS
    figures sat above a byte count, but invisible to any instrument cheap enough
    for CI.
    """
    psd = _forge(4, 4, channels, depth, color_mode, compression=compression, icc=icc)
    assert psd._record.image_data.compression == compression
    assert (Resource.ICC_PROFILE in psd.image_resources) is icc
    assert _pil_peak_bytes(psd, channel, icc) == expected, (
        f"the phase that binds here is {binding}"
    )


def test_check_pixel_size_still_defaults_to_the_returned_array() -> None:
    """Without ``estimated_bytes`` the comparand is ``w * h * channels * 4``.

    :func:`~psd_tools.composite.composite.composite` still calls it that way and
    deliberately so: what follows *its* guard grows with the layer count, so no
    expression in ``width * height * <constant>`` bounds it, and the canvas is
    the only thing the number can honestly describe. The default therefore has
    to keep working, and the error message has to say which of the two it is
    reporting -- a reader handed "Peak allocation" cannot rederive it from the
    dimensions, and one handed "Estimated allocation" should not have to try.
    """
    returned = 4 * 4 * 3 * 4
    check_pixel_size(4, 4, 3, max_alloc_bytes=returned)
    with pytest.raises(ValueError, match="Estimated allocation 192 bytes"):
        check_pixel_size(4, 4, 3, max_alloc_bytes=returned - 1)
    # A model replaces that product outright rather than being added to it: 192
    # bytes would be over this budget several times over, and it is not consulted.
    check_pixel_size(4, 4, 3, max_alloc_bytes=8, estimated_bytes=8)
    with pytest.raises(ValueError, match="Peak allocation 1,000 bytes"):
        check_pixel_size(4, 4, 3, max_alloc_bytes=999, estimated_bytes=1000)
