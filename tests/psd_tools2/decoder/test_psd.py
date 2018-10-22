from __future__ import absolute_import, unicode_literals
import pytest
import logging
import io
import os
from psd_tools2.decoder import PSD

from ..utils import full_name, all_files, check_write_read, check_read_write

try:
    from IPython.lib.pretty import pprint
except ImportError:
    from pprint import pprint


logging.basicConfig(level=logging.DEBUG)

# It seems some fixtures made outside of Photoshop has different paddings.
BAD_PADDINGS = {
    '1layer.psd': 1,
    '2layers.psd': 2,
    'broken-groups.psd': 2,
    'transparentbg-gimp.psd': 2,
}

UTF8_FILES = {
    'layer_params.psb',
    'layer_params.psd',
    'layer_comps.psb',
    'layer_comps.psd',
    'layer_mask_data.psb',
    'layer_mask_data.psd',
    'advanced-blending.psd',
    'effect-stroke-gradient.psd',
    'layer_effects.psd',
    'patterns.psd',
    'fill_adjustments.psd',
    'blend-and-clipping.psd',
    'clipping-mask2.psd',
}

@pytest.mark.parametrize(['filename'], all_files())
def test_psd_read_write(filename):
    with open(filename, 'rb') as f:
        expected = f.read()

    encoding = 'utf_8' if os.path.basename(filename) in UTF8_FILES else 'macroman'
    with io.BytesIO(expected) as f:
        psd = PSD.read(f, encoding=encoding)
        pprint(psd)

    padding = BAD_PADDINGS.get(os.path.basename(filename), 4)
    with io.BytesIO() as f:
        psd.write(f, encoding=encoding, padding=padding)
        f.flush()
        output = f.getvalue()

    assert len(output) == len(expected)
    assert output == expected


@pytest.mark.parametrize(["filename"], all_files())
def test_psd_write_read(filename):
    with open(filename, 'rb') as f:
        psd = PSD.read(f)
    check_write_read(psd)
    check_write_read(psd, encoding='utf_8')


def test_psd_from_error():
    with pytest.raises(AssertionError):
        PSD.frombytes(b'\x00\x00\x00\x00')
