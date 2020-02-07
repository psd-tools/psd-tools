from __future__ import absolute_import, unicode_literals
import pytest
import logging

from enum import Enum
from psd_tools.psd.base import (
    BooleanElement, ByteElement, DictElement, EmptyElement, IntegerElement,
    ListElement, NumericElement, ShortIntegerElement, StringElement
)

from ..utils import check_write_read

logger = logging.getLogger(__name__)


def test_empty():
    check_write_read(EmptyElement())


@pytest.mark.parametrize('fixture', [
    '',
    'a',
    'ab',
    '\u0034\u0035\u0036',
])
def test_string(fixture):
    value = StringElement(fixture)
    check_write_read(value)
    assert value == fixture
    assert repr(value) == repr(fixture)
    assert hash(value) == hash(fixture)
    assert (value % tuple()) == fixture


@pytest.mark.parametrize(
    'kls, fixture', [
        (ByteElement, 1),
        (ShortIntegerElement, 1),
        (IntegerElement, 1),
        (NumericElement, 1.),
    ]
)
def test_numbers(kls, fixture):
    value = kls(fixture)
    check_write_read(value)
    assert value == fixture
    assert (value + fixture) == (fixture * 2)
    assert repr(value) == repr(fixture)
    assert hash(value) == hash(fixture)


@pytest.mark.parametrize(
    'kls, fixture', [
        (ByteElement, b'\x01\x00'),
        (ShortIntegerElement, b'\x00\x01'),
        (BooleanElement, b'\x00\x01'),
    ]
)
def test_malformed_numbers(kls, fixture):
    kls.frombytes(fixture)


def test_boolean():
    value = BooleanElement(True)
    assert value.value is True
    assert value
    value = BooleanElement(False)
    assert value.value is False
    assert not value


def test_list():
    value = ListElement(range(10))
    value.append(10)
    value.extend([11])
    value.insert(0, -1)
    value.remove(-1)
    value.pop()
    assert len(value) == 11
    assert value.index(0) == 0
    value.sort()
    value.reverse()
    repr(value)


class Dummy(bytes, Enum):
    A = b'x'
    B = b'y'
    C = b'x'


def test_dict():
    value = DictElement()
    value[Dummy.A] = 'foo'
    assert value.get(Dummy.A) == value.get(b'x')
    assert list(value.keys())[0] == Dummy.A
    assert list(value.keys())[0] == b'x'
    assert Dummy.A in value
    assert b'x' in value
    assert value[Dummy.A] == 'foo'
    assert value[Dummy(b'x')] == 'foo'
    assert value[b'x'] == 'foo'
    repr(value)
    del value[Dummy.A]
