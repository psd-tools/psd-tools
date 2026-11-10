"""Clipping fixtures: Copyright (c) 2026 PSD fixture contributors.

The repository's MIT LICENSE applies to these self-authored fixtures.
"""

import copy
from typing import Literal

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("aggdraw")
pytest.importorskip("scipy")

from psd_tools.api.layers import Group, PixelLayer
from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import BlendMode, Tag
from psd_tools.psd.descriptor import Bool, Descriptor, Double, Enumerated, List
from psd_tools.terminology import Enum, Key

from ..utils import full_name

pytestmark = pytest.mark.parametrize("force", [False, True])


@pytest.fixture
def psd() -> PSDImage:
    return PSDImage.open(full_name("clipping-order/clipping-interior-independent.psd"))


def render(psd: PSDImage, force: bool) -> np.ndarray:
    image = psd.composite(ignore_preview=True, force=force, apply_icc=False)
    assert image is not None
    return np.asarray(image.convert("RGBA"))


def assert_existing_order(psd: PSDImage, force: bool) -> None:
    actual = render(psd, force)
    psd[0].tagged_blocks.set_data(Tag.BLEND_INTERIOR_ELEMENTS, 0)
    np.testing.assert_array_equal(actual, render(psd, force))


@pytest.mark.parametrize(
    "filename",
    [
        "clipping-independent.psd",
        "clipping-grouped.psd",
        "clipping-interior-independent.psd",
        "clipping-interior-grouped.psd",
        "clipping-overlay-disabled.psd",
    ],
)
def test_photoshop_clipping_order(filename: str, force: bool) -> None:
    psd = PSDImage.open(full_name("clipping-order/" + filename))
    # These merged previews contain the independently exported Photoshop pixels.
    expected = psd.topil(apply_icc=False)
    assert expected is not None
    np.testing.assert_array_equal(render(psd, force), expected.convert("RGBA"))


@pytest.mark.parametrize(
    "tag", [Tag.BLEND_INTERIOR_ELEMENTS, Tag.BLEND_CLIPPING_ELEMENTS]
)
@pytest.mark.parametrize("value", [None, 2])
def test_explicit_flags(
    psd: PSDImage, force: bool, tag: Tag, value: int | None
) -> None:
    if value is None:
        del psd[0].tagged_blocks[tag]
    else:
        psd[0].tagged_blocks.set_data(tag, value)
    assert_existing_order(psd, force)


@pytest.mark.parametrize("master", [False, True])
def test_disabled_effects(psd: PSDImage, force: bool, master: bool) -> None:
    expected = render(psd, force)
    data = psd[0].tagged_blocks.get_data(Tag.OBJECT_BASED_EFFECTS_LAYER_INFO)
    (data if master else data[b"SoFi"])[
        b"masterFXSwitch" if master else Key.Enabled
    ] = Bool(False)
    np.testing.assert_array_equal(render(psd, force), expected)


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize(
    "property,value",
    [("opacity", 128), ("fill_opacity", 128), ("blend_mode", BlendMode.MULTIPLY)],
)
def test_blending_options(
    psd: PSDImage, force: bool, index: int, property: str, value: int | BlendMode
) -> None:
    setattr(psd[index], property, value)
    assert_existing_order(psd, force)


@pytest.mark.parametrize("index", [0, 1])
def test_masks(psd: PSDImage, force: bool, index: int) -> None:
    psd[index].create_mask(Image.new("L", psd[index].size, 128))
    assert_existing_order(psd, force)


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize(
    "tag,value",
    [(Tag.KNOCKOUT_SETTING, 1), (Tag.CHANNEL_BLENDING_RESTRICTIONS_SETTING, [0])],
)
def test_advanced_blending(
    psd: PSDImage, force: bool, index: int, tag: Tag, value: int | list[int]
) -> None:
    psd[index].tagged_blocks.set_data(tag, value)
    assert_existing_order(psd, force)


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("channel", [False, True])
def test_blend_if(psd: PSDImage, force: bool, index: int, channel: bool) -> None:
    ranges = psd[index]._record.blending_ranges
    target = ranges.channel_ranges[0] if channel else ranges.composite_ranges
    target[0] = (0, 32768)
    assert_existing_order(psd, force)


@pytest.mark.parametrize(
    "key,value",
    [
        (Key.Mode, Enumerated(typeID=b"BlnM", enum=Enum.Multiply.value)),
        (Key.Opacity, Double(50)),
    ],
)
def test_overlay_blending(
    psd: PSDImage, force: bool, key: Key, value: Enumerated | Double
) -> None:
    psd[0].effects[0].descriptor[key] = value
    assert_existing_order(psd, force)


