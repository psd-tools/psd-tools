from typing import Any, Type
import logging
import importlib
import math
import numbers
import pkgutil
from enum import Enum
from fractions import Fraction

import attrs
import pytest

import psd_tools.psd

from psd_tools.psd.base import (
    BooleanElement,
    ByteElement,
    DictElement,
    EmptyElement,
    IntegerElement,
    ListElement,
    NumericElement,
    ShortIntegerElement,
    StringElement,
)

from ..utils import check_write_read

logger = logging.getLogger(__name__)


def test_empty() -> None:
    check_write_read(EmptyElement())


@pytest.mark.parametrize(
    "fixture",
    [
        "",
        "a",
        "ab",
        "\u0034\u0035\u0036",
    ],
)
def test_string(fixture: str) -> None:
    value = StringElement(fixture)
    check_write_read(value)
    assert value == fixture
    assert repr(value) == repr(fixture)
    assert hash(value) == hash(fixture)
    assert (value % tuple()) == fixture


@pytest.mark.parametrize(
    "kls, fixture",
    [
        (ByteElement, 1),
        (ShortIntegerElement, 1),
        (IntegerElement, 1),
        (NumericElement, 1.0),
    ],
)
def test_numbers(kls: Type[Any], fixture: int) -> None:
    value = kls(fixture)
    check_write_read(value)
    assert value == fixture
    assert (value + fixture) == (fixture * 2)
    assert repr(value) == repr(fixture)
    assert hash(value) == hash(fixture)


def _abc_members(abc: Type[Any]) -> set:
    """Every member the ABC promises, abstract methods *and* concrete mixins.

    ``register()`` supplies neither, so the mixins are the part that a bare
    registration would silently leave missing.
    """
    dunder_noise = {
        "__abstractmethods__",
        "__class_getitem__",
        "__dict__",
        "__doc__",
        "__init_subclass__",
        "__module__",
        "__orig_bases__",
        "__parameters__",
        "__qualname__",
        "__slots__",
        "__subclasshook__",
        "__weakref__",
    }
    members = set()
    for kls in abc.__mro__:
        if kls is object:
            continue
        members |= {
            name
            for name in vars(kls)
            if (not name.startswith("_") or name.startswith("__"))
            and name not in dunder_noise
            and not name.startswith("_abc")
        }
    return members


@pytest.mark.parametrize(
    "kls, fixture, integral",
    [
        (NumericElement, 1.5, False),
        (IntegerElement, 3, True),
        (ShortIntegerElement, 3, True),
        (ByteElement, 3, True),
        (BooleanElement, True, True),
    ],
)
def test_numbers_abc(kls: Type[Any], fixture: Any, integral: bool) -> None:
    value = kls(fixture)
    assert isinstance(value, numbers.Number)
    assert isinstance(value, numbers.Complex)
    assert isinstance(value, numbers.Real)
    assert isinstance(value, numbers.Integral) is integral


@pytest.mark.parametrize(
    "abc, kls",
    [
        (numbers.Real, NumericElement),
        (numbers.Integral, IntegerElement),
    ],
)
def test_numbers_abc_members_present(abc: Type[Any], kls: Type[Any]) -> None:
    """The registration must not outlive the protocol it claims to implement.

    Deliberately not ``hasattr``: attribute lookup on a class also searches the
    metaclass, so ``__or__``, ``__eq__`` and friends would be satisfied by
    ``type``/``object`` however broken the element was.
    """
    defined = {name for k in kls.__mro__ if k is not object for name in vars(k).keys()}
    missing = sorted(name for name in _abc_members(abc) if name not in defined)
    assert missing == []


@pytest.mark.parametrize(
    "kls, fixture",
    [
        (NumericElement, 1.5),
        (NumericElement, 2.5),
        (NumericElement, -2.5),
        (NumericElement, -3.5),
        (IntegerElement, 3),
        (ShortIntegerElement, 3),
        (ByteElement, 3),
        (BooleanElement, True),
    ],
)
def test_numbers_protocol(kls: Type[Any], fixture: Any) -> None:
    value = kls(fixture)
    assert round(value) == round(fixture)
    assert round(value, 1) == round(fixture, 1)
    assert math.trunc(value) == math.trunc(fixture)
    assert math.floor(value) == math.floor(fixture)
    assert math.ceil(value) == math.ceil(fixture)
    assert complex(value) == complex(fixture)
    assert value.real == fixture.real
    assert value.imag == fixture.imag
    assert value.conjugate() == fixture.conjugate()
    assert f"{value:.2f}" == f"{fixture:.2f}"
    assert f"{value}" == f"{fixture}"
    assert format(value, "") == format(fixture, "")


@pytest.mark.parametrize(
    "kls, fixture",
    [
        (IntegerElement, 3),
        (ShortIntegerElement, 3),
        (ByteElement, 3),
        (BooleanElement, True),
    ],
)
def test_integral_protocol(kls: Type[Any], fixture: int) -> None:
    value = kls(fixture)
    assert value.numerator == fixture.numerator
    assert value.denominator == fixture.denominator
    assert pow(value, 3, 5) == pow(fixture, 3, 5)


