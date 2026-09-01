"""Depth 1, where a row is padded to a byte boundary (#768).

A row of ``width`` pixels occupies ``ceil(width / 8)`` bytes, and until #768
nothing on the read path said so. The RLE codec floored the row size, dropping
whatever the last byte held; ``numpy_io._parse_array()`` unpacked one value per
*bit* with no width to trim against, so the padding came back as pixels. A
bitmap document was therefore readable through ``numpy()`` only if its width was
a multiple of eight, and rendered half from padding even then.

The expectations below are Photoshop's own. ``20x5_1bit_bitmap.psd`` and
``100x20_1bit_bitmap_rle.psd`` were authored by converting a grayscale image to
Bitmap mode (50% threshold) in Photoshop 2026 and saving as PSD, which settles
two things this module then treats as given: the padding bits Photoshop writes
are zero, and an inked -- black -- pixel is a **set** bit. That second one is
why ``pil_io._create_image()`` reads the buffer through the inverted raw mode
``"1;I"``, and why ``_parse_array()``, which returned the bit as it stood,
rendered every 1-bit document as its own negative.
"""

import io

import numpy as np
import pytest
from PIL import Image

from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import Compression

from .utils import full_name

# One character per pixel, "1" white and "0" black -- the convention the
# compositor's color array uses, so these read directly as the expected values.
_EXPECTED: dict[str, list[str]] = {
    # The shipped fixture, four pixels wide: its row fills half a byte, so the
    # padding used to double the array to `(4, 4, 2)` and split the document's
    # four rows across two planes.
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
    # RLE, thirteen bytes per row against a floor of twelve. The first four rows
    # ink only pixels 96-99, so under the old row size they decoded to nothing
    # at all -- and the channel came up short of `topil()`'s stride as well.
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

    Two of these could not be read at all before -- ``cannot reshape array of
    size 120 into shape (5,20)`` -- and the third came back ``(4, 4, 2)``, its
    second plane pure padding.
    """
    array = _open(filename).numpy()
    expected = _expected(filename)
    assert array.shape == expected.shape + (1,)
    assert np.array_equal(array[:, :, 0], expected)


@pytest.mark.parametrize("filename", _FIXTURES)
def test_the_pil_path_agrees_with_the_numpy_one(filename: str) -> None:
    """``topil()`` was the only entry point that was right, and it still is.

    PIL's raw decoder has always read ``ceil(width / 8)`` bytes per row, so
    ``topil()`` recovered the geometry the other paths lost -- but only after
    the RLE codec hands it a whole channel, which is why the RLE fixture used
    to fail here with ``not enough image data``. Its polarity was right too,
    and it is the reference the NumPy path is now inverted to match.
    """
    psd = _open(filename)
    image = psd.topil()
    assert isinstance(image, Image.Image)
    assert image.mode == "1"
    assert np.array_equal(np.array(image, dtype=np.float32), _expected(filename))


@pytest.mark.parametrize("filename", _FIXTURES)
def test_the_composite_agrees_with_the_preview(filename: str) -> None:
    """``ignore_preview=True`` renders the layers; the default returns the preview.

    On a layerless bitmap document those are two readings of the same bytes, so
    they have to agree -- and they did not: the composited one was the negative
    of the preview, scrambled or unformable besides.
    """
    pytest.importorskip("aggdraw")
    pytest.importorskip("scipy")
    pytest.importorskip("skimage")
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


@pytest.mark.parametrize("compression", [Compression.RAW, Compression.RLE])
@pytest.mark.parametrize("filename", _FIXTURES)
def test_a_re_encoded_document_survives_the_round_trip(
    filename: str, compression: Compression
) -> None:
    """The write half of the same arithmetic.

    ``encode_rle()`` kept its own copy of the floored row size, so it read
    ``width // 8`` bytes per row out of a buffer packed at ``ceil(width / 8)``
    and wrote a document sheared by a byte a row. Re-compressing each fixture
    under both codecs and reading it back is what exercises that.
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
