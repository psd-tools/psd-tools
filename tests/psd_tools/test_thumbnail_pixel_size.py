"""Regression tests for GHSA-7m55-42q7-888r.

ThumbnailResource.read() takes width/height straight from the thumbnail
image-resource header, with no comparison against the resource's own byte
length. convert_thumbnail_to_pil() then fed those dimensions straight to
Image.frombytes(), which allocates the full output buffer before decoding
any pixel data -- the same allocation-from-unvalidated-header-dimensions
class as GHSA-8q6g-vjhf-jp8m (see test_pixel_size.py), just in a parser path
that guard never covered.
"""

import io
import struct

import pytest

from psd_tools import PSDImage
from psd_tools.api.pil_io import convert_thumbnail_to_pil
from psd_tools.api.utils import MAX_DIMENSION_PSD
from psd_tools.constants import Resource
from psd_tools.psd.image_resources import ThumbnailResource


def _build_psd_with_thumbnail(
    width: int,
    height: int,
    data: bytes = b"",
    resource_id: int = Resource.THUMBNAIL_RESOURCE,
) -> io.BytesIO:
    """Return a minimal structurally valid PSD carrying one thumbnail resource.

    The canvas itself is a trivial 1x1 RGB image; only the thumbnail resource's
    declared width/height are under test.
    """
    payload = struct.pack(">6I2H", 0, width, height, 0, len(data), len(data), 24, 1)
    payload += data
    block = struct.pack(">4sH", b"8BIM", resource_id) + b"\x00\x00"
    block += struct.pack(">I", len(payload)) + payload
    resources = struct.pack(">I", len(block)) + block

    buf = io.BytesIO()
    # File header: signature, version, 6-byte reserved, channels, height,
    # width, depth, color_mode (RGB = 3).
    buf.write(struct.pack(">4sH6xHIIHH", b"8BPS", 1, 3, 1, 1, 8, 3))
    buf.write(struct.pack(">I", 0))  # color mode data length
    buf.write(resources)
    buf.write(struct.pack(">I", 0))  # layer and mask info length
    buf.write(struct.pack(">H", 0))  # image data: compression = raw
    buf.write(b"\x00" * 3)  # 1x1x3 image data
    buf.seek(0)
    return buf


# width/height are a raw uint32 each, independent of the file's own size, so
# a tiny file can declare a value MAX_DIMENSION_PSD must reject.
_OVER_SPEC = MAX_DIMENSION_PSD + 1


def test_thumbnail_raises_when_exceeds_spec() -> None:
    """thumbnail() must raise ValueError when either axis exceeds the spec."""
    psd = PSDImage.open(_build_psd_with_thumbnail(_OVER_SPEC, 1))
    with pytest.raises(ValueError, match="exceeds"):
        psd.thumbnail()


def test_thumbnail_open_does_not_raise_for_out_of_spec_dimensions() -> None:
    """Parsing the file structure must succeed; the guard only fires on convert."""
    psd = PSDImage.open(_build_psd_with_thumbnail(_OVER_SPEC, _OVER_SPEC))
    assert psd.has_thumbnail() is True


def test_thumbnail_opt_in_byte_budget_raises_when_set() -> None:
    """A within-spec but oversized thumbnail is still bounded by max_alloc_bytes."""
    # 25,000 x 25,000 x 4 bytes/px ~= 2.5 GB, within MAX_DIMENSION_PSD.
    psd = PSDImage.open(
        _build_psd_with_thumbnail(25_000, 25_000), max_alloc_bytes=10_000_000
    )
    with pytest.raises(ValueError, match="configured budget"):
        psd.thumbnail()


def test_thumbnail_opt_in_byte_budget_disabled_by_default() -> None:
    """With no max_alloc_bytes set, a normal small thumbnail is unaffected."""
    data = bytes(range(24))  # 4x2 RGB, row = 4*3 = 12
    psd = PSDImage.open(_build_psd_with_thumbnail(4, 2, data=data))
    assert psd._max_alloc_bytes is None
    image = psd.thumbnail()
    assert image is not None and image.size == (4, 2)


def test_convert_thumbnail_to_pil_raises_before_allocating() -> None:
    """The guard runs on the ThumbnailResource fields directly, unit-level."""
    thumb = ThumbnailResource(
        fmt=0, width=_OVER_SPEC, height=1, row=0, total_size=0, bits=24, planes=1
    )
    with pytest.raises(ValueError, match="exceeds"):
        convert_thumbnail_to_pil(thumb)


def test_convert_thumbnail_to_pil_honours_max_alloc_bytes() -> None:
    """A caller-supplied budget is enforced even for a within-spec thumbnail."""
    thumb = ThumbnailResource(
        fmt=0, width=20_000, height=20_000, row=0, total_size=0, bits=24, planes=1
    )
    with pytest.raises(ValueError, match="configured budget"):
        convert_thumbnail_to_pil(thumb, max_alloc_bytes=10_000_000)


def test_convert_thumbnail_to_pil_still_decodes_a_legitimate_thumbnail() -> None:
    """The guard must not reject a correctly sized raw RGBX thumbnail."""
    data = bytes(range(24))  # 4x2 RGB, row = 4*3 = 12
    thumb = ThumbnailResource(
        fmt=0, width=4, height=2, row=12, total_size=24, bits=24, planes=1, data=data
    )
    image = convert_thumbnail_to_pil(thumb)
    assert image.size == (4, 2)
    assert image.mode == "RGBX"
