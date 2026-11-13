from collections.abc import Sequence
from typing import Any, Literal

import numpy as np
import pytest
from PIL import Image

from psd_tools import PSDImage
from psd_tools.api.layers import AdjustmentLayer, Layer, PixelLayer
from psd_tools.composite import composite
from psd_tools.composite.composite import Compositor
from psd_tools.constants import BlendMode

from ..utils import full_name

# Clipping-alpha fixtures: Copyright (c) 2026 PSD fixture contributors.
# Distributed under the MIT permission and warranty terms in the root LICENSE.


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("ordinary_normal"),
        pytest.param("ordinary_passthrough"),
        pytest.param("nested_masked_inner_clip_normal"),
        pytest.param("nested_fill_inner_clip_normal"),
        pytest.param("pixel_base_mask_normal"),
        pytest.param("opaque_control_normal"),
    ],
)
@pytest.mark.parametrize("force", [False, True])
def test_clipping_alpha_photoshop(name: str, force: bool) -> None:
    psd = PSDImage.open(full_name(f"clipping-alpha/{name}.psd"))
    with Image.open(full_name(f"clipping-alpha/{name}.png")) as image:
        expected = np.asarray(image.convert("RGBA"), dtype=float)
    actual = np.asarray(
        psd.composite(ignore_preview=True, apply_icc=False, force=force), dtype=float
    )
    visible = expected[:, :, 3] > 0
    np.testing.assert_allclose(
        actual[:, :, :3][visible], expected[:, :, :3][visible], atol=1, rtol=0
    )
    np.testing.assert_allclose(actual[:, :, 3], expected[:, :, 3], atol=1, rtol=0)


@pytest.mark.parametrize("mode", ["L", "RGB"])
@pytest.mark.parametrize("depth", [8, 16, 32])
@pytest.mark.parametrize("blend", [BlendMode.NORMAL, BlendMode.MULTIPLY])
@pytest.mark.parametrize("force", [False, True])
def test_clipped_color_preserves_base_coverage(
    mode: str, depth: Literal[8, 16, 32], blend: BlendMode, force: bool
) -> None:
    psd = PSDImage.new(mode, (3, 2), depth=depth)
    channels = 1 if mode == "L" else 3
    pixels = np.full((2, 3, channels + 1), 160, dtype=np.uint8)
    pixels[:, :, -1] = [[0, 1, 128], [64, 192, 255]]
    base = PixelLayer.fromarray(pixels, psd)
    base.opacity = 192
    base.fill_opacity = 160
    base.create_mask(
        Image.fromarray(np.array([[255, 128, 255], [64, 255, 0]], dtype=np.uint8))
    )
    before = composite(psd, force=force)

    pixels[:, :, :-1] = 80
    pixels[:, :, -1] = [[255, 128, 0], [64, 192, 255]]
    clip = PixelLayer.fromarray(pixels, psd)
    clip.clipping = True
    clip.blend_mode = blend
    clip.opacity = 128
    clip.fill_opacity = 192
    clip.create_mask(Image.new("L", (3, 2), 128))
    color, shape, alpha = composite(psd, force=force)

    base_color = base.numpy("color")
    clip_color = clip.numpy("color")
    clip_shape = clip.numpy("shape")
    assert base_color is not None and clip_color is not None and clip_shape is not None
    coverage = clip_shape * (128 / 255) ** 2 * (192 / 255)
    blended = clip_color if blend == BlendMode.NORMAL else base_color * clip_color
    expected = base_color * (1 - coverage) + blended * coverage
    visible = alpha[:, :, 0] > 0
    np.testing.assert_allclose(color[visible], expected[visible], atol=2e-6, rtol=0)
    np.testing.assert_array_equal(shape, before[1])
    np.testing.assert_array_equal(alpha, before[2])


@pytest.mark.parametrize("force", [False, True])
def test_adjustment_clip_keeps_backdrop_alpha(
    force: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("scipy")
    psd = PSDImage.open(full_name("adjustments/adjustment_clipping.psd"))
    layer = next(
        node
        for node in psd.descendants()
        if isinstance(node, AdjustmentLayer) and node.has_clip_layers()
    )
    alpha = np.full((psd.height, psd.width, 1), 0.25, dtype=np.float32)
    compositor = Compositor(psd.bbox, np.repeat(alpha, 3, axis=2), alpha, force=force)
    original = compositor._apply_clip_layers
    seeds = []

    def apply_clips(
        clips: Sequence[Layer], color: np.ndarray, seed: np.ndarray, **kwargs: Any
    ) -> np.ndarray:
        seeds.append(seed.copy())
        return original(clips, color, seed, **kwargs)

    monkeypatch.setattr(compositor, "_apply_clip_layers", apply_clips)
    compositor.apply(layer)
    assert len(seeds) == 1
    np.testing.assert_array_equal(seeds[0], alpha)
