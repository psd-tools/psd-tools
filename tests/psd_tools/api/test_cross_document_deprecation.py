"""Moving a layer into another document is deprecated in favour of copy_to (#1001)."""

import warnings
from collections.abc import Callable

import pytest

from psd_tools import PSDImage
from psd_tools.api.layers import Group, Layer

from ..utils import full_name


def _documents() -> tuple[PSDImage, PSDImage]:
    return PSDImage.open(full_name("2layers.psd")), PSDImage.open(
        full_name("hidden-groups.psd")
    )


_OPERATIONS: dict[str, Callable[[PSDImage, Layer], None]] = {
    "append": lambda dest, layer: dest.append(layer),
    "extend": lambda dest, layer: dest.extend([layer]),
    "insert": lambda dest, layer: dest.insert(0, layer),
    "setitem": lambda dest, layer: dest.__setitem__(0, layer),
}


@pytest.mark.parametrize("operation", _OPERATIONS)
def test_a_cross_document_move_warns_at_the_caller(operation: str) -> None:
    dest, source = _documents()
    layer = source[0]

    with pytest.warns(DeprecationWarning, match="copy_to") as record:
        _OPERATIONS[operation](dest, layer)

    assert record[0].filename == __file__


def test_create_group_warns_at_the_caller() -> None:
    dest, source = _documents()

    with pytest.warns(DeprecationWarning, match="copy_to") as record:
        dest.create_group([source[0]])

    assert record[0].filename == __file__


def test_a_move_still_moves_while_deprecated() -> None:
    dest, source = _documents()
    layer = source[0]

    with pytest.warns(DeprecationWarning):
        dest.append(layer)

    assert layer in dest and layer not in source


@pytest.mark.parametrize("operation", _OPERATIONS)
def test_an_in_document_move_does_not_warn(operation: str) -> None:
    dest = PSDImage.open(full_name("hidden-groups.psd"))
    group = next(layer for layer in dest.descendants() if isinstance(layer, Group))
    layer = dest[0] if dest[0] is not group else dest[1]

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        if operation == "append":
            group.append(layer)
        elif operation == "extend":
            group.extend([layer])
        elif operation == "insert":
            group.insert(0, layer)
        else:
            group[0] = layer
        dest.create_group([dest[0]])


def test_copy_to_does_not_warn() -> None:
    dest, source = _documents()

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        source[0].copy_to(dest)
