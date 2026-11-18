import warnings
from collections.abc import Callable

import pytest

from psd_tools import PSDImage
from psd_tools.api.layers import Group, Layer

from ..utils import full_name


def _psd() -> PSDImage:
    return PSDImage.open(full_name("group.psd"))


def _group(psd: PSDImage) -> Group:
    return next(layer for layer in psd if isinstance(layer, Group))


_CALLS: dict[str, Callable[[PSDImage], object]] = {
    "move_to_group": lambda psd: psd[0].move_to_group(_group(psd)),
    "group_layers": lambda psd: Group.group_layers(psd, [psd[0]]),
    "delete_layer": lambda psd: _group(psd)[0].delete_layer(),
    "clipping_layer_get": lambda psd: psd[0].clipping_layer,
    "clipping_layer_set": lambda psd: setattr(psd[0], "clipping_layer", True),
}


@pytest.mark.parametrize("name", _CALLS)
def test_deprecated_api_warns_at_the_caller(name: str) -> None:
    psd = _psd()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _CALLS[name](psd)

    deprecations = [w for w in caught if w.category is DeprecationWarning]
    assert len(deprecations) == 1
    assert deprecations[0].filename == __file__


def test_clipping_layer_still_reads_and_writes_clipping() -> None:
    layer: Layer = _psd()[0]
    with pytest.warns(DeprecationWarning):
        layer.clipping_layer = True
    assert layer.clipping
    with pytest.warns(DeprecationWarning):
        assert layer.clipping_layer
