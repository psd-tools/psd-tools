import io
import os

import pytest
from psd_tools.psd import PSD

from ..utils import TEST_ROOT, all_files, check_write_read

# It seems some fixtures made outside of Photoshop has different paddings.
BAD_PADDINGS = {
    "1layer.psd": 1,
    "2layers.psd": 2,
    "transparentbg-gimp.psd": 2,
}

# Files that do not conform to Adobe's spec (non-standard padding, broken
# structure) are excluded from byte-for-byte round-trip testing.
# Semantic round-trip (write → read → assertEqual) is covered for all
# files by test_psd_write_read via check_write_read.
SKIP_BYTE_ROUND_TRIP = {
    "group-clipping.psd",  # Known broken file
    "broken-groups.psd",  # 2-byte Unicode padding (non-Adobe tool)
    "unicode_pathname.psd",  # 2-byte DescriptorBlock padding
    "unicode_pathname.psb",  # 2-byte DescriptorBlock padding
}


# Verifies byte-for-byte reproduction for spec-conforming files.
# BAD_PADDINGS handles files from non-Adobe tools that use non-standard
# padding but are otherwise valid. Non-conforming files are excluded via
# SKIP_BYTE_ROUND_TRIP and covered semantically by test_psd_write_read.
@pytest.mark.parametrize(
    "filename",
    [f for f in all_files() if os.path.basename(f) not in SKIP_BYTE_ROUND_TRIP],
)
def test_psd_read_write(filename: str) -> None:
    basename = os.path.basename(filename)
    with open(filename, "rb") as f:
        expected = f.read()

    with io.BytesIO(expected) as f:
        psd = PSD.read(f)

    padding = BAD_PADDINGS.get(basename, 4)
    with io.BytesIO() as f:
        psd.write(f, padding=padding)
        f.flush()
        output = f.getvalue()

    assert len(output) == len(expected)
    assert output == expected


@pytest.mark.parametrize("filename", all_files())
def test_psd_write_read(filename: str) -> None:
    with open(filename, "rb") as f:
        psd = PSD.read(f)
    check_write_read(psd)
    check_write_read(psd, encoding="utf_8")


def test_psd_from_error() -> None:
    with pytest.raises(IOError):
        PSD.frombytes(b"\x00\x00\x00\x00")


@pytest.mark.parametrize(
    ["filename", "length"],
    [
        ("colormodes/4x4_8bit_rgb.psd", 2),
        ("colormodes/4x4_16bit_rgb.psd", 2),
        ("colormodes/4x4_32bit_rgb.psd", 2),
    ],
)
def test_psd__iter_layers(filename: str, length: int) -> None:
    with open(os.path.join(TEST_ROOT, "psd_files", filename), "rb") as f:
        psd = PSD.read(f)
    assert len(list(psd._iter_layers())) == length
