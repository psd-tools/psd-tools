from __future__ import absolute_import, unicode_literals
import pytest
from psd_tools.psd.header import FileHeader


@pytest.fixture
def fixture():
    return (
        b'8BPS\x00\x01\x00\x00\x00\x00\x00\x00\x00\x03\x00\x00\x00\x96\x00'
        b'\x00\x00d\x00 \x00\x03'
    )


def test_header_from_to(fixture):
    header = FileHeader.frombytes(fixture)
    assert header.tobytes() == fixture


def test_header_exception(fixture):
    with pytest.raises(ValueError):
        FileHeader.frombytes(b' ' + fixture)
