from __future__ import unicode_literals, print_function
import pytest
import io
from psd_tools2.utils import (
    pack, unpack, read_length_block, write_length_block, read_pascal_string,
    write_pascal_string,
)


@pytest.mark.parametrize('fmt, value, expected', [
    ('B', 1, b'\x01'),
    ('H', 1, b'\x00\x01'),
    ('I', 1, b'\x00\x00\x00\x01'),
])
def test_pack(fmt, value, expected):
    assert pack(fmt, value) == expected


@pytest.mark.parametrize('fmt, value, expected', [
    ('B', b'\x01', 1),
    ('H', b'\x00\x01', 1),
    ('I', b'\x00\x00\x00\x01', 1),
])
def test_unpack(fmt, value, expected):
    assert unpack(fmt, value)[0] == expected


def test_read_length_block():
    data = b'\x00\x00\x00\x07\x01\x01\x01\x01\x01\x01\x01\x00'
    body = data[4:11]
    with io.BytesIO(data) as f:
        assert read_length_block(f, padding=1) == body
        assert f.tell() == 11
    with io.BytesIO(data) as f:
        assert read_length_block(f, padding=2) == body
        assert f.tell() == 12


def test_write_length_block():
    data = b'\x00\x00\x00\x07\x01\x01\x01\x01\x01\x01\x01\x00'
    body = data[4:11]
    with io.BytesIO() as f:
        write_length_block(f, lambda fp: fp.write(body), padding=1)
        assert f.getvalue() == data[:11]
        assert f.tell() == 11
    with io.BytesIO() as f:
        write_length_block(f, lambda fp: fp.write(body), padding=2)
        assert f.getvalue() == data
        assert f.tell() == 12


@pytest.mark.parametrize(['fixture', 'padding'], [
    ('', 1),
    ('a', 1),
    ('ab', 1),
    ('abc', 1),
    ('', 2),
    ('a', 2),
    ('ab', 2),
    ('abc', 2),
    ('', 4),
    ('a', 4),
    ('ab', 4),
    ('abc', 4),
])
def test_pascal_string(fixture, padding):
    with io.BytesIO() as f:
        write_pascal_string(f, fixture, padding=padding)
        data = f.getvalue()

    with io.BytesIO(data) as f:
        output = read_pascal_string(f, padding=padding)
        assert fixture == output


@pytest.mark.parametrize(['input', 'expected', 'padding'], [
    ('', '\x00\x00', 2),
    ('', '\x00\x00\x00\x00', 4),
])
def test_pascal_string_format(input, expected, padding):
    with io.BytesIO() as f:
        write_pascal_string(f, input, padding=padding)
        assert f.getvalue() == expected
