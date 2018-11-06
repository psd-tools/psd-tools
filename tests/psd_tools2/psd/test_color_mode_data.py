from __future__ import absolute_import, unicode_literals
import pytest
from psd_tools2.psd.color_mode_data import ColorModeData

from ..utils import check_read_write, check_write_read


def test_color_mode_data_from_to():
    check_read_write(ColorModeData, b'\x00\x00\x00\x00')
    check_write_read(ColorModeData(data=b'\x01'))


def test_color_mode_data_exception():
    with pytest.raises(AssertionError):
        ColorModeData.frombytes(b'')
    with pytest.raises(AssertionError):
        ColorModeData.frombytes(str(10).encode('ascii'))
