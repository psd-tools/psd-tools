import json

import pytest

from psd_tools.api._descriptor import get_enum, get_scalar
from psd_tools.psd.descriptor import (
    Bool,
    Descriptor,
    Double,
    Enumerated,
    Integer,
    List,
    String,
    UnitFloat,
)
from psd_tools.terminology import Enum, Klass, Unit


@pytest.fixture
def descriptor() -> Descriptor:
    return Descriptor(
        classID=Klass.Null,
        items={  # type: ignore[arg-type]
            b"long": Integer(40),
            b"doub": Double(2.5),
            b"unit": UnitFloat(value=3.0, unit=Unit.Pixels),
            b"bool": Bool(True),
            b"text": String("hello"),
            b"mode": Enumerated(b"BlnM", b"Mltp"),
            b"nope": Enumerated(b"BlnM", b"zzzz"),
        },
    )


@pytest.mark.parametrize(
    "key, type_, default, expected",
    [
        (b"long", int, 0, 40),
        (b"long", float, 0.0, 40.0),
        (b"doub", float, 0.0, 2.5),
        (b"doub", int, 0, 2),
        (b"unit", float, 0.0, 3.0),
        (b"bool", bool, False, True),
        (b"long", bool, False, True),
        (b"text", str, "", "hello"),
    ],
)
def test_get_scalar_coerces(descriptor, key, type_, default, expected):
    result = get_scalar(descriptor, key, type_, default)
    assert type(result) is type_
    assert result == expected


@pytest.mark.parametrize(
    "key, type_, default",
    [
        (b"miss", int, 7),
        (b"text", int, 7),
        (b"mode", float, 7.0),
        (b"long", str, "d"),
    ],
)
def test_get_scalar_degrades_to_default(descriptor, key, type_, default):
    assert get_scalar(descriptor, key, type_, default) == default


def test_get_scalar_default_is_coerced_to_type():
    data = Descriptor(classID=Klass.Null, items={b"text": String("x")})  # type: ignore[arg-type]
    for key in (b"miss", b"text"):
        assert type(get_scalar(data, key, float, 0)) is float  # type: ignore[arg-type]


def test_get_scalar_none_default_means_absent():
    data = Descriptor(classID=Klass.Null, items={b"text": String("x")})  # type: ignore[arg-type]
    assert get_scalar(data, b"miss", float, None) is None
    assert get_scalar(data, b"text", float, None) is None
    assert get_scalar(None, b"miss", float, None) is None


def test_get_scalar_none_default_still_coerces_present_value():
    data = Descriptor(classID=Klass.Null, items={b"long": Integer(7)})  # type: ignore[arg-type]
    value = get_scalar(data, b"long", float, None)
    assert value == 7.0 and type(value) is float


def test_get_scalar_none_descriptor():
    assert get_scalar(None, b"long", int, 3) == 3


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_get_scalar_non_finite_int_degrades(value):
    data = Descriptor(classID=Klass.Null, items={b"doub": Double(value)})  # type: ignore[arg-type]
    assert get_scalar(data, b"doub", int, 5) == 5


def test_get_scalar_container_degrades_with_debug_log(caplog):
    data = Descriptor(classID=Klass.Null, items={b"list": List()})  # type: ignore[arg-type]
    with caplog.at_level("DEBUG", logger="psd_tools.api._descriptor"):
        assert get_scalar(data, b"list", int, 9) == 9
    assert "Cannot read" in caplog.text


def test_get_scalar_result_is_json_serializable(descriptor):
    json.dumps([get_scalar(descriptor, b"long", int, 0)])


def test_get_enum(descriptor):
    assert get_enum(descriptor, b"mode", Enum) is Enum.Multiply


def test_get_enum_degrades(descriptor):
    assert get_enum(descriptor, b"nope", Enum) is None
    assert get_enum(descriptor, b"miss", Enum) is None
    assert get_enum(descriptor, b"long", Enum, Enum.Normal) is Enum.Normal
    assert get_enum(None, b"mode", Enum, Enum.Normal) is Enum.Normal
