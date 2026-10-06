"""Depth 1, where a row is padded to a byte boundary (#768).

A row of ``width`` pixels occupies ``ceil(width / 8)`` bytes, and the whole
read path has to say so (#768). An RLE codec that floors the row size drops
whatever the last byte holds; ``numpy_io._parse_array()`` unpacking one value
per *bit* with no width to trim against hands the padding back as pixels. A
bitmap document is then readable through ``numpy()`` only where its width is a
multiple of eight, and rendered half from padding even there.

The expectations below are Photoshop's own. ``20x5_1bit_bitmap.psd`` and
``100x20_1bit_bitmap_rle.psd`` were authored by converting a grayscale image to
Bitmap mode (50% threshold) in Photoshop 2026 and saving as PSD, which settles
two things this module then treats as given: the padding bits Photoshop writes
are zero, and an inked -- black -- pixel is a **set** bit. That second one is
why ``pil_io._create_image()`` reads the buffer through the inverted raw mode
``"1;I"``, and why ``_parse_array()`` has to invert the bit rather than return
it as it stands, on pain of rendering every 1-bit document as its own negative.
"""

import io

import numpy as np
import pytest
from PIL import Image

from psd_tools.api.psd_image import PSDImage
from psd_tools.compression import PSDDecompressionWarning, _row_size
from psd_tools.constants import ColorMode, Compression

from .utils import full_name

# One character per pixel, "1" white and "0" black -- the convention the
# compositor's color array uses, so these read directly as the expected values.
_EXPECTED: dict[str, list[str]] = {
    # The shipped fixture, four pixels wide: its row fills half a byte, so
    # keeping the padding doubles the array to `(4, 4, 2)` and splits the
    # document's four rows across two planes.
    "4x4_1bit_bitmap.psd": [
        "0011",
        "0000",
        "1000",
        "1100",
    ],
    # RAW, three bytes per row. Row 2 inks only pixels 16-19 -- the ones that
    # live in the padded byte -- so a stride that drops it loses the row.
    "20x5_1bit_bitmap.psd": [
        "00001111111111111111",
        "01010101010101010101",
        "11111111111111110000",
        "11111111111111111110",
        "10000000000000000000",
    ],
    # RLE, thirteen bytes per row against a floor of twelve. The first four
    # rows ink only pixels 96-99, so under a floored row size they decode to
    # nothing at all -- and the channel comes up short of `topil()`'s stride
    # as well.
    "100x20_1bit_bitmap_rle.psd": (
        ["1" * 96 + "0" * 4] * 4
        + ["0" * 50 + "1" * 50] * 6
        + ["1" * 100] * 5
        + ["0" * 100] * 5
    ),
}

_FIXTURES = sorted(_EXPECTED)


def _expected(filename: str) -> np.ndarray:
    return np.array(
        [[float(c) for c in row] for row in _EXPECTED[filename]], dtype=np.float32
    )


def _open(filename: str) -> PSDImage:
    return PSDImage.open(full_name("colormodes/" + filename))


@pytest.mark.parametrize("filename", _FIXTURES)
def test_numpy_returns_photoshops_pixels(filename: str) -> None:
    """``numpy()`` at the document's own width, with no padding in it.

    Padding left in the array shows up on two of these as ``cannot reshape
    array of size 120 into shape (5,20)``, and on the third as a ``(4, 4, 2)``
    result whose second plane is padding alone.
    """
    array = _open(filename).numpy()
    expected = _expected(filename)
    assert array.shape == expected.shape + (1,)
    assert np.array_equal(array[:, :, 0], expected)


@pytest.mark.parametrize("filename", _FIXTURES)
def test_the_pil_path_agrees_with_the_numpy_one(filename: str) -> None:
    """``topil()`` is the entry point the other paths are measured against.

    PIL's raw decoder reads ``ceil(width / 8)`` bytes per row, so ``topil()``
    has the geometry -- but only once the RLE codec hands it a whole channel,
    short of which the RLE fixture fails here with ``not enough image data``.
    Its polarity is the reference the NumPy path is inverted to match.
    """
    psd = _open(filename)
    image = psd.topil()
    assert isinstance(image, Image.Image)
    assert image.mode == "1"
    assert np.array_equal(np.array(image, dtype=np.float32), _expected(filename))


@pytest.mark.parametrize("filename", _FIXTURES)
def test_the_composite_agrees_with_the_preview(filename: str) -> None:
    """``ignore_preview=True`` renders the layers; the default returns the preview.

    On a layerless bitmap document those are two readings of the same bytes,
    so they have to agree in polarity and in geometry both.
    """
    pytest.importorskip("aggdraw")
    pytest.importorskip("scipy")
    psd = _open(filename)
    composited = psd.composite(ignore_preview=True, apply_icc=False)
    assert isinstance(composited, Image.Image)
    assert np.array_equal(np.array(composited, dtype=np.float32), _expected(filename))
    preview = psd.composite(apply_icc=False)
    assert isinstance(preview, Image.Image)
    assert np.array_equal(np.array(preview), np.array(composited))