@pytest.mark.parametrize(
    "kls, fixture",
    [
        (NumericElement, 7.5),
        (IntegerElement, 7),
        (ShortIntegerElement, 7),
        (ByteElement, 7),
        (BooleanElement, True),
    ],
)
def test_numbers_operators_between_elements(kls: Type[Any], fixture: Any) -> None:
    """Both operands are `numbers.Real`, so no operator may refuse the pair.

    Delegating through ``value.__truediv__(other)`` instead of ``value / other``
    returns ``NotImplemented`` here and raises, which is exactly the kind of
    lie the ABC registration must not tell.
    """
    value = kls(fixture)
    assert value + value == fixture + fixture
    assert value - value == fixture - fixture
    assert value * value == fixture * fixture
    assert value / value == fixture / fixture
    assert value // value == fixture // fixture
    assert value % value == fixture % fixture
    assert divmod(value, value) == divmod(fixture, fixture)
    assert value**value == fixture**fixture


@pytest.mark.parametrize(
    "kls, fixture",
    [
        (IntegerElement, 7),
        (ShortIntegerElement, 7),
        (ByteElement, 7),
        (BooleanElement, True),
    ],
)
def test_integral_operators_between_elements(kls: Type[Any], fixture: int) -> None:
    value = kls(fixture)
    assert value & value == fixture & fixture
    assert value | value == fixture | fixture
    assert value ^ value == fixture ^ fixture
    assert value << kls(1) == fixture << 1
    assert value >> kls(1) == fixture >> 1
    assert ~value == ~fixture


def test_numbers_interoperate_with_fractions() -> None:
    """A registered ``numbers.Real`` has to work as the right-hand operand.

    The ``type: ignore`` is the point of the exercise rather than a wart: a
    virtual registration is invisible to a static checker, which is why PEP 484
    rules the ``numbers`` ABCs out for annotations. This buys runtime
    ``isinstance`` only, and ``float(value)`` remains the way to satisfy mypy.
    """
    assert Fraction(1, 2) + NumericElement(2.5) == 3.0
    assert Fraction(1, 2) * IntegerElement(4) == 2
    assert Fraction(IntegerElement(3)) == Fraction(3, 1)  # type: ignore[call-overload]


def test_every_numeric_subclass_is_registered() -> None:
    """Sweep the package, so a future subclass cannot re-open the hole.

    A subclass that re-declares ``value`` without a numeric converter, or that
    lets attrs generate ``__eq__`` (which also sets ``__hash__`` to ``None``),
    would inherit the registration while breaking what it promises. Both have
    happened: ``UnitFloat`` and ``PixelAspectRatio``.
    """
    for module in pkgutil.iter_modules(psd_tools.psd.__path__):
        importlib.import_module(f"psd_tools.psd.{module.name}")

    def descendants(kls: Type[Any]) -> Any:
        for subclass in kls.__subclasses__():
            yield subclass
            yield from descendants(subclass)

    subclasses = {NumericElement, *descendants(NumericElement)}
    assert len(subclasses) > 1
    for kls in subclasses:
        assert issubclass(kls, numbers.Real), kls
        assert issubclass(kls, numbers.Integral) is issubclass(kls, IntegerElement), kls
        assert kls.__hash__ is not None, kls
        converter = next(f for f in attrs.fields(kls) if f.name == "value").converter
        assert converter in (float, int, bool), (kls, converter)


def test_numeric_element_rejects_a_modulus() -> None:
    """The float branch of the widened ``__pow__`` must refuse a modulus."""
    with pytest.raises(TypeError):
        pow(NumericElement(2.5), 3, 5)


@pytest.mark.parametrize(
    "kls, fixture",
    [
        (ByteElement, b"\x01\x00"),
        (ShortIntegerElement, b"\x00\x01"),
        (BooleanElement, b"\x00\x01"),
    ],
)
def test_malformed_numbers(kls: Type[Any], fixture: bytes) -> None:
    kls.frombytes(fixture)


def test_boolean() -> None:
    value = BooleanElement(True)
    assert value.value is True
    assert value
    value = BooleanElement(False)
    assert value.value is False
    assert not value


def test_list() -> None:
    value = ListElement(list(range(10)))  # type: ignore[arg-type]
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
    A = b"x"
    B = b"y"
    C = b"x"


def test_dict() -> None:
    value = DictElement()
    value[Dummy.A] = "foo"
    assert value.get(Dummy.A) == value.get(b"x")
    assert list(value.keys())[0] == Dummy.A
    assert list(value.keys())[0] == b"x"
    assert Dummy.A in value
    assert b"x" in value
    assert value[Dummy.A] == "foo"
    assert value[Dummy(b"x")] == "foo"
    assert value[b"x"] == "foo"
    repr(value)
    del value[Dummy.A]
