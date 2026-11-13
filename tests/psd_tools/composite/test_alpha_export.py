import sys
from typing import Literal

import numpy as np
import pytest
from PIL import Image, ImageCms

from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import Resource
from psd_tools.psd.image_resources import ImageResource

pytest.importorskip("aggdraw")
pytest.importorskip("scipy")

from psd_tools.composite import composite

composite_module = sys.modules["psd_tools.composite.composite"]


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("apply_icc", [False, True])
@pytest.mark.parametrize("viewport", [None, (1, 0, 3, 1)])
def test_opaque_union_export(
    force: bool, apply_icc: bool, viewport: tuple[int, int, int, int] | None
) -> None:
    psd = PSDImage.new("RGB", (2, 1))
    psd.create_pixel_layer(Image.new("RGBA", psd.size, (31, 99, 201, 255)))
    psd.create_pixel_layer(Image.new("RGBA", psd.size, (17, 69, 123, 128)))
    psd.image_resources[Resource.ICC_PROFILE] = ImageResource(
        key=Resource.ICC_PROFILE,
        data=ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes(),
    )
    color, _, alpha = composite(psd, force=force, viewport=viewport)
    np.testing.assert_array_equal(
        alpha[0, 0], np.nextafter(np.float32(1), np.float32(0))
    )

    image = psd.composite(
        force=force, ignore_preview=True, apply_icc=apply_icc, viewport=viewport
    )
    assert image.mode == "RGBA"
    assert image.getpixel((0, 0)) == (23, 83, 161, 255)
    np.testing.assert_array_equal(
        np.asarray(image)[:, :, :3], (255 * color).astype(np.uint8)
    )
    if viewport is not None:
        assert image.getpixel((1, 0)) == (255, 255, 255, 0)
    else:
        assert image.getpixel((1, 0)) == (23, 83, 161, 255)


@pytest.mark.parametrize("force", [False, True])
def test_export_preserves_every_byte_alpha(force: bool) -> None:
    pixels = np.zeros((1, 256, 4), dtype=np.uint8)
    pixels[:, :, :3] = (17, 69, 123)
    pixels[:, :, 3] = np.arange(256, dtype=np.uint8)
    psd = PSDImage.new("RGBA", (256, 1))
    psd.create_pixel_layer(Image.fromarray(pixels))

    image = psd.composite(force=force, ignore_preview=True, apply_icc=False)
    color, _, _ = composite(psd, force=force)
    np.testing.assert_array_equal(np.asarray(image)[:, :, 3], pixels[:, :, 3])
    np.testing.assert_array_equal(
        np.asarray(image)[:, :, :3], (255 * color).astype(np.uint8)
    )


@pytest.mark.parametrize("force", [False, True])
def test_near_opaque_union_keeps_transparency(force: bool) -> None:
    psd = PSDImage.new("RGB", (1, 1))
    for _ in range(2):
        psd.create_pixel_layer(Image.new("RGBA", psd.size, (0, 0, 0, 254)))
    _, _, alpha = composite(psd, force=force)
    assert 254 / 255 < alpha[0, 0, 0] < 1 - np.finfo(np.float32).eps
    image = psd.composite(ignore_preview=True, force=force, apply_icc=False)
    assert image.getpixel((0, 0)) == (0, 0, 0, 254)


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize(
    "mode, depth", [("RGB", 8), ("RGB", 16), ("RGB", 32), ("L", 8)]
)
def test_export_alpha_endpoint_tolerance(
    monkeypatch: pytest.MonkeyPatch,
    force: bool,
    mode: str,
    depth: Literal[8, 16, 32],
) -> None:
    epsilon = np.finfo(np.float32).eps
    threshold = np.float32(1 - epsilon)
    alpha = np.array(
        [
            0,
            0.5,
            254 / 255,
            np.nextafter(threshold, np.float32(0)),
            threshold,
            np.nextafter(np.float32(1), np.float32(0)),
            1,
        ],
        dtype=np.float32,
    ).reshape(1, -1, 1)
    channels = 3 if mode == "RGB" else 1
    color = np.broadcast_to(alpha, (1, alpha.size, channels)).copy()
    original_alpha = alpha.copy()
    original_color = color.copy()
    psd = PSDImage.new(mode, (alpha.size, 1), depth=depth)

    def rendered(
        *args: object, **kwargs: object
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return color, alpha, alpha

    monkeypatch.setattr(composite_module, "composite", rendered)
    image = psd.composite(ignore_preview=True, force=force, apply_icc=False)
    expected_alpha = (255 * alpha[:, :, 0]).astype(np.uint8)
    if mode == "RGB" and depth == 8:
        expected_alpha[:, 4:] = 255
    np.testing.assert_array_equal(np.asarray(image)[:, :, -1], expected_alpha)
    np.testing.assert_array_equal(
        np.asarray(image)[:, :, :-1], (255 * color).astype(np.uint8)
    )
    np.testing.assert_array_equal(alpha, original_alpha)
    np.testing.assert_array_equal(color, original_color)


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("backdrop", ["transparent", "opaque", "array"])
def test_opaque_union_export_backdrop(force: bool, backdrop: str) -> None:
    psd = PSDImage.new("RGB", (2, 1))
    psd.create_pixel_layer(Image.new("RGBA", psd.size, (31, 99, 201, 255)))
    psd.create_pixel_layer(Image.new("RGBA", psd.size, (17, 69, 123, 128)))
    alpha: float | np.ndarray
    if backdrop == "array":
        alpha = np.array([[[0.0], [1.0]]], dtype=np.float32)
    else:
        alpha = 1.0 if backdrop == "opaque" else 0.0
    color = np.full((1, 2, 3), 0.5, dtype=np.float32)
    original_alpha = np.array(alpha, copy=True)
    original_color = color.copy()
    image = psd.composite(
        color=color, alpha=alpha, ignore_preview=True, force=force, apply_icc=False
    )
    assert image.mode == ("RGB" if backdrop == "opaque" and not force else "RGBA")
    np.testing.assert_array_equal(
        np.asarray(image.convert("RGB")), np.array([[[23, 83, 161]] * 2])
    )
    if image.mode == "RGBA":
        np.testing.assert_array_equal(np.asarray(image)[:, :, 3], 255)
    np.testing.assert_array_equal(alpha, original_alpha)
    np.testing.assert_array_equal(color, original_color)
