from __future__ import absolute_import, unicode_literals
import pytest
from psd_tools2.decoder.descriptor import TYPES
from ..utils import check_write_read


@pytest.mark.parametrize('cls', [
    TYPES[key] for key in TYPES
])
def test_descriptor_wr(cls):
    print(cls())
    check_write_read(cls())