def test_padding_bits_are_not_pixels() -> None:
    """Set every padding bit and nothing about the image may change.

    Photoshop writes them as zero, so no fixture proves on its own that they are
    *ignored* rather than merely benign. Forging them to one separates the two:
    a reader that keeps them returns twenty-four values for a twenty-pixel row.
    """
    psd = _open("20x5_1bit_bitmap.psd")
    body = bytearray(psd._record.image_data.data)
    assert len(body) == 5 * 3  # RAW, three bytes a row
    for row in range(5):
        body[row * 3 + 2] |= 0x0F  # the four padding bits of the trailing byte
    psd._record.image_data.data = bytes(body)
    assert np.array_equal(psd.numpy()[:, :, 0], _expected("20x5_1bit_bitmap.psd"))


def test_an_undecodable_1bit_document_degrades_to_black() -> None:
    """The black fill, read back through both entry points rather than as bytes.

    A 1-bit channel that fails to decode gets a fill rather than a
    ``RuntimeError``, and the fill is ``0xff``, not zero -- the half a
    byte-level assertion alone would not catch, since zeroes here would hand
    the caller a blank white document and call it black.
    """
    psd = _open("20x5_1bit_bitmap.psd")
    psd._record.image_data.compression = Compression.ZIP
    psd._record.image_data.data = b"\x78\x9c" + b"\xff" * 20  # garbage deflate
    with pytest.warns(PSDDecompressionWarning, match="channel replaced with black"):
        array = psd.numpy()
    assert array.shape == (5, 20, 1)
    assert not array.any()
    assert not np.array(psd.topil()).any()


@pytest.mark.parametrize("compression", [Compression.RAW, Compression.RLE])
@pytest.mark.parametrize("filename", _FIXTURES)
def test_a_re_encoded_document_survives_the_round_trip(
    filename: str, compression: Compression
) -> None:
    """The write half of the same arithmetic.

    An encoder reading ``width // 8`` bytes per row out of a buffer packed at
    ``ceil(width / 8)`` writes a document sheared by a byte a row.
    Re-compressing each fixture under both codecs and reading it back is what
    exercises that.
    """
    psd = _open(filename)
    expected = psd.numpy()
    header = psd._record.header
    planes = psd._record.image_data.get_data(header)
    assert isinstance(planes, list)
    psd._record.image_data.compression = compression
    psd._record.image_data.set_data(planes, header)

    buf = io.BytesIO()
    psd.save(buf)
    buf.seek(0)
    assert np.array_equal(PSDImage.open(buf).numpy(), expected)


def test_new_builds_a_bitmap_document_at_depth_1() -> None:
    """``PSDImage.new("1", ...)`` writes the depth the mode stores at (#873).

    Photoshop writes every bitmap document at depth 1, and the header is what a
    reader believes: a ``BITMAP`` header at depth 8 describes a document no
    other reader has to accept, however consistently psd-tools reads its own
    back.
    """
    psd = PSDImage.new("1", (20, 3))
    assert psd.color_mode == ColorMode.BITMAP
    assert psd.depth == 1
    assert PSDImage.new("1", (20, 3), depth=1).depth == 1
    # The fill is at the mode's own depth: `color=0` is black, which the stored
    # plane spells as a set bit.
    assert np.unique(psd.numpy()) == [0.0]
    assert np.unique(PSDImage.new("1", (20, 3), color=1.0).numpy()) == [1.0]


def test_a_depth_1_document_round_trips_through_a_file() -> None:
    """The packed section, through the public API and a real file.

    A row of twenty pixels is three bytes rather than twenty, and the fill has
    to survive the inversion the mode reads its bits through: white in, white
    out.
    """
    psd = PSDImage.new("1", (20, 3), color=1.0)
    psd.mark_updated()
    buf = io.BytesIO()
    psd.save(buf)
    buf.seek(0)
    reopened = PSDImage.open(buf)

    assert reopened.depth == 1
    header = reopened._record.header
    stored = reopened._record.image_data.get_data(header, split=False)
    assert isinstance(stored, bytes)
    assert len(stored) == _row_size(20, 1) * 3
    assert np.unique(reopened.numpy()) == [1.0]
    assert np.unique(np.asarray(reopened.topil())) == [True]


def test_a_non_bitmap_document_still_rejects_depth_1() -> None:
    """One bit a channel is the bitmap mode's, not a depth every mode takes."""
    with pytest.raises(ValueError, match="Invalid depth: 1"):
        PSDImage.new("RGB", (4, 4), depth=1)
