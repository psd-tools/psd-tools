from __future__ import absolute_import, unicode_literals
import os
import pytest
from IPython.display import display

from psd_tools.psd.descriptor import (
    TYPES, Descriptor, Reference, Double, String, Bool, LargeInteger, Integer,
    UnitFloat
)
from psd_tools.terminology import Unit

from ..utils import check_write_read, check_read_write, TEST_ROOT

DESCRIPTOR_DATA = ['0.dat', '1.dat']


@pytest.mark.parametrize('cls', [TYPES[key] for key in TYPES])
def test_empty_wr(cls):
    check_write_read(cls())


@pytest.mark.parametrize('filename', DESCRIPTOR_DATA)
def test_descriptor_rw(filename):
    filepath = os.path.join(TEST_ROOT, 'descriptors', filename)
    with open(filepath, 'rb') as f:
        check_read_write(Descriptor, f.read())


@pytest.mark.parametrize('filename', DESCRIPTOR_DATA)
def test_descriptor_display(filename):
    filepath = os.path.join(TEST_ROOT, 'descriptors', filename)
    with open(filepath, 'rb') as f:
        value = Descriptor.frombytes(f.read())
    display(value)


@pytest.mark.parametrize(
    'fixture', [(
        b'\x00\x00\x00\x01name\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00name\x00'
        b'\x00\x00\x030j0W\x00\x00'
    )]
)
def test_reference_rw(fixture):
    check_read_write(Reference, fixture)


@pytest.mark.parametrize(
    'kls, value', [
        (Double, 1.),
        (String, ''),
        (Bool, True),
        (LargeInteger, 1),
        (Integer, 1),
    ]
)
def test_value_elements(kls, value):
    fixture = kls(value)
    assert fixture == value


@pytest.mark.parametrize(
    'unit, value', [
        (Unit.Pixels, 100.0),
        (Unit.Points, 0.0),
    ]
)
def test_unit_float(unit, value):
    fixture = UnitFloat(unit=unit, value=value)
    assert fixture == value
    assert fixture + 1.0
    assert isinstance(float(fixture), float)
