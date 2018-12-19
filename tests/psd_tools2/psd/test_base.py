from __future__ import absolute_import, unicode_literals
import pytest
import logging

from enum import Enum
from psd_tools2.psd.base import (
    BooleanElement, ByteElement, DictElement, EmptyElement, IntegerElement,
    ListElement, NumericElement, ShortIntegerElement, StringElement,
    ValueElement
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


@pytest.mark.parametrize('kls, fixture', [
    (ByteElement, 1),
    (ShortIntegerElement, 1),
    (IntegerElement, 1),
    (NumericElement, 1.),
])
def test_numbers(kls, fixture):
    value = kls(fixture)
    check_write_read(value)
    assert value == fixture
    assert (value + fixture) == (fixture * 2)
    assert repr(value) == repr(fixture)
    assert hash(value) == hash(fixture)


def test_boolean():
    value = BooleanElement(True)
    assert value == True
    assert value
    value = BooleanElement(False)
    assert value == False
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


class Dummy(Enum):
    A = b'x'
    B = b'y'
    C = b'x'


class EnumDict(DictElement):
    enum = Dummy


def test_dict():
    value = EnumDict()
    value['A'] = 'foo'
    assert value.get('A') == value.get(Dummy.A)
    assert list(value.keys())[0] == Dummy.A
    assert 'A' in value
    assert value['A'] == 'foo'
    assert value[b'A'] == 'foo'
    assert value['x'] == 'foo'
    assert value[b'x'] == 'foo'
    repr(value)
    del value['A']
