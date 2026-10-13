"""``create_pixel_layer_from_array`` keeps a deep document's own precision (#871)."""

from pathlib import Path
from typing import Any, Literal

import numpy as np
import pytest

from psd_tools.api.layers import PixelLayer
from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import BlendMode, Compression

DEPTHS: tuple[Literal[8, 16, 32], ...] = (8, 16, 32)

# Values no 8-bit step can hold at depth 16, so a layer narrowed on the way
# through reads back different.
FINE = ((np.arange(3 * 5 * 3).reshape(3, 5, 3) * 1237 + 11) % 65535) / 65535.0
FINE = FINE.astype(np.float32)
ALPHA = (((np.arange(3 * 5).reshape(3, 5) * 977 + 5) % 65535) / 65535.0).astype(
    np.float32
)


def _document(mode: str, depth: Literal[8, 16, 32]) -> PSDImage:
    return PSDImage.new(mode, (8, 8), depth=depth)


@pytest.mark.parametrize("depth", [16, 32])
def test_precision_beyond_eight_bits_is_kept(depth: Literal[16, 32]) -> None:
    psd = _document("RGB", depth)
    layer = psd.create_pixel_layer_from_array(FINE, compression=Compression.RAW)
    assert isinstance(layer, PixelLayer)
    out = layer.numpy("color")
    assert out is not None
    np.testing.assert_allclose(out, FINE, atol=1e-5)
    assert not np.allclose(out, np.rint(FINE * 255) / 255, atol=1e-4)


@pytest.mark.parametrize("depth", DEPTHS)
@pytest.mark.parametrize(
    "mode, planes", [("RGB", 3), ("CMYK", 4), ("L", 1), ("LAB", 3)]
)
def test_color_and_alpha_round_trip(
    mode: str, planes: int, depth: Literal[8, 16, 32]
) -> None:
    psd = _document(mode, depth)
    colors = np.stack([np.roll(FINE[:, :, 0], k, axis=1) for k in range(planes)], 2)
    array = np.dstack([colors, ALPHA])
    out = psd.create_pixel_layer_from_array(array).numpy()
    assert out is not None and out.shape == array.shape
    step = {8: 0.5 / 255, 16: 0.5 / 65535, 32: 1e-7}[depth]
    np.testing.assert_allclose(out, array, atol=step + 1e-7)


def test_missing_alpha_is_opaque() -> None:
    layer = _document("RGB", 16).create_pixel_layer_from_array(FINE)
    shape = layer.numpy("shape")
    assert shape is not None
    assert np.all(shape == 1.0)


def test_two_dimensional_array_is_one_channel() -> None:
    layer = _document("L", 16).create_pixel_layer_from_array(FINE[:, :, 0])
    out = layer.numpy("color")
    assert out is not None and out.shape == (3, 5, 1)


@pytest.mark.parametrize(
    "dtype, depth, maximum", [(np.uint16, 16, 65535), (np.uint8, 32, 255)]
)
def test_unsigned_integers_are_scaled_by_their_maximum(
    dtype: Any, depth: Literal[16, 32], maximum: int
) -> None:
    raw = ((np.arange(3 * 5 * 3).reshape(3, 5, 3) * 5 + 3) % maximum).astype(dtype)
    out = _document("RGB", depth).create_pixel_layer_from_array(raw).numpy("color")
    assert out is not None
    np.testing.assert_array_equal(np.rint(out * maximum).astype(dtype), raw)


def test_survives_save_and_reload(tmp_path: Path) -> None:
    psd = _document("RGB", 16)
    array = np.dstack([FINE, ALPHA])
    psd.create_pixel_layer_from_array(
        array, name="deep", top=2, left=1, opacity=128, blend_mode=BlendMode.MULTIPLY
    )
    path = tmp_path / "deep.psd"
    psd.save(path)
    layer = PSDImage.open(path)[0]
    assert (layer.name, layer.top, layer.left, layer.opacity) == ("deep", 2, 1, 128)
    assert layer.blend_mode == BlendMode.MULTIPLY
    out = layer.numpy()
    assert out is not None
    np.testing.assert_allclose(out, array, atol=1e-5)


def test_group_creation_appends_to_the_group() -> None:
    psd = _document("RGB", 16)
    group = psd.create_group(name="g")
    layer = group.create_pixel_layer_from_array(FINE)
    assert layer.parent is group and list(group) == [layer]


def test_rejects_wrong_channel_count() -> None:
    with pytest.raises(ValueError, match="channels"):
        _document("RGB", 16).create_pixel_layer_from_array(FINE[:, :, :2])


@pytest.mark.parametrize(
    "bad, error",
    [
        (np.full((3, 5, 3), np.nan, dtype=np.float32), ValueError),
        (np.zeros((0, 5, 3), dtype=np.float32), ValueError),
        (np.zeros((3, 5, 3), dtype=np.int32), TypeError),
        ([[0.0]], TypeError),
    ],
)
def test_rejects_unusable_arrays(bad: Any, error: type[Exception]) -> None:
    with pytest.raises(error):
        _document("RGB", 16).create_pixel_layer_from_array(bad)


def test_out_of_range_floats_saturate_below_depth_32() -> None:
    array = np.full((3, 5, 3), 1.2, dtype=np.float32)
    out = _document("RGB", 16).create_pixel_layer_from_array(array).numpy("color")
    assert out is not None and np.all(out == 1.0)
