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
import zlib

import pytest

from typing import Any, Literal, Optional

from psd_tools import PSDImage, PSDLargeImageWarning
from psd_tools import compression as _compression
from psd_tools.compression import compress
from psd_tools.api import utils as _utils
from psd_tools.api.numpy_io import _image_data_planes
from psd_tools.api.utils import has_transparency
from psd_tools.constants import ColorMode, Compression
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


@pytest.mark.parametrize("channel", [None, "color", "shape", "alpha", "mask"])
@pytest.mark.parametrize("filename", _COLORMODE_FIXTURES)
def test_numpy_guard_estimate_never_exceeds_the_allocation(
    filename: str, channel: Optional[_Channel]
) -> None:
    """No shipped fixture may be rejected at a budget it actually fits inside.

    The same invariant as above swept over the real corpus, covering every
    colour mode and all four depths -- bitmap included, since #737 gave the
    estimate a depth term; see the depth-1 section below for what that has to
    get right.

    Swept over ``channel`` as well, because the estimate has to match whichever
    branch the argument selects -- see the synthesised paths below, which this
    parametrisation is what catches.

    Note what "the allocation" means for a channel argument. ``numpy("color")``
    and ``numpy("shape")`` return *views* into the full array -- on
    ``4x4_8bit_rgba.psd``, ``numpy("color")`` hands back 192 bytes of a 256-byte
    buffer -- so the returned array's ``nbytes`` is not what was allocated. The
    guard has to bound the buffer, so that is what is compared against.
    """
    psd = _colormode(filename)
    flat = channel == "mask" or (channel == "shape" and not has_transparency(psd))
    allocated = 4 * 4 * 1 * 4 if flat else psd.numpy(None).nbytes
    _colormode(filename, allocated).numpy(channel)


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

    Raised by review on this PR. The over-estimate predates it for every
    multi-channel mode; sizing indexed by its expanded width would have added a
    third case rather than introducing the problem.
    """
    one_plane = 4 * 4 * 1 * 4
    assert _colormode(filename).numpy(channel).nbytes == one_plane
    assert _image_data_planes(_colormode(filename)) > 1  # the stored width differs
    _colormode(filename, one_plane).numpy(channel)


# ---------------------------------------------------------------------------
# Depth 1: the estimate follows the codec, not the pixel count (#737)
# ---------------------------------------------------------------------------
#
# At depth 1 the byte count and the pixel count part company. `_parse_array()`
# unpacks the buffer with `np.unpackbits`, one float32 per *bit*, so the array
# is eight values per stored byte -- and `decompress()`'s `length` is
# `width * height` *bytes* at depth 1, eight times the packed size a row of
# `width` pixels actually occupies. A RAW or ZIP body written that wide is
# returned in full (the length check is skipped below depth 8), so the array
# came back eight times wider than the estimate assumed.
#
# The estimate therefore asks the codec rather than the header. Both directions
# are pinned below, as everywhere else in this file: exact for RAW and RLE,
# and for ZIP an upper bound, which is the one place this trades a false
# positive for closing the hole.


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

    ``"packed"`` is ``height * channels`` rows of ``max(width // 8, 1)`` bytes:
    the row size the codecs read, and for a width that is a multiple of eight
    also the row a conforming writer packs. (At any other width the two part
    company -- a row occupies ``ceil(width / 8)`` bytes and the reader floors
    it, which is #768. Every width parametrised below is a multiple of eight or
    smaller than eight, so that distinction does not arise here.) ``"padded"``
    is one byte per pixel -- ``decompress()``'s own ``length`` at depth 1, eight
    times the packed size -- which is what a crafted file supplies to get eight
    times the allocation out of the estimate.
    """
    rows = height * channels
    if body == "packed":
        payload = bytes(rows * max(width // 8, 1))
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


# Widths are multiples of eight, or below eight where the codecs' `max(..., 1)`
# row floor applies: at any other width the unpacked value count does not
# divide into `(-1, height, width)` and `numpy()` cannot form the array at all.
# `test_depth_1_estimate_rounds_up_a_part_used_plane` covers that case.
_DEPTH_1_DOCUMENTS = [
    (4, 4, 1, ColorMode.BITMAP),
    (64, 64, 1, ColorMode.BITMAP),
    (64, 64, 1, ColorMode.GRAYSCALE),
    (64, 64, 3, ColorMode.RGB),
    (8, 3, 1, ColorMode.BITMAP),
]


@pytest.mark.parametrize(
    "compression, body",
    [
        (Compression.RAW, "packed"),
        (Compression.RAW, "padded"),
        (Compression.RLE, "packed"),
        (Compression.ZIP, "padded"),
    ],
)
@pytest.mark.parametrize("width, height, channels, color_mode", _DEPTH_1_DOCUMENTS)
def test_numpy_guard_estimate_is_exact_at_depth_1(
    width: int,
    height: int,
    channels: int,
    color_mode: int,
    compression: Compression,
    body: str,
) -> None:
    """Every depth-1 combination whose allocation is knowable, bracketed.

    The ``"padded"`` rows are the under-count #737 reports -- eight planes where
    the header implies one -- and the ``"packed"`` rows are the documents that
    must not be rejected for it: a conforming 1-bit body allocates a single
    plane, and estimating it at eight would refuse a sound file. Both come out
    of the same arithmetic, which is the point.
    """
    _assert_estimate_is_exact(
        lambda budget=None: _forge_1bit(
            width, height, channels, color_mode, compression, body, budget
        )
    )


@pytest.mark.parametrize("compression", [Compression.RAW, Compression.ZIP])
def test_numpy_guard_rejects_the_padded_1bit_allocation(
    compression: Compression,
) -> None:
    """The issue's reproduction: 8x the budget, allocated without a raise.

    A 64x64 1-bit document returns ``(64, 64, 8)`` = 131,072 bytes; the estimate
    without a depth term put it at 16,384. The budget below is that old
    estimate, which must now be refused rather than exceeded eightfold.
    """
    budget = 64 * 64 * 1 * 4
    psd = _forge_1bit(64, 64, 1, ColorMode.BITMAP, compression, "padded", budget)
    with pytest.raises(ValueError, match="configured budget"):
        psd.numpy()
    # ... and the allocation it was hiding, for the record.
    assert (
        _forge_1bit(64, 64, 1, ColorMode.BITMAP, compression, "padded").numpy().nbytes
        == 8 * budget
    )


def test_numpy_guard_estimate_covers_the_shipped_bitmap_fixture() -> None:
    """``4x4_1bit_bitmap.psd`` allocates two planes, not the header's one.

    The one 1-bit document in the corpus, and the shape a real one has: RAW with
    a properly packed body, four bytes for four rows. A four-pixel row occupies
    a whole byte, so it unpacks to twice its pixel count -- the 2.0x reading in
    #737, well below the 8x a byte-per-pixel body reaches.

    So this is also the case a flat factor of eight would have broken: it would
    put this fixture at 512 bytes and reject it at the 128 it allocates. What
    admits it is the body's own length, ``min(len(data), length)``, which is the
    term that makes the estimate exact here rather than merely safe.
    """
    psd = _colormode("4x4_1bit_bitmap.psd")
    assert psd._record.image_data.compression == Compression.RAW
    assert len(psd._record.image_data.data) == 4  # packed: one byte per row
    assert psd.channels == 1  # the header says one plane...
    allocated = _assert_estimate_is_exact(
        lambda budget=None: _colormode("4x4_1bit_bitmap.psd", budget)
    )
    assert allocated == 4 * 4 * 2 * 4  # ...the array is two planes wide


def test_composite_guard_estimate_is_exact_for_the_bitmap_fixture() -> None:
    """The same bracket through ``composite()``, the shipped 1-bit path.

    A layerless document composites by reading its own image data, so the
    depth-1 estimate is what bounds it -- with ``ignore_preview=True``, since
    the default path returns the flattened preview through
    :func:`~psd_tools.api.pil_io.convert_image_data_to_pil` and is bounded by
    the PIL estimate instead.
    """
    pytest.importorskip("aggdraw")
    pytest.importorskip("scipy")
    pytest.importorskip("skimage")
    allocated = _colormode("4x4_1bit_bitmap.psd").numpy(None).nbytes
    _colormode("4x4_1bit_bitmap.psd", allocated).composite(ignore_preview=True)
    with pytest.raises(ValueError, match="configured budget"):
        _colormode("4x4_1bit_bitmap.psd", allocated - 1).composite(ignore_preview=True)


def test_zip_at_depth_1_is_bounded_rather_than_measured() -> None:
    """ZIP's inflated size is unknowable without inflating it, so the bound is ``length``.

    That is exact for the crafted body above and eight times over for a
    conforming one, the single over-estimate this fix accepts. It is the right
    way round: ``_safe_zlib_decompress()`` caps the output at ``length``, so a
    body of 26 bytes -- what ``length`` zero bytes deflate to for a 64x64
    channel -- really can become 131,072 bytes of float32. Nothing pays for the
    slack in practice: of the 293 documents in ``tests/psd_files``, 241 store
    their merged image data RLE and 52 RAW, and none uses either ZIP codec.
    """
    psd = _forge_1bit(64, 64, 1, ColorMode.BITMAP, Compression.ZIP, "packed")
    assert psd.numpy().nbytes == 64 * 64 * 1 * 4  # one plane, in fact
    assert _image_data_planes(psd) == 8  # bounded at `length`, eight times over


@pytest.mark.parametrize(
    "body_bytes, values, planes",
    [
        # Two bytes per row: 16 values against a 20-pixel row, four fifths of a
        # plane. Rounding down would floor the estimate to nothing at all.
        (3 * 2, 48, 1),
        # Between one and two planes' worth, the only shape that tells ceil from
        # floor once the `max(1, ...)` clamp is in play: floor says one plane,
        # 240 bytes, below the 320 the values really occupy.
        (10, 80, 2),
    ],
)
def test_depth_1_estimate_rounds_a_part_used_plane_up(
    body_bytes: int, values: int, planes: int
) -> None:
    """A width that is not a multiple of eight leaves a partial plane, which costs.

    A stored byte spans eight pixels and the rows here are 20 wide, so the
    unpacked values never land on a plane boundary. ``numpy()`` cannot form such
    an array at all -- neither 48 nor 80 values divide into ``(-1, 3, 20)`` --
    so what is pinned is the arithmetic, whose job is to stay above the values
    ``_parse_array()`` transiently holds either way.

    That the read fails is #768, not something this asserts is correct: the
    depth-1 path returns padding bits as pixels. When it stops doing so, the
    ``reshape`` expectation below is what should be revisited.
    """
    psd = _forge_1bit(20, 3, 1, ColorMode.BITMAP, Compression.RAW, "padded")
    psd._record.image_data.data = bytes(body_bytes)
    bound = psd._record.image_data.decompressed_size_bound(psd._record.header)
    assert 8 * bound == values
    assert _image_data_planes(psd) == planes
    assert planes * 20 * 3 >= values  # the estimate covers what is unpacked
    with pytest.raises(ValueError, match="reshape"):
        psd.numpy()


def test_a_zip_stream_one_byte_over_length_is_refused() -> None:
    """The boundary case in ``_safe_zlib_decompress``'s own ceiling.

    It asks zlib for ``max_length + 1`` bytes so an oversize stream gives a byte
    away instead of ending exactly at the limit -- and a stream inflating to
    precisely that handed the byte back: all its input consumed, no
    ``unconsumed_tail`` left to catch it. At depth 1 those eight extra bits
    became eight more float32 values than any arithmetic over ``length`` could
    reach: an 8x1 document returned ``(1, 8, 9)``, 288 bytes, against a
    256-byte estimate.

    The ceiling now holds, so the channel is refused. Below depth 8 that ends
    the read -- the black-fill fallback is gated on ``depth >= 8`` -- which is
    what any undecodable 1-bit channel has always done; from depth 8 up the same
    stream degrades to black instead of raising the length mismatch it used to.
    """
    psd = _forge_1bit(8, 1, 1, ColorMode.BITMAP, Compression.ZIP, "padded")
    psd._record.image_data.data = zlib.compress(bytes(8 * 1 + 1))  # `length` + 1
    with (
        pytest.warns(_compression.PSDDecompressionWarning, match="exceeds expected"),
        pytest.raises(RuntimeError, match="produced no result"),
    ):
        psd.numpy()


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
    rather than merely bounded, because the fill is now exactly ``length``.
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
    with pytest.warns(_compression.PSDDecompressionWarning):
        open_doc(array.nbytes).numpy()
    with pytest.raises(ValueError, match="configured budget"):
        open_doc(array.nbytes - 1).numpy()
