from typing import Iterator

import pytest

from psd_tools.psd.header import FileHeader


@pytest.fixture
def fixture() -> Iterator[bytes]:
    yield (
        b"8BPS\x00\x01\x00\x00\x00\x00\x00\x00\x00\x03\x00\x00\x00\x96\x00"
        b"\x00\x00d\x00 \x00\x03"
    )


def test_header_from_to(fixture: bytes) -> None:
    header = FileHeader.frombytes(fixture)
    assert header.tobytes() == fixture


def test_header_exception(fixture: bytes) -> None:
    with pytest.raises(ValueError):
        FileHeader.frombytes(b" " + fixture)
