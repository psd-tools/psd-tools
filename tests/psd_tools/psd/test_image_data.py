from typing import Any, List

import pytest

from psd_tools.constants import Compression
from psd_tools.psd.header import FileHeader
from psd_tools.psd.image_data import ImageData

from ..utils import check_write_read

RAW_IMAGE_3x3_8bit = b"\x00\x01\x02\x01\x01\x01\x01\x00\x00"
RAW_IMAGE_2x2_16bit = b"\x00\x01\x00\x02\x00\x03\x00\x04"


def test_image_data() -> None:
    check_write_read(ImageData())
    check_write_read(ImageData(data=b"\x00"))


_CHANNEL_CASES = [
    (
        Compression.RAW,
        [RAW_IMAGE_3x3_8bit] * 3,
        FileHeader(width=3, height=3, depth=8, channels=3, version=1),
    ),
    (
        Compression.RLE,
        [RAW_IMAGE_3x3_8bit] * 3,
        FileHeader(width=3, height=3, depth=8, channels=3, version=1),
    ),
    (
        Compression.ZIP,
        [RAW_IMAGE_3x3_8bit] * 3,
        FileHeader(width=3, height=3, depth=8, channels=3, version=1),
    ),
    (
        Compression.RAW,
        [RAW_IMAGE_3x3_8bit] * 3,
        FileHeader(width=3, height=3, depth=8, channels=3, version=2),
    ),
    (
        Compression.RLE,
        [RAW_IMAGE_3x3_8bit] * 3,
        FileHeader(width=3, height=3, depth=8, channels=3, version=2),
    ),
    (
        Compression.ZIP,
        [RAW_IMAGE_3x3_8bit] * 3,
        FileHeader(width=3, height=3, depth=8, channels=3, version=2),
    ),
    (
        Compression.RAW,
        [RAW_IMAGE_2x2_16bit] * 3,
        FileHeader(width=2, height=2, depth=16, channels=3, version=1),
    ),
    (
        Compression.RLE,
        [RAW_IMAGE_2x2_16bit] * 3,
        FileHeader(width=2, height=2, depth=16, channels=3, version=1),
    ),
    (
        Compression.ZIP,
        [RAW_IMAGE_2x2_16bit] * 3,
        FileHeader(width=2, height=2, depth=16, channels=3, version=1),
    ),
]


@pytest.mark.parametrize("compression, data, header", _CHANNEL_CASES)
def test_image_data_data(compression: int, data: List[bytes], header: Any) -> None:
    image_data = ImageData(compression)
    image_data.set_data(data, header)
    output = image_data.get_data(header)
    assert output == data, "output=%r, expected=%r" % (output, data)


@pytest.mark.parametrize("compression, data, header", _CHANNEL_CASES)
def test_image_data_decompressed_size_bound(
    compression: int, data: List[bytes], header: Any
) -> None:
    """The bound must cover what :py:meth:`ImageData.get_data` really produces.

    Every channel at once, which is the part of the mapping the bound exists to
    keep in one place: ``get_data`` passes ``height * channels`` rows to the
    codec, so a bound derived from ``height`` alone would be short by a factor
    of the channel count. Read together with
    :py:func:`psd_tools.compression.decompressed_size_bound`, whose own tests
    pin the per-codec arithmetic.
    """
    image_data = ImageData(compression)
    image_data.set_data(data, header)
    produced = image_data.get_data(header, split=False)
    assert isinstance(produced, bytes)
    assert len(produced) <= image_data.decompressed_size_bound(header)
