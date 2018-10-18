from __future__ import absolute_import, unicode_literals
import pytest
from psd_tools2.decoder import PSD

from ..utils import full_name, all_files

try:
    from IPython.lib.pretty import pprint
except ImportError:
    from pprint import pprint


@pytest.mark.parametrize(["filename"], all_files())
def test_psd_read(filename):
    with open(filename, 'rb') as f:
        psd = PSD.read(f)
        pprint(psd)


def test_psd_from_error():
    with pytest.raises(AssertionError):
        PSD.frombytes(b'\x00\x00\x00\x00')
