"""Synthetic RGB8 Color Dodge references rendered by Photoshop 27.4.0."""

import importlib
import io
from pathlib import Path
from typing import Any, TypedDict

import numpy as np
import pytest
from PIL import Image

from psd_tools.api.layers import PixelLayer
from psd_tools.api.psd_image import PSDImage
from psd_tools.composite import composite
from psd_tools.constants import BlendMode, ChannelID, Tag
from psd_tools.psd.layer_and_mask import LayerBlendingRanges

from ..utils import full_name

composite_module = importlib.import_module("psd_tools.composite.composite")


def make_document(
    fill: int = 204,
    flag: bool = True,
    opacity: int = 255,
    backdrop_alpha: int = 255,
    mask: bool = False,
    clipped: bool = False,
    clip_grouped: bool = True,
    base_mask: bool = False,
) -> PSDImage:
    palette = np.array(
        [
            (0, 0, 0),
            (255, 255, 255),
            (255, 0, 0),
            (0, 255, 0),
            (0, 0, 255),
            (255, 255, 0),
            (0, 255, 255),
            (255, 0, 255),
            (254, 255, 253),
            (1, 2, 3),
            (16, 64, 192),
            (128, 240, 32),
            (254, 1, 128),
            (64, 128, 240),
            (192, 32, 16),
            (253, 254, 255),
        ],
        dtype=np.uint8,
    )
    alpha = np.array([0, 1, 2, 16, 32, 64, 128, 255], dtype=np.uint8)
    base = np.empty((32, 32, 4), dtype=np.uint8)
    base[:, :, :3] = palette[np.arange(32) // 2][None, :, :]
    base[:, :, 3] = backdrop_alpha
    doc = PSDImage.new("RGB", (32, 32))
    bottom = PixelLayer.fromarray(base, doc, name="Synthetic RGB backdrop")
    bottom.tagged_blocks.set_data(Tag.BLEND_CLIPPING_ELEMENTS, int(clip_grouped))
    if base_mask:
        bottom.create_mask(
            Image.fromarray(np.broadcast_to(alpha[np.arange(32) % 8], (32, 32)).copy())
        )
    top = np.empty_like(base)
    top[:, :, :3] = palette[np.arange(32) // 2][:, None, :]
    top[:, :, 3] = alpha[np.arange(32) % 8]
    layer = PixelLayer.fromarray(top, doc, name="Synthetic RGB dodge")
    layer.blend_mode = BlendMode.COLOR_DODGE
    layer.fill_opacity = fill
    layer.opacity = opacity
    layer.clipping = clipped
    layer.tagged_blocks.set_data(Tag.TRANSPARENCY_SHAPES_LAYER, int(flag))
    if mask:
        layer.create_mask(
            Image.fromarray(
                np.broadcast_to(alpha[np.arange(32) % 8, None], (32, 32)).copy()
            )
        )
    return doc


class Options(TypedDict, total=False):
    fill: int
    opacity: int
    backdrop_alpha: int
    mask: bool
    clipped: bool
    clip_grouped: bool
    base_mask: bool


CASES: list[Any] = [
    ("fill0", {"fill": 0}),
    ("fill1", {"fill": 1}),
    ("fill2", {"fill": 2}),
    ("fill16", {"fill": 16}),
    ("fill128", {"fill": 128}),
    ("fill204", {"fill": 204}),
    ("fill254", {"fill": 254}),
    ("fill255", {"fill": 255}),
    ("opacity128", {"opacity": 128}),
    ("opacity1", {"opacity": 1}),
    ("masked", {"mask": True}),
    ("masked-opacity128", {"mask": True, "opacity": 128}),
    ("backdrop128", {"backdrop_alpha": 128}),
    ("backdrop0", {"backdrop_alpha": 0}),
    pytest.param("fill204", {"clipped": True}, id="clipped"),
    pytest.param(
        "fill204", {"clipped": True, "clip_grouped": False}, id="clipped-ungrouped"
    ),
    ("clipped-base-mask", {"clipped": True, "base_mask": True}),
]


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("flag", [False, True])
@pytest.mark.parametrize(("name", "options"), CASES)
def test_color_dodge_native(
    name: str, options: Options, flag: bool, force: bool
) -> None:
    doc = make_document(flag=flag, **options)
    reference_flag = False if name in ("fill0", "fill1") else flag
    path = full_name(
        f"color-dodge-fill/rgb-flag{int(reference_flag)}-{name}-reference.png"
    )
    with Image.open(path) as image:
        expected = np.asarray(image.convert("RGBA"), dtype=np.float32)
    rendered = doc.composite(ignore_preview=True, force=force, apply_icc=False)
    assert rendered is not None
    actual = np.asarray(rendered.convert("RGBA"), dtype=np.float32)
    # Photoshop can retain different RGB where alpha is zero.
    covered = (expected[:, :, 3] > 0) & (actual[:, :, 3] > 0)
    assert (
        np.max(np.abs(actual[:, :, :3] - expected[:, :, :3])[covered], initial=0) <= 2
    )
    assert np.max(np.abs(actual[:, :, 3] - expected[:, :, 3])) <= 1
    actual_alpha, expected_alpha = actual[:, :, 3:4] / 255, expected[:, :, 3:4] / 255
    for background in (0, 255):
        visible_actual = actual[:, :, :3] * actual_alpha + background * (
            1 - actual_alpha
        )
        visible_expected = expected[:, :, :3] * expected_alpha + background * (
            1 - expected_alpha
        )
        assert np.max(np.abs(visible_actual - visible_expected)) <= 2
    color, shape, alpha = composite(doc, force=force)
    assert np.isfinite(color).all()
    assert np.max(np.abs(alpha[:, :, 0] * 255 - expected[:, :, 3])) <= 1
    doc[-1].blend_mode = BlendMode.NORMAL
    _, normal_shape, normal_alpha = composite(doc, force=force)
    np.testing.assert_array_equal(alpha, normal_alpha)
    np.testing.assert_array_equal(shape, normal_shape)


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("flag", [False, True])
def test_nonbinary_clipping_base_remains_excluded(
    flag: bool, force: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    factors: list[object] = []
    original = composite_module._color_dodge_factor

    def spy(layer: Any, *args: Any) -> object:
        factor = original(layer, *args)
        if layer.blend_mode == BlendMode.COLOR_DODGE:
            factors.append(factor)
        return factor

    monkeypatch.setattr(composite_module, "_color_dodge_factor", spy)
    doc = make_document(flag=flag, clipped=True, backdrop_alpha=128)
    assert doc.composite(ignore_preview=True, force=force, apply_icc=False)
    assert factors == [None]


@pytest.mark.parametrize("force", [False, True])
def test_ignored_clip_layer_leaves_color_dodge_fill_unchanged(
    force: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = make_document()
    expected = doc.composite(ignore_preview=True, force=force, apply_icc=False)
    clip = PixelLayer.fromarray(
        np.full((32, 32, 4), 255, dtype=np.uint8), doc, name="Synthetic clip"
    )
    clip.clipping = True

    factors: list[object] = []
    original = composite_module._color_dodge_factor

    def spy(layer: Any, *args: Any) -> object:
        factor = original(layer, *args)
        if layer.blend_mode == BlendMode.COLOR_DODGE:
            factors.append(factor)
        return factor

    monkeypatch.setattr(composite_module, "_color_dodge_factor", spy)
    ignored = doc.composite(
        ignore_preview=True,
        force=force,
        apply_icc=False,
        layer_filter=lambda layer: layer is not clip,
    )
    assert factors[-1] is not None
    assert ignored is not None and expected is not None
    np.testing.assert_array_equal(np.asarray(ignored), np.asarray(expected))

    doc.composite(ignore_preview=True, force=force, apply_icc=False)
    assert factors[-1] is None


def test_clipping_base_shape_read_once_per_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = make_document(clipped=True)[0]
    reads = []
    original = base.numpy

    def counting(*args: Any, **kwargs: Any) -> Any:
        reads.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(base, "numpy", counting)
    compositor = composite_module.Compositor(
        (0, 0, 1, 1), np.zeros((1, 1, 3)), np.zeros((1, 1, 1)), clip_base=base
    )
    assert compositor._clip_base_has_binary_shape()
    assert compositor._clip_base_has_binary_shape()
    assert reads == [("shape",)]


def test_synthetic_roundtrip(tmp_path: Path) -> None:
    doc = make_document(flag=False, fill=1, mask=True, opacity=128)
    path = tmp_path / "dodge.psd"
    doc.save(path)
    loaded = PSDImage.open(path)
    assert loaded[-1].tagged_blocks.get_data(Tag.TRANSPARENCY_SHAPES_LAYER) == 0
    assert loaded[-1].fill_opacity == 1
    before = doc.composite(ignore_preview=True)
    after = loaded.composite(ignore_preview=True)
    np.testing.assert_array_equal(before, after)


def test_empty_blending_ranges_use_color_dodge_fill() -> None:
    doc = make_document()
    expected = doc.composite(ignore_preview=True, apply_icc=False)
    doc[-1]._record.blending_ranges = LayerBlendingRanges.read(
        io.BytesIO(b"\x00\x00\x00\x00")
    )
    actual = doc.composite(ignore_preview=True, apply_icc=False)
    np.testing.assert_array_equal(actual, expected)


def test_clipping_base_without_transparency_uses_color_dodge_fill() -> None:
    doc = make_document(clipped=True)
    expected = doc.composite(ignore_preview=True, apply_icc=False)
    base = doc[0]
    channels = [
        (info, data)
        for info, data in zip(base._record.channel_info, base._channels, strict=True)
        if info.id != ChannelID.TRANSPARENCY_MASK
    ]
    base._record.channel_info = type(base._record.channel_info)(
        info for info, _ in channels
    )
    base._channels = type(base._channels)(data for _, data in channels)
    assert base.numpy("shape") is None
    actual = doc.composite(ignore_preview=True, apply_icc=False)
    np.testing.assert_array_equal(actual, expected)
