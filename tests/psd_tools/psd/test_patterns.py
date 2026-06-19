from typing import Any, Tuple
import logging

import pytest

from psd_tools.psd.patterns import VirtualMemoryArray

from ..utils import check_read_write, check_write_read

logger = logging.getLogger(__name__)

VIRTUAL_MEMORY_ARRAY = (
    b"\x00\x00\x00\x01\x00\x00\x00W\x00\x00\x00\x08\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x08\x00\x00\x00\x08\x00\x08\x00\xdc\xff\xff\xff"
    b"\xff\xff\xdf8\xff\xff\xff\xff\xff\xdf:\xd8\xff\xff\xff\xff\xe0;\xd9"
    b"\xff\xff\xff\xff\xe1=\xda\xff\xff\xff\xff\xe2?\xdc\xff\xff\xff\xff"
    b"\xe2@\xdd\xff\xff\xff\xff\xe3B\xde\xff\xff\xff\xff\xffD\xdf\xff\xff"
    b"\xff\xff\xff\xe0"
)


@pytest.mark.parametrize(
    "args",
    [
        (0, None, None, None, 0, b""),
        (1, 8, (0, 0, 8, 8), 8, 0, b"\x00" * 64),
    ],
)
def test_virtual_memory_array_wr(args: Tuple[Any, ...]) -> None:
    check_write_read(VirtualMemoryArray(*args))


@pytest.mark.parametrize("fixture", [VIRTUAL_MEMORY_ARRAY])
def test_virtual_memory_array_rw(fixture: bytes) -> None:
    check_read_write(VirtualMemoryArray, fixture)


@pytest.mark.parametrize("fixture", [VIRTUAL_MEMORY_ARRAY])
def test_virtual_memory_array_data(fixture: bytes) -> None:
    value = VirtualMemoryArray.frombytes(fixture)
    data = value.get_data()
    assert value.rectangle is not None
    assert data is not None
    assert value.pixel_depth is not None
    top, left, bottom, right = value.rectangle
    width = right - left
    height = bottom - top
    value.set_data((width, height), data, value.pixel_depth, value.compression)
    assert value.tobytes() == fixture


def test_virtual_memory_array_get_data_non_zero_origin() -> None:
    """get_data() must use relative dimensions (right-left, bottom-top), not absolute coords."""
    # rectangle (top=10, left=20, bottom=18, right=28) => width=8, height=8
    vma = VirtualMemoryArray(
        is_written=1,
        depth=8,
        rectangle=(10, 20, 18, 28),
        pixel_depth=8,
        compression=0,
        data=b"\x00" * 64,
    )
    data = vma.get_data()
    assert data is not None
    assert len(data) == 8 * 8  # 64 bytes, not 28*18=504
