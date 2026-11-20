"""``toarray`` and the array forms of the document and mask entry points (#995)."""

from typing import Literal

import numpy as np
import pytest

from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import Compression

FINE = (((np.arange(4 * 6 * 4).reshape(4, 6, 4) * 1237 + 11) % 65535) / 65535.0).astype(
    np.float32
)
MASK = (((np.arange(5 * 7).reshape(5, 7) * 977 + 5) % 65535) / 65535.0).astype(
    np.float32
)


def _layer(depth: Literal[8, 16, 32] = 8):  # type: ignore[no-untyped-def]
    psd = PSDImage.new("RGB", (8, 8), depth=depth)
    return psd.create_pixel_layer_from_array(np.ones((5, 7, 3), dtype=np.float32))


def test_toarray_matches_numpy() -> None:
    psd = PSDImage.new("RGB", (4, 3), color=(10, 20, 30))
    layer = _layer()
    np.testing.assert_array_equal(psd.toarray(), psd.numpy())
    assert type(layer).numpy is type(layer).toarray
    toarray, numpy = layer.toarray(), layer.numpy()
    assert toarray is not None and numpy is not None
    np.testing.assert_array_equal(toarray, numpy)
    assert layer.toarray("shape") is not None


@pytest.mark.parametrize("depth", [8, 16, 32])
@pytest.mark.parametrize(
    "mode, channels", [("L", 1), ("RGB", 3), ("RGBA", 4), ("CMYK", 4), ("LAB", 3)]
)
def test_psdimage_fromarray_round_trip(
    mode: str, channels: int, depth: Literal[8, 16, 32]
) -> None:
    array = FINE[:, :, :channels].copy()
    if mode == "RGBA":
        # The preview is stored over white, so colour is recoverable only
        # where the pixel is mostly opaque.
        array[:, :, 3] = 0.9 + 0.1 * array[:, :, 3]
    psd = PSDImage.fromarray(array, mode=mode, depth=depth)
    assert (psd.width, psd.height, psd.depth) == (6, 4, depth)
    tolerance = {8: 1 / 255, 16: 1 / 65535, 32: 1e-5}[depth]
    np.testing.assert_allclose(psd.toarray(), array, atol=tolerance)


@pytest.mark.parametrize(
    "dtype, depth", [(np.uint8, 8), (np.uint16, 16), (np.float32, 32)]
)
def test_psdimage_fromarray_depth_follows_dtype(dtype: type, depth: int) -> None:
    array: np.ndarray = (FINE[:, :, :3] * 255).astype(dtype)
    psd = PSDImage.fromarray(array)
    assert psd.depth == depth
    assert psd.toarray().shape == (4, 6, 3)


def test_psdimage_fromarray_infers_mode_from_channels() -> None:
    assert PSDImage.fromarray(FINE[:, :, 0]).color_mode.name == "GRAYSCALE"
    assert PSDImage.fromarray(FINE[:, :, :3]).channels == 3
    assert PSDImage.fromarray(FINE).channels == 4


def test_psdimage_fromarray_round_trips_through_save(tmp_path) -> None:  # type: ignore[no-untyped-def]
    psd = PSDImage.fromarray(FINE, depth=16, compression=Compression.RAW)
    path = tmp_path / "out.psd"
    psd.save(path)
    np.testing.assert_allclose(PSDImage.open(path).toarray(), psd.toarray(), atol=1e-6)


@pytest.mark.parametrize(
    "array, mode, exception",
    [
        (FINE[:, :, :3], "CMYK", ValueError),
        (FINE[:, :, :2], None, ValueError),
        (FINE[:, :, :1], "Indexed", ValueError),
        (np.zeros((0, 4, 3), dtype=np.uint8), None, ValueError),
        (np.zeros((4, 4, 3), dtype=np.int32), None, TypeError),
        ([[0]], None, TypeError),
    ],
)
def test_psdimage_fromarray_rejects(array, mode, exception) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(exception):
        PSDImage.fromarray(array, mode=mode)


@pytest.mark.parametrize("depth", [8, 16, 32])
def test_create_mask_from_array_keeps_depth(depth: Literal[8, 16, 32]) -> None:
    layer = _layer(depth)
    mask = layer.create_mask_from_array(MASK, compression=Compression.RAW)
    assert mask is not None and layer.has_mask()
    assert (mask.left, mask.top) == (layer.left, layer.top)
    assert (mask.width, mask.height) == (7, 5)
    tolerance = {8: 1 / 255, 16: 1 / 65535, 32: 1e-6}[depth]
    out = layer.toarray("mask", real_mask=False)
    assert out is not None
    np.testing.assert_allclose(out[:, :, 0], MASK, atol=tolerance)


def test_create_mask_from_array_accepts_a_channel_axis_and_offsets() -> None:
    layer = _layer()
    mask = layer.create_mask_from_array(
        (MASK * 255).astype(np.uint8)[:, :, np.newaxis], top=2, left=3
    )
    assert (mask.top, mask.left) == (2, 3)


def test_update_mask_from_array_replaces_the_mask() -> None:
    layer = _layer(16)
    layer.create_mask_from_array(MASK)
    mask = layer.update_mask_from_array(MASK[:3, :4] * 0.5, top=1)
    assert (mask.top, mask.width, mask.height) == (1, 4, 3)
    out = layer.toarray("mask", real_mask=False)
    assert out is not None
    np.testing.assert_allclose(out[:, :, 0], MASK[:3, :4] * 0.5, atol=1e-4)


def test_mask_from_array_state_errors() -> None:
    layer = _layer()
    with pytest.raises(ValueError, match="does not have a mask"):
        layer.update_mask_from_array(MASK)
    layer.create_mask_from_array(MASK)
    with pytest.raises(ValueError, match="already has a mask"):
        layer.create_mask_from_array(MASK)


@pytest.mark.parametrize(
    "array, exception",
    [
        (np.zeros((4, 4, 3), dtype=np.uint8), ValueError),
        (np.zeros((0, 4), dtype=np.uint8), ValueError),
        (np.full((4, 4), np.nan, dtype=np.float32), ValueError),
        (np.zeros((4, 4), dtype=np.int32), TypeError),
    ],
)
def test_create_mask_from_array_rejects(array, exception) -> None:  # type: ignore[no-untyped-def]
    layer = _layer()
    with pytest.raises(exception):
        layer.create_mask_from_array(array)
    assert not layer.has_mask()


def test_psdimage_fromarray_bitmap_defaults_to_depth_one() -> None:
    psd = PSDImage.fromarray(np.eye(4, 6, dtype=np.float32), mode="1")
    assert psd.depth == 1
    np.testing.assert_array_equal(psd.toarray()[:, :, 0], np.eye(4, 6))


def test_psdimage_fromarray_32bit_carries_hdrt_block() -> None:
    psd = PSDImage.fromarray(FINE[:, :, :3])
    assert psd._record.color_mode_data.value


def test_psdimage_fromarray_rejects_oversized_width() -> None:
    with pytest.raises(ValueError, match="Width too large"):
        PSDImage.fromarray(np.zeros((1, 300001), dtype=np.uint8))


def test_update_mask_from_array_error_leaves_mask_unchanged() -> None:
    layer = _layer()
    layer.create_mask_from_array(MASK)
    before = layer.toarray("mask", real_mask=False)
    with pytest.raises(ValueError):
        layer.update_mask_from_array(np.zeros((4, 4, 3), dtype=np.uint8))
    after = layer.toarray("mask", real_mask=False)
    assert before is not None and after is not None
    np.testing.assert_array_equal(before, after)
