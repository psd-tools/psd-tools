"""Per-layer allocation guard at the numpy and PIL layer funnels (#842)."""

import gc
import tracemalloc
import warnings

import pytest

from psd_tools import PSDImage, PSDLargeImageWarning
from psd_tools.api.numpy_io import _layer_read_peak_bytes
from psd_tools.api.pil_io import _layer_peak_bytes

from psd_tools.constants import ChannelID

from .utils import full_name


def _rgb_layer(**kwargs):
    psd = PSDImage.open(full_name("clipping-mask2.psd"), **kwargs)
    return next(layer for layer in psd.descendants() if layer.name == "Background")


def test_layer_numpy_rejected_over_budget():
    layer = _rgb_layer(max_alloc_bytes=1000)
    with pytest.raises(ValueError, match="Peak allocation"):
        layer.numpy("color")


def test_layer_topil_rejected_over_budget():
    layer = _rgb_layer(max_alloc_bytes=1000)
    with pytest.raises(ValueError, match="Peak allocation"):
        layer.topil()


def test_layer_read_within_budget():
    layer = _rgb_layer(max_alloc_bytes=1 << 30)
    assert layer.numpy("color") is not None
    assert layer.topil() is not None


def test_composite_rejected_by_layer_guard():
    # A budget the canvas fits but a layer read does not.
    psd = PSDImage.open(full_name("clipping-mask2.psd"))
    canvas = psd.width * psd.height * 4 * 4
    psd._max_alloc_bytes = canvas
    with pytest.raises(ValueError, match="Peak allocation"):
        psd.composite(force=True)


def test_layer_peak_bounds_measured_numpy_peak():
    layer = _rgb_layer()
    gc.collect()
    tracemalloc.start()
    array = layer.numpy("color")
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert array is not None
    modelled = _layer_read_peak_bytes(layer.width, layer.height, 8, array.shape[2], 3)
    # Fixed interpreter-side objects are not modelled, as on the document paths.
    assert modelled + 65536 >= peak


def test_layer_peak_bounds_single_channel_read():
    # Sized from the channels the read selects, not the record's.
    layer = _rgb_layer()
    one = _layer_read_peak_bytes(layer.width, layer.height, 8, 1, 1)
    three = _layer_read_peak_bytes(layer.width, layer.height, 8, 3, 1)
    assert one < three


def test_zero_area_layer_reads_are_not_guarded():
    psd = PSDImage.open(full_name("empty-layer.psd"), max_alloc_bytes=1)
    empty = [
        layer
        for layer in psd.descendants()
        if layer.width * layer.height == 0 and not layer.is_group()
    ]
    assert empty
    for layer in empty:
        assert layer.numpy("color") is None
        assert layer.topil() is None
        assert _layer_peak_bytes(layer, None, True) is None


def test_layer_guard_does_not_warn_per_layer(monkeypatch):
    monkeypatch.setattr("psd_tools.api.utils.WARN_PIXELS", 1)
    layer = _rgb_layer()
    with warnings.catch_warnings():
        warnings.simplefilter("error", PSDLargeImageWarning)
        layer.numpy("color")
        layer.topil()


def test_layer_dimension_over_psd_maximum_rejected(monkeypatch):
    monkeypatch.setattr("psd_tools.api.utils.MAX_DIMENSION_PSD", 10)
    layer = _rgb_layer()
    with pytest.raises(ValueError, match="exceeds the PSD maximum"):
        layer.numpy("color")
    with pytest.raises(ValueError, match="exceeds the PSD maximum"):
        layer.topil()


def test_pil_peak_reports_read_planes():
    layer = _rgb_layer()
    _, _, planes, _ = _layer_peak_bytes(layer, None, False)
    assert planes == 3
    _, _, planes, _ = _layer_peak_bytes(layer, 0, False)
    assert planes == 1


def test_layer_mask_read_rejected_over_budget():
    psd = PSDImage.open(full_name("clipping-mask2.psd"), max_alloc_bytes=1)
    layer = next(x for x in psd.descendants() if x.mask is not None)
    with pytest.raises(ValueError, match="Peak allocation"):
        layer.numpy("mask")
    with pytest.raises(ValueError, match="Peak allocation"):
        layer.topil(channel=ChannelID.USER_LAYER_MASK)


def test_layer_with_empty_channel_data_is_not_guarded():
    layer = _rgb_layer(max_alloc_bytes=1)
    for c in layer._channels:
        c.data = b""
    assert layer.numpy("color") is None
    assert layer.topil() is None
    assert _layer_peak_bytes(layer, None, False) is None
