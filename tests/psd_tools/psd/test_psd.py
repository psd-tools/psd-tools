from __future__ import absolute_import, unicode_literals
import pytest
import io
import os
from psd_tools.psd import PSD

from ..utils import all_files, check_write_read, TEST_ROOT

# It seems some fixtures made outside of Photoshop has different paddings.
BAD_PADDINGS = {
    '1layer.psd': 1,
    '2layers.psd': 2,
    'broken-groups.psd': 2,
    'transparentbg-gimp.psd': 2,
}

BAD_UNICODE_PADDINGS = {
    'broken-groups.psd': 2,  # Unicode aligns 2 byte.
    'unicode_pathname.psd': 2,  # DescriptorBlock aligns 2 byte.
    'unicode_pathname.psb': 2,  # DescriptorBlock aligns 2 byte.
}


@pytest.mark.parametrize('filename', all_files())
def test_psd_read_write(filename):
    basename = os.path.basename(filename)
    with open(filename, 'rb') as f:
        expected = f.read()

    with io.BytesIO(expected) as f:
        psd = PSD.read(f)

    padding = BAD_PADDINGS.get(basename, 4)
    with io.BytesIO() as f:
        psd.write(f, padding=padding)
        f.flush()
        output = f.getvalue()

    if basename in BAD_UNICODE_PADDINGS:
        pytest.xfail('Broken file')
    assert len(output) == len(expected)
    assert output == expected


@pytest.mark.parametrize('filename', all_files())
def test_psd_write_read(filename):
    with open(filename, 'rb') as f:
        psd = PSD.read(f)
    check_write_read(psd)
    check_write_read(psd, encoding='utf_8')


def test_psd_from_error():
    with pytest.raises(AssertionError):
        PSD.frombytes(b'\x00\x00\x00\x00')


@pytest.mark.parametrize(['filename', 'length'], [
    ('colormodes/4x4_8bit_rgb.psd', 2),
    ('colormodes/4x4_16bit_rgb.psd', 2),
    ('colormodes/4x4_32bit_rgb.psd', 2),
])
def test_psd__iter_layers(filename, length):
    with open(os.path.join(TEST_ROOT, 'psd_files', filename), 'rb') as f:
        psd = PSD.read(f)
    assert len(list(psd._iter_layers())) == length
