"""Moving a layer into another document raises, pointing at copy_to (#1005)."""

import warnings
from collections.abc import Callable
from typing import Any, cast

import pytest

from psd_tools import PSDImage
from psd_tools.api.layers import Group, Layer

from ..utils import full_name


def _documents() -> tuple[PSDImage, PSDImage]:
    return PSDImage.open(full_name("2layers.psd")), PSDImage.open(
        full_name("hidden-groups.psd")
    )


_OPERATIONS: dict[str, Callable[[PSDImage, Layer], object]] = {
    "append": lambda dest, layer: dest.append(layer),
    "extend": lambda dest, layer: dest.extend([layer]),
    "insert": lambda dest, layer: dest.insert(0, layer),
    "setitem": lambda dest, layer: dest.__setitem__(0, layer),
    "create_group": lambda dest, layer: dest.create_group([layer]),
}


@pytest.mark.parametrize("operation", _OPERATIONS)
def test_a_cross_document_move_raises_and_changes_nothing(operation: str) -> None:
    dest, source = _documents()
    layer = source[0]
    dest_layers, source_layers = list(dest), list(source)

    with pytest.raises(ValueError, match="copy_to"):
        _OPERATIONS[operation](dest, layer)

    assert list(dest) == dest_layers
    assert list(source) == source_layers
    assert layer.parent is source


def test_a_non_layer_item_raises_type_error() -> None:
    dest, _ = _documents()

    with pytest.raises(TypeError):
        dest.create_group([1])  # type: ignore[list-item]


def test_a_nested_cross_document_layer_raises() -> None:
    dest, source = _documents()
    group = next(layer for layer in source.descendants() if isinstance(layer, Group))
    child = next(iter(group))

    with pytest.raises(ValueError, match="copy_to"):
        dest.append(child)


@pytest.mark.parametrize("operation", ["append", "extend", "insert", "setitem"])
def test_an_in_document_move_still_moves(operation: str) -> None:
    dest = PSDImage.open(full_name("hidden-groups.psd"))
    group = next(layer for layer in dest.descendants() if isinstance(layer, Group))
    layer = dest[0] if dest[0] is not group else dest[1]

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _OPERATIONS[operation](cast(Any, group), layer)
        dest.create_group([dest[0]])

    assert layer.parent is group


def test_copy_to_still_crosses_documents() -> None:
    dest, source = _documents()

    copy = source[0].copy_to(dest)

    assert copy in dest and copy is not source[0]
