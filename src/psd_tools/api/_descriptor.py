"""Typed boundary for reading descriptor values from ``psd_tools.api``."""

from __future__ import annotations

import logging
import math
from enum import Enum
from numbers import Real
from typing import Any, Mapping, TypeVar, overload

from psd_tools.constants import BlendMode
from psd_tools.psd.base import DictElement
from psd_tools.psd.descriptor import Descriptor
from psd_tools.terminology import Enum as Term

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


def get_descriptor(data: _Data, key: _Key) -> Descriptor | None:
    """Read the object at *key* as a :py:class:`Descriptor`.

    Returns ``None`` when the key is absent or holds anything else.
    """
    raw = _lookup(data, key)
    if raw is None or isinstance(raw, Descriptor):
        return raw
    logger.debug("Cannot read %r as Descriptor: %r", key, raw)
    return None


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


# A descriptor names a blend mode by terminology code (`Nrml`) or by long name
# (`normal`), never by layer-record code (`norm`).
DESCRIPTOR_BLEND_MODES: dict[bytes, BlendMode] = {
    code: mode
    for mode, codes in {
        BlendMode.NORMAL: (Term.Normal, b"normal"),
        BlendMode.DISSOLVE: (Term.Dissolve, b"dissolve"),
        BlendMode.DARKEN: (Term.Darken, b"darken"),
        BlendMode.MULTIPLY: (Term.Multiply, b"multiply"),
        BlendMode.COLOR_BURN: (Term.ColorBurn, b"colorBurn"),
        BlendMode.LINEAR_BURN: (b"linearBurn",),
        BlendMode.DARKER_COLOR: (b"darkerColor",),
        BlendMode.LIGHTEN: (Term.Lighten, b"lighten"),
        BlendMode.SCREEN: (Term.Screen, b"screen"),
        BlendMode.COLOR_DODGE: (Term.ColorDodge, b"colorDodge"),
        BlendMode.LINEAR_DODGE: (b"linearDodge",),
        BlendMode.LIGHTER_COLOR: (b"lighterColor",),
        BlendMode.OVERLAY: (Term.Overlay, b"overlay"),
        BlendMode.SOFT_LIGHT: (Term.SoftLight, b"softLight"),
        BlendMode.HARD_LIGHT: (Term.HardLight, b"hardLight"),
        BlendMode.VIVID_LIGHT: (b"vividLight",),
        BlendMode.LINEAR_LIGHT: (b"linearLight",),
        BlendMode.PIN_LIGHT: (b"pinLight",),
        BlendMode.HARD_MIX: (b"hardMix",),
        BlendMode.DIFFERENCE: (Term.Difference, b"difference"),
        BlendMode.EXCLUSION: (Term.Exclusion, b"exclusion"),
        BlendMode.SUBTRACT: (Term.Subtract, b"blendSubtraction"),
        BlendMode.DIVIDE: (b"blendDivide",),
        BlendMode.HUE: (Term.Hue, b"hue"),
        BlendMode.SATURATION: (Term.Saturation, b"saturation"),
        BlendMode.COLOR: (Term.Color, b"color"),
        BlendMode.LUMINOSITY: (Term.Luminosity, b"luminosity"),
    }.items()
    for code in codes
}


@overload
def get_blend_mode(data: _Data, key: _Key) -> BlendMode | None: ...
@overload
def get_blend_mode(data: _Data, key: _Key, default: BlendMode) -> BlendMode: ...
def get_blend_mode(
    data: _Data, key: _Key, default: BlendMode | None = None
) -> BlendMode | None:
    """Read the blend mode ``Enumerated`` at *key* as a :py:class:`BlendMode`.

    Returns *default* when the key is absent or its code is not a blend mode.
    """
    raw = _lookup(data, key)
    if raw is None:
        return default
    mode = DESCRIPTOR_BLEND_MODES.get(getattr(raw, "enum", b""))
    if mode is None:
        logger.debug("Cannot read %r as BlendMode: %r", key, raw)
        return default
    return mode
