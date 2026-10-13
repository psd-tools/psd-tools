"""Per-layer allocation guard at the numpy and PIL layer funnels (#842)."""

import gc
import tracemalloc
import warnings

import numpy as np
import pytest
from PIL import Image

from psd_tools import PSDImage, PSDLargeImageWarning
from psd_tools.api import numpy_io
from psd_tools.api.layers import Layer
from psd_tools.api.numpy_io import _layer_read_peak_bytes
from psd_tools.api.pil_io import _layer_peak_bytes

from psd_tools.compression import decompress_row_peak_bytes
from psd_tools.constants import ChannelID, Compression

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


def test_layer_inherits_budget_set_after_open():
    layer = _rgb_layer(max_alloc_bytes="unlimited")
    assert layer.numpy("color") is not None
    layer._psd.max_alloc_bytes = 1000
    with pytest.raises(ValueError, match="1,000 bytes"):
        layer.numpy("color")


def test_layer_read_within_budget():
    layer = _rgb_layer(max_alloc_bytes=1 << 30)
    assert layer.numpy("color") is not None
    assert layer.topil() is not None


def test_composite_rejected_by_layer_guard():
    # A budget the canvas fits but a layer read does not.
    psd = PSDImage.open(full_name("clipping-mask2.psd"))
    canvas = psd.width * psd.height * 4 * 4
    psd.max_alloc_bytes = canvas
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


def test_numpy_peak_charges_held_bytes_in_every_phase():
    base = _layer_read_peak_bytes(100, 100, 8, 1, 3)
    assert _layer_read_peak_bytes(100, 100, 8, 1, 3, held=7) == base + 7


def test_shape_read_is_sized_with_the_color_array_held(monkeypatch):
    seen = []
    real = numpy_io._layer_read_peak_bytes

    def spy(*args, **kwargs):
        seen.append(args[5] if len(args) > 5 else kwargs.get("held", 0))
        return real(*args, **kwargs)

    monkeypatch.setattr(numpy_io, "_layer_read_peak_bytes", spy)
    psd = PSDImage.open(full_name("semi-transparent-layers.psd"))
    layer = next(
        x
        for x in psd.descendants()
        if x.width * x.height > 0
        and any(
            i.id == ChannelID.TRANSPARENCY_MASK and len(c.data) > 0
            for i, c in zip(x._record.channel_info, x._channels)
        )
    )
    layer.numpy()
    assert seen[0] == 0
    assert seen[1] == layer.numpy("color").nbytes


def test_pil_decompress_phase_holds_earlier_planes():
    layer = _rgb_layer()
    _, _, planes, peak = _layer_peak_bytes(layer, None, False)
    pixels = layer.width * layer.height
    assert peak >= pixels * (planes - 1)


def test_pil_widening_only_charged_with_a_stored_alpha():
    layer = _rgb_layer()
    assert all(i.id != ChannelID.TRANSPARENCY_MASK for i in layer._record.channel_info)
    _, _, _, peak = _layer_peak_bytes(layer, None, False)
    # Merge phase: three retained bands, the slack plane and the merged image.
    assert peak == layer.width * layer.height * 7


def test_backing_bytes_charges_the_owner_of_a_truncated_view():
    full = np.zeros((4, 4, 4), dtype=np.float32)
    assert numpy_io._backing_bytes(full[:, :, :3]) == full.nbytes
    assert numpy_io._backing_bytes(full.reshape(16, 4)[:, :3]) == full.nbytes


def test_repeated_channel_ids_are_charged_once_per_decode():
    layer = _rgb_layer()
    _, _, planes, peak = _layer_peak_bytes(layer, None, False)
    info, data = layer._record.channel_info[0], layer._channels[0]
    empty = type(data)(compression=data.compression, data=b"")
    for _ in range(50):
        layer._record.channel_info.insert(0, info)
        layer._channels.insert(0, empty)
    _, _, repeated, repeated_peak = _layer_peak_bytes(layer, None, False)
    assert repeated == planes + 50
    assert repeated_peak > peak
    layer._psd._max_alloc_bytes = peak
    with pytest.raises(ValueError, match="Peak allocation"):
        layer.topil()


def test_compositor_shape_read_is_sized_with_the_color_array_held(monkeypatch):
    seen = []
    real = numpy_io._layer_read_peak_bytes

    def spy(*args, **kwargs):
        seen.append(args[5] if len(args) > 5 else kwargs.get("held", 0))
        return real(*args, **kwargs)

    monkeypatch.setattr(numpy_io, "_layer_read_peak_bytes", spy)
    psd = PSDImage.open(full_name("semi-transparent-layers.psd"))
    psd.composite(force=True)
    assert any(h > 0 for h in seen)


def test_compositor_shape_read_dispatches_through_layer_numpy(monkeypatch):
    real = Layer.numpy
    calls = []

    def spy(self, channel=None, real_mask=True):
        calls.append(channel)
        return real(self, channel, real_mask)

    monkeypatch.setattr(Layer, "numpy", spy)
    psd = PSDImage.open(full_name("semi-transparent-layers.psd"))
    psd.composite(force=True)
    assert "shape" in calls


def test_topil_unknown_channel_id_returns_none():
    assert _rgb_layer().topil(channel=10) is None


def _tall_narrow_layer(rows: int) -> Layer:
    """A one-pixel-wide layer, whose channels the writer stores as RLE."""
    psd = PSDImage.new("RGB", (1, rows))
    return psd.create_pixel_layer(Image.new("RGB", (1, rows)), name="L")


def test_a_tall_narrow_rle_layer_is_not_admitted_at_its_payload_peak() -> None:
    """The rows an RLE decode holds are part of what the guard has to bound.

    ``_layer_read_peak_bytes()`` without ``row_objects`` sizes the codec's
    payload alone, which on a one-pixel-wide channel is a fraction of what the
    read allocates: a budget set at it admits a read that then allocates several
    times past it. Both rows below are the guard's own decisions rather than a
    measured peak, which belongs to the platform it was taken on.
    """
    rows = 8000
    layer = _tall_narrow_layer(rows)
    assert {c.compression for c in layer._channels} == {Compression.RLE}

    payload_only = _layer_read_peak_bytes(
        1, rows, 8, 3, numpy_io._DECOMPRESS_PEAK[Compression.RLE]
    )
    layer._psd._max_alloc_bytes = payload_only
    with pytest.raises(ValueError, match="Peak allocation"):
        layer.numpy("color")

    # The payload and the rows it holds, which is what the guard is given.
    charged = payload_only + decompress_row_peak_bytes(Compression.RLE, rows)
    layer._psd._max_alloc_bytes = charged
    assert layer.numpy("color") is not None
