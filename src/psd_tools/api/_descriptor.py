"""Typed boundary for reading descriptor values from ``psd_tools.api``."""

from __future__ import annotations

import logging
import math
from enum import Enum
from numbers import Real
from typing import Any, Mapping, TypeVar, overload

from psd_tools.psd.base import DictElement

logger = logging.getLogger(__name__)

_S = TypeVar("_S", int, float, bool, str)
_E = TypeVar("_E", bound=Enum)


_Data = DictElement | Mapping[Any, Any] | None
_Key = bytes | str


def _lookup(data: _Data, key: _Key) -> Any:
    return None if data is None else data.get(key)


@overload
def get_scalar(data: _Data, key: _Key, type_: type[_S], default: None) -> _S | None: ...
@overload
def get_scalar(data: _Data, key: _Key, type_: type[_S], default: _S) -> _S: ...
def get_scalar(
    data: _Data, key: _Key, type_: type[_S], default: _S | None
) -> _S | None:
    """Read *key* as a plain *type_*, whatever OSType it arrived as.

    A float read as ``int`` truncates toward zero. Returns *default*, coerced to
    *type_*, when the key is absent (silently) or the value cannot be coerced
    (with a debug log). A *default* of ``None`` is returned as is.
    """
    return coerce_scalar(_lookup(data, key), type_, default, key)


@overload
def coerce_scalar(
    raw: Any, type_: type[_S], default: None, label: Any = ...
) -> _S | None: ...
@overload
def coerce_scalar(raw: Any, type_: type[_S], default: _S, label: Any = ...) -> _S: ...
def coerce_scalar(
    raw: Any, type_: type[_S], default: _S | None, label: Any = None
) -> _S | None:
    """Read an already fetched *raw* value as :py:func:`get_scalar` does.

    *label* names the value in the debug log.
    """
    fallback: _S | None = (
        None if default is None else type_(default)  # type: ignore[call-overload]
    )
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
    logger.debug("Cannot read %r as %s: %r", label, type_.__name__, raw)
    return fallback


@overload
def get_enum(data: _Data, key: _Key, enum_cls: type[_E]) -> _E | None: ...
@overload
def get_enum(data: _Data, key: _Key, enum_cls: type[_E], default: _E) -> _E: ...
def get_enum(
    data: _Data,
    key: _Key,
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
