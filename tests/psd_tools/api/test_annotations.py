"""Scalar property annotations must match what the property returns (#788)."""

import logging
from typing import Any, Iterator

import pytest

from psd_tools.api.psd_image import PSDImage

from ..utils import all_files

logger = logging.getLogger(__name__)

_SCALARS: dict[type, tuple[type, ...]] = {
    bool: (bool,),
    int: (int,),
    float: (int, float),  # PEP 484: an int satisfies float
    str: (str,),
}


def _scalar_properties(cls: type) -> Iterator[tuple[str, type]]:
    for klass in cls.__mro__:
        for name, attr in vars(klass).items():
            if not isinstance(attr, property) or attr.fget is None:
                continue
            # get_type_hints() cannot resolve every forward reference in api/.
            annotation = attr.fget.__annotations__.get("return")
            if annotation in _SCALARS:
                yield name, annotation


def _objects(psd: PSDImage) -> Iterator[Any]:
    for layer in psd.descendants():
        yield layer
        if layer.has_stroke():
            yield layer.stroke
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
        for name, annotation in set(_scalar_properties(type(obj))):
            value = getattr(obj, name)
            if not isinstance(value, _SCALARS[annotation]):
                mismatches.append(
                    f"{type(obj).__name__}.{name}: {annotation.__name__}"
                    f" -> {type(value).__name__}"
                )
    assert not mismatches, sorted(set(mismatches))
