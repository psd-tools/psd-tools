from __future__ import absolute_import, unicode_literals
import pytest
import logging

from psd_tools.psd.patterns import VirtualMemoryArray

from ..utils import check_write_read, check_read_write

logger = logging.getLogger(__name__)

VIRTUAL_MEMORY_ARRAY = (
    b'\x00\x00\x00\x01\x00\x00\x00W\x00\x00\x00\x08\x00\x00\x00\x00\x00\x00'
    b'\x00\x00\x00\x00\x00\x08\x00\x00\x00\x08\x00\x08\x00\xdc\xff\xff\xff'
    b'\xff\xff\xdf8\xff\xff\xff\xff\xff\xdf:\xd8\xff\xff\xff\xff\xe0;\xd9'
    b'\xff\xff\xff\xff\xe1=\xda\xff\xff\xff\xff\xe2?\xdc\xff\xff\xff\xff'
    b'\xe2@\xdd\xff\xff\xff\xff\xe3B\xde\xff\xff\xff\xff\xffD\xdf\xff\xff'
    b'\xff\xff\xff\xe0'
)


@pytest.mark.parametrize(
    'args', [
        (0, None, None, None, 0, b''),
        (1, 8, (0, 0, 8, 8), 8, 0, b'\x00' * 64),
    ]
)
def test_virtual_memory_array_wr(args):
    check_write_read(VirtualMemoryArray(*args))


@pytest.mark.parametrize('fixture', [VIRTUAL_MEMORY_ARRAY])
def test_virtual_memory_array_rw(fixture):
    check_read_write(VirtualMemoryArray, fixture)


@pytest.mark.parametrize('fixture', [VIRTUAL_MEMORY_ARRAY])
def test_virtual_memory_array_data(fixture):
    value = VirtualMemoryArray.frombytes(fixture)
    data = value.get_data()
    width, height = value.rectangle[3], value.rectangle[2]
    value.set_data((width, height), data, value.pixel_depth, value.compression)
    assert value.tobytes() == fixture
