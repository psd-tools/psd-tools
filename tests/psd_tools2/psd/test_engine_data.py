from __future__ import absolute_import, unicode_literals
import os
import pytest
from psd_tools2.psd.engine_data import Tokenizer, EngineToken, EngineData

from ..utils import check_write_read, check_read_write, TEST_ROOT


@pytest.mark.parametrize('fixture, length', [
    (b'(\xfe\xff0\x00) /1 (\xfe\xff\x001)', 3),
    (b'(\xfe\xff0\x00\\) /1 \\(\xfe\xff\x001)', 1),
    (b'(\xfe\xff) <<', 2),
])
def test_tokenizer(fixture, length):
    tokenizer = Tokenizer(fixture)
    tokens = list(tokenizer)
    assert len(tokens) == length


@pytest.mark.parametrize('fixture, token_type', [
    (b'(\xfe\xff0\n0\n)', EngineToken.STRING),
])
def test_tokenizer_item(fixture, token_type):
    tokenizer = Tokenizer(fixture)
    token, o_token_type = next(tokenizer)
    assert o_token_type == token_type


@pytest.mark.parametrize('filename, indent, write', [
    ('TySh_1.dat', 0, True),
    ('Txt2_1.dat', None, False),
])
def test_engine_data(filename, indent, write):
    filepath = os.path.join(TEST_ROOT, 'engine_data', filename)
    with open(filepath, 'rb') as f:
        fixture = f.read()

    engine_data = EngineData.frombytes(fixture)
    output = engine_data.tobytes(indent=indent, write_container=write)
    assert output == fixture
