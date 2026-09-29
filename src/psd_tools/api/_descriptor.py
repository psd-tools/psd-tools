"""Typed boundary for reading descriptor values from ``psd_tools.api``."""

from __future__ import annotations

import logging
import math
from enum import Enum
from numbers import Real
from typing import Any, TypeVar, overload

from psd_tools.psd.base import DictElement

logger = logging.getLogger(__name__)

_S = TypeVar("_S", int, float, bool, str)
_E = TypeVar("_E", bound=Enum)


def _lookup(data: DictElement | None, key: bytes) -> Any:
    return None if data is None else data.get(key)


def get_scalar(
    data: DictElement | None, key: bytes, type_: type[_S], default: _S
) -> _S:
    """Read *key* as a plain *type_*, whatever OSType it arrived as.

    A float read as ``int`` truncates toward zero. Returns *default*, coerced to
    *type_*, when the key is absent (silently) or the value cannot be coerced
    (with a debug log).
    """
    fallback: _S = type_(default)  # type: ignore[call-overload]
    raw = _lookup(data, key)
    if raw is None:
        return fallback
    value = getattr(raw, "value", raw)
    try:
        if type_ is str:
            if isinstance(value, str):
                return value  # type: ignore[return-value]
        elif isinstance(value, Real) and not (
            type_ is int and not math.isfinite(value)
        ):
            return type_(value)  # type: ignore[return-value,call-overload]
    except (TypeError, ValueError, OverflowError):
        pass
    logger.debug("Cannot read %r as %s: %r", key, type_.__name__, raw)
    return fallback


@overload
def get_enum(data: DictElement | None, key: bytes, enum_cls: type[_E]) -> _E | None: ...
@overload
def get_enum(
    data: DictElement | None, key: bytes, enum_cls: type[_E], default: _E
) -> _E: ...
def get_enum(
    data: DictElement | None,
    key: bytes,
    enum_cls: type[_E],
    default: _E | None = None,
) -> _E | None:
    """Read the ``Enumerated`` at *key* as an *enum_cls* member.

    Returns *default* when the key is absent or its value is not a member.
    """
    raw = _lookup(data, key)
    if raw is None:
        return default
    try:
        return enum_cls(raw.enum)
    except (AttributeError, ValueError):
        logger.debug("Cannot read %r as %s: %r", key, enum_cls.__name__, raw)
        return default
