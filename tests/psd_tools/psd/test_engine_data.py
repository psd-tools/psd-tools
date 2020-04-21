from __future__ import absolute_import, unicode_literals
import os
import pytest
from psd_tools.psd.engine_data import (
    Tokenizer, EngineToken, EngineData, Float, String
)

from ..utils import check_read_write, TEST_ROOT


@pytest.mark.parametrize(
    'fixture, length', [
        (b'(\xfe\xff0\x00) /1 (\xfe\xff\x001)', 3),
        (b'(\xfe\xff0\x00\\) /1 \\(\xfe\xff\x001)', 1),
        (b'(\xfe\xff) <<', 2),
    ]
)
def test_tokenizer(fixture, length):
    tokenizer = Tokenizer(fixture)
    tokens = list(tokenizer)
    assert len(tokens) == length


@pytest.mark.parametrize(
    'fixture, token_type', [
        (b'(\xfe\xff0\n0\n)', EngineToken.STRING),
    ]
)
def test_tokenizer_item(fixture, token_type):
    tokenizer = Tokenizer(fixture)
    token, o_token_type = next(tokenizer)
    assert o_token_type == token_type


@pytest.mark.parametrize(
    'filename, indent, write', [
        ('TySh_1.dat', 0, True),
        ('Txt2_1.dat', None, False),
        ('Txt2_2.dat', None, False),
        ('Txt2_3.dat', None, False),
        ('Txt2_4.dat', None, False),
    ]
)
def test_engine_data(filename, indent, write):
    filepath = os.path.join(TEST_ROOT, 'engine_data', filename)
    with open(filepath, 'rb') as f:
        fixture = f.read()

    engine_data = EngineData.frombytes(fixture)
    output = engine_data.tobytes(indent=indent, write_container=write)
    assert output == fixture


@pytest.mark.parametrize('filename', ['TySh_2.dat',])
def test_engine_data_parse(filename):
    filepath = os.path.join(TEST_ROOT, 'engine_data', filename)
    with open(filepath, 'rb') as f:
        assert isinstance(EngineData.read(f), EngineData)


@pytest.mark.parametrize(
    'fixture', [
        b'0.0',
        b'.4',
        b'-.4',
        b'1.0',
        b'.00006',
        b'-47.55428',
    ]
)
def test_float(fixture):
    check_read_write(Float, fixture)


@pytest.mark.parametrize(
    'fixture', [
        b'(\xfe\xff0\x00)',
        b'(\xfe\xff0\x00\\) /1 \\(\xfe\xff\x001)',
        b'(\xfe\xff)',
        b'(\xfe\xffb\x10\\\\1\x00\r)',
    ]
)
def test_string(fixture):
    check_read_write(String, fixture)