@pytest.mark.parametrize("index", [0, 1])
def test_additional_effects(psd: PSDImage, force: bool, index: int) -> None:
    data = psd[0].tagged_blocks.get_data(Tag.OBJECT_BASED_EFFECTS_LAYER_INFO)
    if index == 0:
        data[b"solidFillMulti"] = List([data[b"SoFi"], copy.deepcopy(data[b"SoFi"])])
        del data[b"SoFi"]
    else:
        psd[1].tagged_blocks.set_data(
            Tag.OBJECT_BASED_EFFECTS_LAYER_INFO, copy.deepcopy(data)
        )
    assert_existing_order(psd, force)


@pytest.mark.parametrize("key", [Key.Mode, Key.Opacity, Key.Color])
def test_overlay_defaults(psd: PSDImage, force: bool, key: Key) -> None:
    expected = render(psd, force)
    del psd[0].effects[0].descriptor[key]
    np.testing.assert_array_equal(render(psd, force), expected)


@pytest.mark.parametrize("index", [0, 1])
def test_ignored_effects(psd: PSDImage, force: bool, index: int) -> None:
    expected = render(psd, force)
    data = copy.deepcopy(
        psd[0].tagged_blocks.get_data(Tag.OBJECT_BASED_EFFECTS_LAYER_INFO)
    )
    if index == 1:
        data[b"masterFXSwitch"] = Bool(False)
    other = Descriptor(classID=b"unknown")
    other[b"present"] = other[Key.Enabled] = Bool(True)
    data[b"extra"] = other
    psd[index].tagged_blocks.set_data(Tag.OBJECT_BASED_EFFECTS_LAYER_INFO, data)
    np.testing.assert_array_equal(render(psd, force), expected)


@pytest.mark.parametrize("blend_mode", [BlendMode.NORMAL, BlendMode.PASS_THROUGH])
def test_grouped_pair(psd: PSDImage, force: bool, blend_mode: BlendMode) -> None:
    expected = render(psd, force)
    group = Group.new(psd)
    group.blend_mode = blend_mode
    group.extend(list(psd)[:2])
    np.testing.assert_array_equal(render(psd, force), expected)


def test_multiple_clips(psd: PSDImage, force: bool) -> None:
    expected = render(psd, force).copy()
    clip = PixelLayer.frompil(Image.new("RGB", (16, 16), "blue"), psd, left=16, top=16)
    clip.clipping = True
    expected[16:32, 16:32] = [0, 0, 255, 255]
    np.testing.assert_array_equal(render(psd, force), expected)


@pytest.mark.parametrize("mode", ["RGB", "L", "CMYK", "LAB"])
@pytest.mark.parametrize("depth", [8, 16, 32])
def test_pixel_formats(
    psd: PSDImage, force: bool, mode: str, depth: Literal[8, 16, 32]
) -> None:
    document = PSDImage.new(mode, (8, 8), depth=depth)
    base = PixelLayer.frompil(Image.new(mode, (4, 4), 32), document, left=2, top=2)
    clip = PixelLayer.frompil(Image.new(mode, (2, 2), 96), document, left=3, top=3)
    clip.clipping = True
    clipped = render(document, force)
    for tag in (
        Tag.OBJECT_BASED_EFFECTS_LAYER_INFO,
        Tag.BLEND_INTERIOR_ELEMENTS,
        Tag.BLEND_CLIPPING_ELEMENTS,
    ):
        base.tagged_blocks[tag] = copy.deepcopy(psd[0].tagged_blocks[tag])
    clip.visible = False
    expected = render(document, force).copy()
    clip.visible = True
    expected[3:5, 3:5] = clipped[3:5, 3:5]
    np.testing.assert_array_equal(render(document, force), expected)


@pytest.mark.parametrize("index", [0, 1])
def test_partial_alpha(psd: PSDImage, force: bool, index: int) -> None:
    original = psd[index]
    image = original.topil()
    assert image is not None
    image.putalpha(128)
    layer = PixelLayer.frompil(image, psd, left=8, top=8)
    layer.tagged_blocks.update(copy.deepcopy(original.tagged_blocks))
    psd.remove(layer)
    psd[index] = layer
    layer.clipping = index == 1
    assert_existing_order(psd, force)


def test_filter_and_hidden_clip(psd: PSDImage, force: bool) -> None:
    expected = render(psd, force)
    psd[1].visible = False
    np.testing.assert_array_equal(
        render(psd, force)[8:56, 8:56], np.broadcast_to([192, 48, 48, 255], (48, 48, 4))
    )
    image = psd.composite(
        ignore_preview=True,
        force=force,
        apply_icc=False,
        layer_filter=lambda layer: True,
    )
    assert image is not None
    np.testing.assert_array_equal(image.convert("RGBA"), expected)
