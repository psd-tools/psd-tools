"""Scalar property annotations must match what the property returns (#788).

Covers layers and the wrappers hanging off them: strokes, originations, masks,
vector masks, effects, smart objects and the top-level type setting. The
runs, paragraphs and styles beneath a type setting are not walked.
"""

import logging
import types
from typing import Any, Iterator, Union, get_args, get_origin

import pytest

from psd_tools.api.layers import SmartObjectLayer, TypeLayer
from psd_tools.api.psd_image import PSDImage

from ..utils import all_files

logger = logging.getLogger(__name__)

_SCALARS: dict[type, tuple[type, ...]] = {
    bool: (bool,),
    int: (int,),
    float: (int, float),  # PEP 484: an int satisfies float
    str: (str,),
}

_BY_NAME: dict[Any, type] = {t.__name__: t for t in _SCALARS}


def _scalar_of(annotation: Any) -> tuple[type, bool] | None:
    """The scalar an annotation promises, and whether `None` is allowed."""
    optional = False
    if isinstance(annotation, str):
        # `from __future__ import annotations` leaves the source text.
        optional = annotation.endswith(" | None")
        annotation = _BY_NAME.get(annotation.removesuffix(" | None"))
    elif get_origin(annotation) in (Union, types.UnionType):
        args = [a for a in get_args(annotation) if a is not type(None)]
        optional = len(args) < len(get_args(annotation))
        annotation = args[0] if len(args) == 1 else None
    return (annotation, optional) if annotation in _SCALARS else None


def _scalar_properties(cls: type) -> Iterator[tuple[str, type, bool]]:
    for klass in cls.__mro__:
        for name, attr in vars(klass).items():
            if not isinstance(attr, property) or attr.fget is None:
                continue
            # get_type_hints() cannot resolve every forward reference in api/.
            found = _scalar_of(attr.fget.__annotations__.get("return"))
            if found is not None:
                yield (name, *found)


def _objects(psd: PSDImage) -> Iterator[Any]:
    for layer in psd.descendants():
        yield layer
        if layer.has_stroke():
            yield layer.stroke
        if layer.has_mask():
            yield layer.mask
        if layer.has_vector_mask():
            yield layer.vector_mask
        yield layer.effects
        yield from layer.effects
        if isinstance(layer, SmartObjectLayer):
            yield layer.smart_object
        if isinstance(layer, TypeLayer):
            yield layer.typesetting
        # An Invalidated origination carries no live-shape properties.
        yield from (o for o in layer.origination if not o.invalidated)


@pytest.mark.parametrize("filename", all_files())
def test_scalar_annotations_match_runtime(filename: str) -> None:
    try:
        psd = PSDImage.open(filename)
        objects = list(_objects(psd))
    except Exception as e:  # Broken fixtures are covered by the parsing tests.
        pytest.skip(f"unreadable: {e}")

    mismatches = []
    for obj in objects:
        for name, annotation, optional in set(_scalar_properties(type(obj))):
            value = getattr(obj, name)
            if value is None and optional:
                continue
            if not isinstance(value, _SCALARS[annotation]):
                mismatches.append(
                    f"{type(obj).__name__}.{name}: {annotation.__name__}"
                    f" -> {type(value).__name__}"
                )
    assert not mismatches, sorted(set(mismatches))
