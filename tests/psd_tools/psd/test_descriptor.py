from typing import Any, Type
import os

import pytest

from psd_tools.psd.descriptor import (
    TYPES,
    Bool,
    Descriptor,
    Double,
    Integer,
    LargeInteger,
    Reference,
    String,
    UnitFloat,
    UnitFloats,
)
from psd_tools.terminology import Enum, Unit

from ..utils import TEST_ROOT, check_read_write, check_write_read

DESCRIPTOR_DATA = ["0.dat", "1.dat"]


@pytest.mark.parametrize("cls", [TYPES[key] for key in TYPES])
def test_empty_wr(cls: Type[Any]) -> None:
    check_write_read(cls())


@pytest.mark.parametrize("filename", DESCRIPTOR_DATA)
def test_descriptor_rw(filename: str) -> None:
    filepath = os.path.join(TEST_ROOT, "descriptors", filename)
    with open(filepath, "rb") as f:
        check_read_write(Descriptor, f.read())


@pytest.mark.parametrize("filename", DESCRIPTOR_DATA)
def test_descriptor_display(filename: str) -> None:
    filepath = os.path.join(TEST_ROOT, "descriptors", filename)
    with open(filepath, "rb") as f:
        Descriptor.frombytes(f.read())


@pytest.mark.parametrize(
    "fixture",
    [
        (
            b"\x00\x00\x00\x01name\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00name\x00"
            b"\x00\x00\x030j0W\x00\x00"
        )
    ],
)
def test_reference_rw(fixture: bytes) -> None:
    check_read_write(Reference, fixture)


@pytest.mark.parametrize(
    "kls, value",
    [
        (Double, 1.0),
        (String, ""),
        (Bool, True),
        (LargeInteger, 1),
        (Integer, 1),
    ],
)
def test_value_elements(kls: Type[Any], value: Any) -> None:
    fixture = kls(value)
    assert fixture == value


@pytest.mark.parametrize(
    "unit, value",
    [
        (Unit.Pixels, 100.0),
        (Unit.Points, 0.0),
    ],
)
def test_unit_float(unit: Unit, value: float) -> None:
    fixture = UnitFloat(unit=unit, value=value)
    assert fixture == value
    assert fixture + 1.0
    assert isinstance(float(fixture), float)


def test_unit_float_converts_value() -> None:
    fixture = UnitFloat(unit=Unit.Pixels, value="1.5")  # type: ignore[arg-type]
    assert isinstance(fixture.value, float)
    assert fixture == 1.5
    assert UnitFloat(unit=Unit.Pixels, value=100).value == 100.0  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [None, object(), [1.0], b"oops"])
def test_unit_float_rejects_a_non_number(value: Any) -> None:
    """``None`` and any other object used to be accepted silently."""
    with pytest.raises((TypeError, ValueError)):
        UnitFloat(unit=Unit.Pixels, value=value)


@pytest.mark.parametrize(
    "fixture",
    [
        b"RrCm\x00\x00\x00\x00\x00\x00\x00\x00",
        b"#Pxl\x00\x00\x00\x00\x00\x00\x00\x00",
    ],
)
def test_unit_float_enum(fixture: bytes) -> None:
    UnitFloat.frombytes(fixture)


@pytest.mark.parametrize("cls", [UnitFloat, UnitFloats])
def test_unit_converts_a_raw_code(cls: Type[Any]) -> None:
    """A valid 4-byte code is normalised, so ``write()`` can reach ``.value``."""
    fixture = cls(unit=b"#Prc")
    assert fixture.unit is Unit.Percent
    # UnitFloat compares on `value` alone, so round-trip `unit` explicitly.
    assert cls.frombytes(fixture.tobytes()).unit is Unit.Percent


@pytest.mark.parametrize("cls", [UnitFloat, UnitFloats])
def test_unit_keeps_the_enum_fallback(cls: Type[Any]) -> None:
    """A ruler unit is not a ``Unit``; ``Enum`` carries it, on both paths."""
    assert cls(unit=b"RrCm").unit is Enum.RulerCm
    assert cls(unit=Enum.RulerCm).unit is Enum.RulerCm


@pytest.mark.parametrize("cls", [UnitFloat, UnitFloats])
@pytest.mark.parametrize("unit", [b"ZZZZ", b"#Prc\x00", None, 0, "#Prc"])
def test_unit_rejects_a_bad_code_at_construction(cls: Type[Any], unit: Any) -> None:
    """``write()`` used to be the first thing to complain, with ``AttributeError``."""
    with pytest.raises(ValueError, match="is not a valid Unit or Enum"):
        cls(unit=unit)
