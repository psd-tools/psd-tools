import logging
from pathlib import Path
from typing import Any, Optional, Tuple

import numpy as np
import pytest
from PIL import Image

from psd_tools.api.layers import (
    AdjustmentLayer,
    Artboard,
    Group,
    Layer,
    PixelLayer,
    ShapeLayer,
    SmartObjectLayer,
    TypeLayer,
)
from psd_tools.api.pil_io import get_pil_channels, get_pil_depth, post_process
from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import (
    BlendMode,
    ColorMode,
    CompatibilityMode,
    ProtectedFlags,
    SectionDivider,
    SheetColorType,
    Tag,
)

from psd_tools.psd.descriptor import Integer

from ..utils import full_name

logger = logging.getLogger(__name__)


@pytest.fixture
def pixel_layer() -> PixelLayer:
    return PSDImage.open(full_name("layers/pixel-layer.psd"))[0]  # type: ignore[return-value]


@pytest.fixture
def adjustment_layer() -> AdjustmentLayer:
    return PSDImage.open(full_name("layers/brightness-contrast.psd"))[0]  # type: ignore[return-value]


@pytest.fixture
def fill_layer() -> AdjustmentLayer:
    return PSDImage.open(full_name("layers/solid-color-fill.psd"))[0]  # type: ignore[return-value]


@pytest.fixture
def shape_layer() -> ShapeLayer:
    return PSDImage.open(full_name("layers/shape-layer.psd"))[0]  # type: ignore[return-value]


@pytest.fixture
def smartobject_layer() -> SmartObjectLayer:
    return PSDImage.open(full_name("layers/smartobject-layer.psd"))[0]  # type: ignore[return-value]


@pytest.fixture
def type_layer() -> TypeLayer:
    return PSDImage.open(full_name("layers/type-layer.psd"))[0]  # type: ignore[return-value]


@pytest.fixture
def group() -> Group:
    return PSDImage.open(full_name("layers/group.psd"))[0]  # type: ignore[return-value]


ALL_FIXTURES = [
    "pixel_layer",
    "shape_layer",
    "smartobject_layer",
    "type_layer",
    "group",
    "adjustment_layer",
    "fill_layer",
]


def test_pixel_layer_properties(pixel_layer: PixelLayer) -> None:
    layer = pixel_layer
    assert layer.name == "Pixel", "layer.name = %s" % type(layer.name)
    assert layer.kind == "pixel"
    assert layer.visible is True
    assert layer.opacity == 255
    assert isinstance(layer.parent, PSDImage)
    assert isinstance(layer.blend_mode, BlendMode)
    assert layer.left == 1
    assert layer.top == 1
    assert layer.right == 30
    assert layer.bottom == 30
    assert layer.width == 29
    assert layer.height == 29
    assert layer.size == (29, 29)
    assert layer.bbox == (1, 1, 30, 30)
    assert layer.clipping is False
    assert layer.tagged_blocks is not None
    assert layer.layer_id == 3


def test_pixel_layer_writable_properties(pixel_layer: PixelLayer) -> None:
    layer = pixel_layer
    layer.name = "foo"
    assert layer.name == "foo"
    layer._record.tobytes()
    layer.name = "👽"
    assert layer.name == "👽"
    layer._record.tobytes()

    layer.visible = False
    assert layer.visible is False

    layer.opacity = 128
    assert layer.opacity == 128

    layer.blend_mode = BlendMode.LINEAR_DODGE
    assert layer.blend_mode == BlendMode.LINEAR_DODGE

    layer.left = 2
    assert layer.left == 2
    layer.top = 2
    assert layer.top == 2
    assert layer.size == (29, 29)

    layer.offset = (1, 1)
    assert layer.offset == (1, 1)
    assert layer.size == (29, 29)

    layer.clipping = True
    assert layer.clipping is True


def test_layer_is_visible(pixel_layer: PixelLayer) -> None:
    assert pixel_layer.is_visible()


@pytest.fixture(params=["pixel_layer", "group"])
def is_group_args(request: Any) -> Tuple[Any, Optional[bool]]:
    return (
        request.getfixturevalue(request.param),
        {"pixel_layer": False, "group": True}.get(request.param),
    )


def test_layer_is_group(is_group_args: Tuple[Any, bool]) -> None:
    layer, expected = is_group_args
    assert layer.is_group() == expected


def test_layer_has_mask(pixel_layer: PixelLayer) -> None:
    assert pixel_layer.has_mask() is False


@pytest.fixture(params=ALL_FIXTURES)
def kind_args(request: Any) -> Tuple[Any, str]:
    expected = request.param.replace("_layer", "")
    expected = expected.replace("fill", "solidcolorfill")
    expected = expected.replace("adjustment", "brightnesscontrast")
    return (request.getfixturevalue(request.param), expected)


def test_layer_kind(kind_args: Tuple[Any, str]) -> None:
    layer, expected = kind_args
    assert layer.kind == expected


def test_curves_with_vectormask() -> None:
    layer = PSDImage.open(full_name("layers/curves-with-vectormask.psd"))[0]
    assert layer.kind == "curves"


@pytest.fixture(params=ALL_FIXTURES)
def topil_args(request: Any) -> Tuple[Any, bool]:
    is_image = request.param in {
        "pixel_layer",
        "smartobject_layer",
        "type_layer",
        "fill_layer",
        "shape_layer",
    }
    return (request.getfixturevalue(request.param), is_image)


def test_topil(topil_args: Tuple[Any, bool]) -> None:
    fixture, is_image = topil_args
    image = fixture.topil()

    channel_ids = [c.id for c in fixture._record.channel_info if c.id >= -1]
    for channel in channel_ids:
        fixture.topil(channel)

    assert isinstance(image, Image.Image) if is_image else image is None


def test_clip_adjustment() -> None:
    psd = PSDImage.open(full_name("clip-adjustment.psd"))
    assert len(psd) == 2
    layer = psd[0]
    assert layer.kind == "type"
    assert len(layer.clip_layers) == 1


def test_nested_clipping() -> None:
    """Check if the nested clipping layers are correctly identified.

    Structure of the PSD file `clipping-mask.psd` is as follows:

        PSDImage(mode=3 size=360x200 depth=8 channels=3)
        [0] PixelLayer('Background' size=360x200)
        [1] Group('Group 2' size=238x219)
          [0] Group('Group 1' size=185x219)
            [0] PixelLayer('Shape 3' size=185x72)
            [1] ShapeLayer('Shape 4' size=157x160)
          [1] ShapeLayer('Shape 1' size=124x69)
          [2] +ShapeLayer('Shape 2' size=69x75 clip)
    """
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    psd.compatibility_mode = CompatibilityMode.CLIP_STUDIO_PAINT
    psd[1].blend_mode = BlendMode.NORMAL
    psd[1].clipping = True
    assert psd[1].clipping is True
    group_1 = psd[1]
    assert isinstance(group_1, Group)
    assert group_1[1].has_clip_layers()
    assert group_1[2].clipping
    assert psd[0].has_clip_layers()


def test_clip_stack() -> None:
    """Check if consecutive clipping layers are correctly identified."""
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    group_1 = psd[1]
    assert isinstance(group_1, Group)
    group_1[1].clipping = True
    assert group_1[0].has_clip_layers()
    assert group_1[1].clipping
    assert group_1[2].clipping
    assert not group_1[1].has_clip_layers()
    assert not group_1[2].has_clip_layers()


def test_type_layer(type_layer: TypeLayer) -> None:
    assert type_layer.text == "A"
    assert type_layer.transform == (
        1.0000000000000002,
        0.0,
        0.0,
        1.0,
        0.0,
        4.978787878787878,
    )
    assert type_layer.engine_dict
    assert type_layer.resource_dict
    assert type_layer.document_resources
    assert type_layer.warp


def test_group_writable_properties(group: Group) -> None:
    assert group.blend_mode == BlendMode.PASS_THROUGH
    group.blend_mode = BlendMode.SCREEN
    assert group.blend_mode == BlendMode.SCREEN


def test_group_extract_bbox() -> None:
    psd = PSDImage.open(full_name("hidden-groups.psd"))
    assert Group.extract_bbox(list(psd)[1:], False) == (40, 72, 83, 134)
    assert Group.extract_bbox(list(psd)[1:], True) == (25, 34, 83, 134)
    group_1 = psd[1]
    assert isinstance(group_1, Group)
    with pytest.raises(TypeError):
        Group.extract_bbox(group_1[0])  # type: ignore[arg-type]


def test_group_blend_mode() -> None:
    psd = PSDImage.open(full_name("blend-modes/group-divider-blend-mode.psd"))
    assert psd[0].blend_mode is not None
    blend_mode = psd[0].blend_mode
    psd[0].blend_mode = BlendMode.NORMAL
    assert psd[0].blend_mode == BlendMode.NORMAL
    psd[0].blend_mode = blend_mode
    assert psd[0].blend_mode == blend_mode


def test_sibling_layers() -> None:
    psd = PSDImage.open(full_name("hidden-groups.psd"))
    assert psd[0].next_sibling() is psd[1]
    assert psd[1].previous_sibling() is psd[0]
    assert psd[0].next_sibling(visible=True) is psd[2]
    assert psd[2].previous_sibling(visible=True) is psd[0]
    group_1 = psd[1]
    assert isinstance(group_1, Group)
    assert group_1[0].next_sibling() is None
    assert group_1[0].previous_sibling() is None


def test_shape_and_fill_layer() -> None:
    psd = PSDImage.open(full_name("vector-mask2.psd"))
    for i in range(8):
        assert isinstance(psd[i], ShapeLayer)
    for i in range(8, 10):
        assert isinstance(psd[i], PixelLayer)


def test_has_effects() -> None:
    """Both arms over a file whose three effect layers differ only in state.

    Every layer but the background holds one *listed* ``ColorOverlay``, so
    ``enabled=False`` stays True throughout: layer 1 draws it, layer 2 has it
    switched off, and layer 3 has the master switch off. That is the
    distinction ``has_effects()`` reports -- what the fx list shows, against
    what is drawn -- and not whether an effects block exists (#830).
    """
    psd = PSDImage.open(full_name("effects/effects-enabled.psd"))
    assert not psd[0].has_effects()
    # No block at all: both arms say no, which is the branch that used to be
    # a tagged-block scan ahead of everything else.
    assert not psd[0].has_effects(enabled=False)
    assert psd[1].has_effects()
    assert psd[1].has_effects(name="ColorOverlay")
    assert not psd[1].has_effects(name="DropShadow")
    assert not psd[2].has_effects()
    assert psd[2].has_effects(enabled=False)
    assert not psd[3].has_effects()
    assert psd[3].has_effects(enabled=False)
    assert psd[3].has_effects(enabled=False, name="ColorOverlay")
    assert not psd[3].has_effects(enabled=False, name="DropShadow")


def test_bbox_updates() -> None:
    psd = PSDImage.open(full_name("hidden-groups.psd"))
    group1 = psd[1]
    group1.visible = False
    assert group1.bbox == (0, 0, 0, 0)
    group1.visible = True
    assert group1.bbox == (25, 34, 80, 88)


def test_extract_bbox_excludes_clipping() -> None:
    """Clipping layers should be excluded from bbox by default (issue #547)."""
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    group2 = psd[1]
    assert isinstance(group2, Group)
    shape1 = group2[1]  # Shape 1, clipping=False, bbox=(50, 44, 174, 113)
    shape2 = group2[2]  # Shape 2, clipping=True,  bbox=(141, 17, 210, 92)

    # With include_clipping=True (old behavior): Shape 2 extends the top and right bounds
    assert Group.extract_bbox([shape1, shape2], include_clipping=True) == (
        50,
        17,
        210,
        113,
    )

    # Default (include_clipping=False, new behavior): only shape1 contributes
    assert Group.extract_bbox([shape1, shape2]) == (50, 44, 174, 113)
    assert Group.extract_bbox([shape1, shape2], include_clipping=False) == (
        50,
        44,
        174,
        113,
    )


def test_bbox_invalidated_on_clipping_change() -> None:
    """Changing a layer's clipping flag should invalidate the parent group's bbox cache."""
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    group2 = psd[1]
    assert isinstance(group2, Group)
    initial_bbox = group2.bbox

    # Make Shape 1 a clipping layer; it should be excluded from group bbox
    group2[1].clipping = True
    assert group2._bbox is None  # cache was invalidated

    # Restore and confirm the bbox is recomputed to original value
    group2[1].clipping = False
    assert group2.bbox == initial_bbox


def test_new_group(group: Group) -> None:
    test_group = Group.new(group, "Test Group")
    assert test_group._parent is group
    assert (
        test_group._record.tagged_blocks.get_data(Tag.SECTION_DIVIDER_SETTING).kind
        is SectionDivider.OPEN_FOLDER
    )
    assert test_group._bounding_record is not None
    assert (
        test_group._bounding_record.tagged_blocks.get_data(
            Tag.SECTION_DIVIDER_SETTING
        ).kind
        is SectionDivider.BOUNDING_SECTION_DIVIDER
    )
    assert (
        test_group._record.tagged_blocks.get_data(Tag.UNICODE_LAYER_NAME)
        == "Test Group"
    )
    assert (
        test_group._bounding_record.tagged_blocks.get_data(Tag.UNICODE_LAYER_NAME)
        == "</Layer group>"
    )


def test_group_layers(
    pixel_layer: PixelLayer,
    smartobject_layer: SmartObjectLayer,
    fill_layer: AdjustmentLayer,
    adjustment_layer: AdjustmentLayer,
) -> None:
    psdimage = pixel_layer._psd
    test_group = Group.group_layers(
        parent=psdimage,  # type: ignore[arg-type]
        layers=[pixel_layer, smartobject_layer, fill_layer, adjustment_layer],
    )
    assert len(test_group) == 4

    assert test_group[0] is pixel_layer
    assert test_group[1] is smartobject_layer
    assert test_group[2] is fill_layer
    assert test_group[3] is adjustment_layer

    for child in test_group:
        assert child in test_group
        assert child._parent is test_group
        assert child._psd is psdimage

    assert test_group._parent is psdimage
    assert test_group._psd is psdimage


@pytest.mark.parametrize(
    "mode",
    ["RGB", "RGBA", "L", "LA", "CMYK", "1", "LAB"],
)
def test_pixel_layer_frompil(mode: str) -> None:
    # Create a PixelLayer from a PIL image and verify channel data
    target_mode = "RGB"
    psdimage = PSDImage.new(mode=target_mode, size=(30, 30))
    original_image = Image.new(mode, (30, 30))
    layer = psdimage.create_pixel_layer(original_image, name="Test Layer")
    assert len(psdimage) == 1

    image = original_image.convert(psdimage.pil_mode)
    # Alpha-bearing modes automatically gain a mask channel.
    has_alpha = "A" in original_image.getbands()
    expected_channels = (
        get_pil_channels(image.mode.rstrip("A")) + 1 + (1 if has_alpha else 0)
    )
    assert len(layer._record.channel_info) == expected_channels
    assert len(layer._channels) == expected_channels
    assert layer.has_mask() == has_alpha

    for channel in range(get_pil_channels(image.mode.rstrip("A"))):
        assert (
            layer._channels[channel + 1].get_data(
                image.width, image.height, get_pil_depth(image.mode.rstrip("A"))
            )
            == image.getchannel(channel).tobytes()
        )


def test_create_mask() -> None:
    psdimage = PSDImage.new(mode="RGB", size=(30, 30))
    layer = psdimage.create_pixel_layer(Image.new("RGB", (30, 30)), name="Test Layer")
    assert not layer.has_mask()

    mask_img = Image.new("L", (30, 30), 128)
    mask = layer.create_mask(mask_img)

    assert layer.has_mask()
    assert mask.width == 30
    assert mask.height == 30
    mask_pil = mask.topil()
    assert mask_pil is not None
    assert mask_pil.tobytes() == mask_img.tobytes()


def test_create_mask_raises_if_already_has_mask() -> None:
    psdimage = PSDImage.new(mode="RGB", size=(30, 30))
    layer = psdimage.create_pixel_layer(Image.new("RGB", (30, 30)))
    layer.create_mask(Image.new("L", (30, 30), 255))
    with pytest.raises(ValueError, match="already has a mask"):
        layer.create_mask(Image.new("L", (30, 30), 0))


def test_create_mask_uses_alpha_channel() -> None:
    psdimage = PSDImage.new(mode="RGB", size=(30, 30))
    layer = psdimage.create_pixel_layer(Image.new("RGB", (30, 30)))
    rgba_img = Image.new("RGBA", (30, 30), (255, 0, 0, 64))
    layer.create_mask(rgba_img)

    assert layer.has_mask()
    assert layer.mask is not None
    mask_pil = layer.mask.topil()
    assert mask_pil is not None
    assert mask_pil.getpixel((0, 0)) == 64


def test_frompil_auto_mask_from_rgba() -> None:
    psdimage = PSDImage.new(mode="RGB", size=(30, 30))
    rgba_img = Image.new("RGBA", (30, 30), (255, 0, 0, 200))
    layer = psdimage.create_pixel_layer(rgba_img)

    assert layer.has_mask()
    assert layer.mask is not None
    mask_pil = layer.mask.topil()
    assert mask_pil is not None
    assert mask_pil.getpixel((0, 0)) == 200


def test_frompil_rgba_psd_no_mask() -> None:
    # Issue #607: RGBA-mode PSD should store alpha as transparency channel,
    # not as an extra USER_LAYER_MASK.
    psdimage = PSDImage.new(mode="RGBA", size=(4, 4))
    img = Image.new("RGBA", (4, 4), (255, 0, 0, 128))
    layer = psdimage.create_pixel_layer(img, name="draw")
    assert not layer.has_mask()
    # Alpha must be preserved in the layer's transparency channel.
    layer_pil = layer.topil()
    assert layer_pil is not None
    assert layer_pil.mode == "RGBA"
    assert layer_pil.getchannel("A").getpixel((0, 0)) == 128


def test_frompil_la_psd_no_mask() -> None:
    # Same check for LA-mode PSD.
    psdimage = PSDImage.new(mode="LA", size=(4, 4))
    img = Image.new("LA", (4, 4), (200, 128))
    layer = psdimage.create_pixel_layer(img, name="draw")
    assert not layer.has_mask()
    # Alpha must be preserved in the layer's transparency channel.
    layer_pil = layer.topil()
    assert layer_pil is not None
    assert layer_pil.mode == "LA"
    assert layer_pil.getchannel("A").getpixel((0, 0)) == 128


def test_create_mask_round_trip(tmp_path: Any) -> None:
    psdimage = PSDImage.new(mode="RGB", size=(30, 30))
    layer = psdimage.create_pixel_layer(Image.new("RGB", (30, 30)))
    mask_img = Image.new("L", (30, 30), 77)
    layer.create_mask(mask_img)

    out = tmp_path / "test_mask.psd"
    psdimage.save(str(out))

    psdimage2 = PSDImage.open(str(out))
    layer2 = psdimage2[0]
    assert layer2.has_mask()
    assert layer2.mask is not None
    mask_pil = layer2.mask.topil()
    assert mask_pil is not None
    assert mask_pil.tobytes() == mask_img.tobytes()


def test_remove_mask() -> None:
    psdimage = PSDImage.new(mode="RGB", size=(30, 30))
    layer = psdimage.create_pixel_layer(Image.new("RGB", (30, 30)))
    layer.create_mask(Image.new("L", (30, 30), 200))
    assert layer.has_mask()

    layer.remove_mask()

    assert not layer.has_mask()
    assert layer.mask is None


def test_remove_mask_raises_if_no_mask() -> None:
    psdimage = PSDImage.new(mode="RGB", size=(30, 30))
    layer = psdimage.create_pixel_layer(Image.new("RGB", (30, 30)))
    with pytest.raises(ValueError, match="does not have a mask"):
        layer.remove_mask()


def test_remove_mask_round_trip(tmp_path: Any) -> None:
    psdimage = PSDImage.new(mode="RGB", size=(30, 30))
    layer = psdimage.create_pixel_layer(Image.new("RGB", (30, 30)))
    layer.create_mask(Image.new("L", (30, 30), 200))
    layer.remove_mask()

    out = tmp_path / "test_remove_mask.psd"
    psdimage.save(str(out))

    psdimage2 = PSDImage.open(str(out))
    assert not psdimage2[0].has_mask()


def test_update_mask() -> None:
    psdimage = PSDImage.new(mode="RGB", size=(30, 30))
    layer = psdimage.create_pixel_layer(Image.new("RGB", (30, 30)))
    layer.create_mask(Image.new("L", (30, 30), 100))

    new_mask_img = Image.new("L", (30, 30), 200)
    mask = layer.update_mask(new_mask_img)

    assert layer.has_mask()
    mask_pil = mask.topil()
    assert mask_pil is not None
    assert mask_pil.tobytes() == new_mask_img.tobytes()


def test_update_mask_raises_if_no_mask() -> None:
    psdimage = PSDImage.new(mode="RGB", size=(30, 30))
    layer = psdimage.create_pixel_layer(Image.new("RGB", (30, 30)))
    with pytest.raises(ValueError, match="does not have a mask"):
        layer.update_mask(Image.new("L", (30, 30), 255))


def test_update_mask_changes_size() -> None:
    psdimage = PSDImage.new(mode="RGB", size=(40, 40))
    layer = psdimage.create_pixel_layer(Image.new("RGB", (40, 40)))
    layer.create_mask(Image.new("L", (40, 40), 100))

    small_mask = Image.new("L", (20, 15), 255)
    mask = layer.update_mask(small_mask, top=5, left=5)

    assert mask.width == 20
    assert mask.height == 15
    assert mask.top == 5
    assert mask.left == 5


def test_update_mask_round_trip(tmp_path: Any) -> None:
    psdimage = PSDImage.new(mode="RGB", size=(30, 30))
    layer = psdimage.create_pixel_layer(Image.new("RGB", (30, 30)))
    layer.create_mask(Image.new("L", (30, 30), 100))
    updated_mask = Image.new("L", (30, 30), 42)
    layer.update_mask(updated_mask)

    out = tmp_path / "test_update_mask.psd"
    psdimage.save(str(out))

    psdimage2 = PSDImage.open(str(out))
    layer2 = psdimage2[0]
    assert layer2.has_mask()
    assert layer2.mask is not None
    mask_pil = layer2.mask.topil()
    assert mask_pil is not None
    assert mask_pil.tobytes() == updated_mask.tobytes()


def test_layer_fill_opacity(pixel_layer: PixelLayer) -> None:
    assert pixel_layer.fill_opacity == 255

    pixel_layer.fill_opacity = 128
    assert pixel_layer.fill_opacity == 128

    pixel_layer.fill_opacity = 0
    assert pixel_layer.fill_opacity == 0


def test_layer_reference_point(pixel_layer: PixelLayer) -> None:
    assert pixel_layer.reference_point == (15.0, 15.0)

    pixel_layer.reference_point = (10.5, 20.5)
    assert pixel_layer.reference_point == (10.5, 20.5)

    with pytest.raises(ValueError, match=r".* sequence of two floats.*"):
        pixel_layer.reference_point = (10.5,)  # type: ignore[assignment]

    with pytest.raises(ValueError, match=r".* sequence of two floats.*"):
        pixel_layer.reference_point = (10.5, 20.5, 30.5)  # type: ignore[assignment]


def test_layer_sheet_color(pixel_layer: PixelLayer) -> None:
    assert pixel_layer.sheet_color == SheetColorType.NO_COLOR

    pixel_layer.sheet_color = SheetColorType.RED
    assert pixel_layer.sheet_color == SheetColorType.RED

    pixel_layer.sheet_color = SheetColorType.NO_COLOR
    assert pixel_layer.sheet_color == SheetColorType.NO_COLOR


def test_layer_move_up(
    group: Group,
    pixel_layer: PixelLayer,
    smartobject_layer: SmartObjectLayer,
    fill_layer: AdjustmentLayer,
    adjustment_layer: AdjustmentLayer,
) -> None:
    group.extend([pixel_layer])
    test_group = Group.group_layers(
        parent=group,
        layers=[smartobject_layer, fill_layer, adjustment_layer],
    )
    with pytest.raises(IndexError):
        test_group.move_up(1)
    assert test_group._parent is not None
    assert test_group._parent.index(test_group) == 1
    pixel_layer.move_up(1)
    assert test_group._parent.index(test_group) == 0

    smartobject_layer.move_up(1)
    assert test_group.index(fill_layer) == 0
    assert test_group.index(smartobject_layer) == 1
    assert test_group.index(adjustment_layer) == 2

    fill_layer.move_up(2)
    assert test_group.index(smartobject_layer) == 0
    assert test_group.index(adjustment_layer) == 1
    assert test_group.index(fill_layer) == 2


def test_layer_move_down(
    group: Group,
    pixel_layer: PixelLayer,
    smartobject_layer: SmartObjectLayer,
    fill_layer: AdjustmentLayer,
    adjustment_layer: AdjustmentLayer,
) -> None:
    group.extend([pixel_layer])
    test_group = Group.group_layers(
        parent=group,
        layers=[smartobject_layer, fill_layer, adjustment_layer],
    )
    with pytest.raises(IndexError):
        pixel_layer.move_down(1)
    assert test_group._parent is not None
    assert test_group._parent.index(test_group) == 1
    test_group.move_down(1)
    assert test_group._parent.index(test_group) == 0

    fill_layer.move_down(1)
    assert test_group.index(fill_layer) == 0
    assert test_group.index(smartobject_layer) == 1
    assert test_group.index(adjustment_layer) == 2

    adjustment_layer.move_down(2)
    assert test_group.index(adjustment_layer) == 0
    assert test_group.index(fill_layer) == 1
    assert test_group.index(smartobject_layer) == 2


def test_group_append(group: Group, pixel_layer: PixelLayer) -> None:
    group.append(pixel_layer)
    assert pixel_layer in group
    assert pixel_layer._parent is group
    assert pixel_layer._psd is group._psd


def test_group_extend(
    group: Group,
    pixel_layer: PixelLayer,
    type_layer: TypeLayer,
    smartobject_layer: SmartObjectLayer,
    fill_layer: AdjustmentLayer,
) -> None:
    group.extend([pixel_layer, type_layer, smartobject_layer, fill_layer])

    for layer in [pixel_layer, type_layer, smartobject_layer, fill_layer]:
        assert layer in group
        assert layer._parent is group
        assert layer._psd is group._psd


# ---------------------------------------------------------------------------
# extend() walks its argument once (#820)
#
# It used to walk it three times -- once to validate, once to detach each
# layer from its old parent, once to attach -- which broke three things its
# own docstring promises: a one-shot iterable added nothing, a live container
# lost layers or hung, and a layer named twice landed at two indices.
#
# The two halves of the fix are ``list(layers)`` and the de-duplication, and
# each has a case below that fails without it. The split is not the obvious
# one: the de-dup comprehension is itself a materialization whenever there is
# more than one element, so it alone repairs a *multi-layer* container. What
# needs ``list()`` on its own is a generator, and a container holding exactly
# one layer -- hence the ``size`` parametrization.
# ---------------------------------------------------------------------------


def test_group_extend_adds_a_repeated_layer_once(
    group: Group, pixel_layer: PixelLayer
) -> None:
    """A layer named twice in one call lands once, and stays removable."""
    group.extend([pixel_layer, pixel_layer])

    assert len(group) == 1
    assert group[0] is pixel_layer
    assert group.count(pixel_layer) == 1
    assert group.index(pixel_layer) == 0

    # The duplicate left one layer at two indices with a single ``_parent``,
    # so ``remove()`` dropped only the first of them and ``index()`` could
    # never name the second.
    group.remove(pixel_layer)
    assert pixel_layer not in group
    assert len(group) == 0


def test_group_extend_does_not_write_a_repeated_layer_twice(tmp_path: Any) -> None:
    """The duplicate reached the saved file, not just the in-memory list."""
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    layer_info = psd._record.layer_and_mask_information.layer_info
    assert layer_info is not None
    before = len(layer_info.layer_records)
    layer = psd[0]
    group = psd.create_group(name="G")
    group.extend([layer, layer])

    path = tmp_path / "duplicate.psd"
    psd.save(str(path))
    reopened = PSDImage.open(str(path))

    saved_info = reopened._record.layer_and_mask_information.layer_info
    assert saved_info is not None
    # The moved layer keeps its record; the group adds its own and the
    # bounding one that closes it. A second copy of the layer would be a
    # fourth.
    assert len(saved_info.layer_records) == before + 2
    reopened_group = reopened[-1]
    assert isinstance(reopened_group, Group)
    assert [child.name for child in reopened_group] == [layer.name]


def test_group_extend_keeps_the_last_mention_of_a_repeated_layer(
    group: Group, pixel_layer: PixelLayer, type_layer: TypeLayer
) -> None:
    """De-duplication leaves a layer where a loop of ``append()`` would."""
    group.extend([pixel_layer, type_layer, pixel_layer])
    assert list(group) == [type_layer, pixel_layer]

    # Same sequence, one ``append()`` at a time, onto a second group: the last
    # mention wins there because appending a layer the group already holds
    # moves it to the end. Keeping the *first* mention instead -- what
    # ``dict.fromkeys()`` gives -- would order these two differently.
    reference = PSDImage.open(full_name("layers/group.psd"))[0]
    assert isinstance(reference, Group)
    for layer in [pixel_layer, type_layer, pixel_layer]:
        reference.append(layer)

    assert list(reference) == [type_layer, pixel_layer]
    assert len(group) == 0  # The loop above moved them out.


def test_group_extend_accepts_a_one_shot_iterable(
    group: Group, pixel_layer: PixelLayer, type_layer: TypeLayer
) -> None:
    """A generator used to add nothing: the checks drained it first."""
    group.extend(layer for layer in [pixel_layer, type_layer])

    assert list(group) == [pixel_layer, type_layer]
    for layer in group:
        assert layer._parent is group
        assert layer._psd is group._psd


def test_group_extend_with_nothing_to_add(group: Group) -> None:
    """An empty argument of either kind is a no-op, not an error."""
    nothing: list[Layer] = []

    group.extend(nothing)
    assert len(group) == 0

    group.extend(layer for layer in nothing)
    assert len(group) == 0


@pytest.mark.parametrize("size", [1, 3])
def test_group_extend_empties_a_live_container_into_another_group(
    size: int,
) -> None:
    """``dest.extend(src)`` is how a group's contents move, and it lost them.

    ``GroupMixin`` is iterable, so the detach loop was walking the very
    container it was mutating -- ``donor._layers.remove(layer)`` takes from the
    list being iterated -- and so reached only every other layer. The ones it
    did reach were detached and never re-attached, because the attach step
    re-read the same half-drained container: those are the layers lost from the
    document. The one it skipped was left in ``src`` *and* appended to
    ``dest``, parented to ``dest`` alone.

    ``size=1`` is the case that pins the materialization: with more than one
    layer the de-duplication pass builds a list of its own and would mask a
    missing ``list(layers)``.
    """
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    donor = psd[1]
    assert isinstance(donor, Group)
    src = psd.create_group(layer_list=list(donor)[:size], name="Src")
    moved = list(src)
    assert len(moved) == size
    dest = psd.create_group(name="Dest")

    dest.extend(src)

    assert list(dest) == moved
    assert len(src) == 0
    for layer in moved:
        assert layer._parent is dest


def test_group_extend_on_its_own_contents_changes_nothing() -> None:
    """Feeding a group itself is a no-op, and used not to terminate."""
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    group = psd.create_group(layer_list=list(psd), name="G")
    contents = list(group)
    assert len(contents) > 1

    # The backing list first, deliberately: that shape terminates either way
    # -- it just duplicated one layer and lost another -- so a regression
    # fails here rather than at ``extend(group)`` below, which without the
    # materialization never terminates at all.
    group.extend(group._layers)
    assert list(group) == contents

    group.extend(group)
    assert list(group) == contents


def test_group_insert(
    group: Group,
    pixel_layer: PixelLayer,
    type_layer: TypeLayer,
    smartobject_layer: SmartObjectLayer,
    fill_layer: AdjustmentLayer,
) -> None:
    group.append(pixel_layer)

    group.insert(0, fill_layer)
    assert group[0] is fill_layer

    group.insert(5, smartobject_layer)
    assert group[-1] is smartobject_layer

    group.insert(1, type_layer)
    assert group[1] is type_layer

    group.insert(-1, pixel_layer)
    assert (
        group[-2] is pixel_layer
    )  # Negative index insert the item before the one currently at the given index.


def test_group_setitem(
    group: Group,
    pixel_layer: PixelLayer,
    type_layer: TypeLayer,
    smartobject_layer: SmartObjectLayer,
    fill_layer: AdjustmentLayer,
) -> None:
    group.extend([pixel_layer, type_layer])

    group[0] = fill_layer
    assert len(group) == 2
    assert group[0] is fill_layer
    assert group[1] is type_layer
    assert pixel_layer not in group
    assert pixel_layer._parent is None
    assert fill_layer._parent is group
    assert fill_layer._psd is group._psd

    group[-1] = smartobject_layer
    assert len(group) == 2
    assert group[-1] is smartobject_layer
    assert type_layer not in group

    # Assigning the layer that is already at the index changes nothing.
    group[0] = fill_layer
    assert len(group) == 2
    assert group[0] is fill_layer

    # A layer already in the group moves to the index instead of being
    # duplicated, so the group shrinks, as with append() and insert().
    group[1] = fill_layer
    assert len(group) == 1
    assert group[0] is fill_layer

    # A layer that came from before the replaced one lands one index lower
    # than the index it was assigned to, because taking it out shifts the
    # rest of the group down.
    group.extend([pixel_layer, type_layer])
    assert len(group) == 3
    assert group[0] is fill_layer
    group[2] = fill_layer
    assert len(group) == 2
    assert group[0] is pixel_layer
    assert group[1] is fill_layer

    group[0] = fill_layer
    assert len(group) == 1

    with pytest.raises(IndexError):
        group[5] = pixel_layer
    assert len(group) == 1

    with pytest.raises(TypeError):
        group[0] = "not a layer"  # type: ignore[assignment]
    assert len(group) == 1

    with pytest.raises(TypeError):
        group[0:1] = [pixel_layer]  # type: ignore[index,assignment]
    assert len(group) == 1


def test_psd_image_setitem_round_trip(tmp_path: Any) -> None:
    psdimage = PSDImage.new(mode="RGB", size=(30, 30))
    psdimage.create_pixel_layer(Image.new("RGB", (30, 30), (255, 0, 0)), name="Red")
    psdimage.create_pixel_layer(Image.new("RGB", (30, 30), (0, 255, 0)), name="Green")
    replacement = PSDImage.new(mode="RGB", size=(30, 30)).create_pixel_layer(
        Image.new("RGB", (30, 30), (0, 0, 255)), name="Blue"
    )

    psdimage[0] = replacement
    assert [layer.name for layer in psdimage] == ["Blue", "Green"]

    out = tmp_path / "test_setitem.psd"
    psdimage.save(str(out))

    psdimage2 = PSDImage.open(str(out))
    assert [layer.name for layer in psdimage2] == ["Blue", "Green"]


def test_group_delitem(
    group: Group,
    pixel_layer: PixelLayer,
    type_layer: TypeLayer,
    smartobject_layer: SmartObjectLayer,
) -> None:
    group.extend([pixel_layer, type_layer, smartobject_layer])

    del group[0]
    assert len(group) == 2
    assert pixel_layer not in group

    # A slice is rejected up front, the way item assignment rejects one, and
    # the group is left alone.
    with pytest.raises(TypeError):
        del group[0:2]  # type: ignore[arg-type]
    assert len(group) == 2
    assert group[0] is type_layer
    assert group[1] is smartobject_layer


def test_group_remove(
    group: Group,
    pixel_layer: PixelLayer,
    type_layer: TypeLayer,
    smartobject_layer: SmartObjectLayer,
    fill_layer: AdjustmentLayer,
) -> None:
    group.extend([pixel_layer, type_layer, smartobject_layer])

    group.remove(pixel_layer)
    assert pixel_layer not in group

    group.remove(smartobject_layer)
    assert smartobject_layer not in group

    with pytest.raises(ValueError, match=r".* not found in group"):
        group.remove(pixel_layer)

    with pytest.raises(ValueError, match=r".* not found in group"):
        group.remove(fill_layer)


def test_group_pop(
    group: Group,
    pixel_layer: PixelLayer,
    type_layer: TypeLayer,
    smartobject_layer: SmartObjectLayer,
    fill_layer: AdjustmentLayer,
) -> None:
    group.extend([pixel_layer, type_layer, smartobject_layer, fill_layer])

    assert group.pop() is fill_layer
    assert group.pop(0) is pixel_layer
    assert group.pop(1) is smartobject_layer

    assert len(group) == 1

    with pytest.raises(IndexError):
        group.pop(5)

    group.clear()

    with pytest.raises(IndexError):
        group.pop()


def test_group_clear(
    group: Group,
    pixel_layer: PixelLayer,
    type_layer: TypeLayer,
    smartobject_layer: SmartObjectLayer,
    fill_layer: AdjustmentLayer,
) -> None:
    group.extend([pixel_layer, type_layer, smartobject_layer, fill_layer])
    assert len(group) == 4

    group.clear()
    assert len(group) == 0


def test_group_index(
    group: Group,
    pixel_layer: PixelLayer,
    type_layer: TypeLayer,
    smartobject_layer: SmartObjectLayer,
    fill_layer: AdjustmentLayer,
) -> None:
    with pytest.raises(ValueError, match=r".* not in list"):
        group.index(pixel_layer)

    group.extend([pixel_layer, type_layer, smartobject_layer, fill_layer])

    assert group.index(pixel_layer) == 0
    assert group.index(type_layer) == 1
    assert group.index(smartobject_layer) == 2
    assert group.index(fill_layer) == 3

    group.clear()

    with pytest.raises(ValueError, match=r".* not in list"):
        group.index(fill_layer)


def test_group_count(
    group: Group,
    pixel_layer: PixelLayer,
    type_layer: TypeLayer,
    smartobject_layer: SmartObjectLayer,
    fill_layer: AdjustmentLayer,
) -> None:
    group.extend([pixel_layer, type_layer, smartobject_layer, fill_layer])

    assert group.count(pixel_layer) == 1
    assert group.count(type_layer) == 1
    assert group.count(smartobject_layer) == 1
    assert group.count(fill_layer) == 1

    group.clear()

    assert group.count(pixel_layer) == 0
    assert group.count(type_layer) == 0
    assert group.count(smartobject_layer) == 0
    assert group.count(fill_layer) == 0

    # Append the pixel_layer twice, but we do not allow duplicates.
    group.append(pixel_layer)
    group.append(pixel_layer)

    assert group.count(pixel_layer) == 1


def test_artboard_move(group: Group) -> None:
    artboard = Artboard._move(group)

    assert artboard._channels is group._channels
    assert artboard._record is group._record
    assert artboard._bounding_channels is group._bounding_channels
    assert artboard._bounding_record is group._bounding_record


def test_lock_layer(pixel_layer: PixelLayer) -> None:
    pixel_layer.lock(
        ProtectedFlags.TRANSPARENCY | ProtectedFlags.COMPOSITE | ProtectedFlags.POSITION
    )
    locks = pixel_layer.locks
    assert locks is not None

    assert locks.transparency
    assert locks.composite
    assert locks.position
    assert not locks.nesting

    pixel_layer.lock(ProtectedFlags.NESTING)
    locks = pixel_layer.locks
    assert locks is not None

    assert not locks.transparency
    assert not locks.composite
    assert not locks.position
    assert locks.nesting

    pixel_layer.unlock()
    locks = pixel_layer.locks
    assert locks is not None

    assert locks.value == 0

    pixel_layer.lock()
    locks = pixel_layer.locks
    assert locks is not None

    assert locks.complete


def test_group_move_between_psdimages() -> None:
    psdimage = PSDImage.new(mode="RGB", size=(100, 100))
    layer = psdimage.create_pixel_layer(
        Image.new("RGB", (50, 50), (255, 0, 0)),
        name="Red Layer",
    )
    assert layer._psd is psdimage
    assert len(psdimage) == 1
    psdimage2 = PSDImage.new(mode="RGB", size=(200, 200))
    group = psdimage2.create_group(
        [],
        name="Empty Group",
    )
    assert len(psdimage2) == 1
    assert len(group) == 0

    group.append(layer)
    assert layer._psd is psdimage2
    assert len(psdimage) == 0
    assert len(psdimage2) == 1
    assert len(group) == 1
    assert layer.parent is group


@pytest.mark.parametrize("move", ["append", "extend", "insert"])
def test_cross_document_move_rebuilds_the_donor_record_list(
    tmp_path: Path, move: str
) -> None:
    """A layer moved out of a document must leave that document's file (#841).

    ``extend()`` and ``insert()`` rebuilt the *receiving* document's flat
    record list only, and :py:meth:`PSDImage.save` writes the stored list
    without rebuilding it, so the donor went on writing the layer it no longer
    holds and the layer landed in *both* files. The in-memory tree was already
    right, so only a save and reopen of the donor sees this.

    All three entry points are moved separately because they reach the rebuild
    by different routes: ``append()`` delegates to ``extend()``, while
    ``insert()`` carries its own donor bookkeeping. The donor is a shipped
    file rather than a ``PSDImage.new()`` one so that it starts clean --
    ``create_pixel_layer()`` would have marked it updated already, and the
    dirty flag below would then hold whether or not the move set it.
    """
    donor = PSDImage.open(full_name("clipping-mask.psd"))
    dest = PSDImage.new(mode="RGB", size=donor.size)
    layer = donor[0]
    assert layer.name == "Background"
    assert not donor.is_updated()

    if move == "append":
        dest.append(layer)
    elif move == "extend":
        dest.extend([layer])
    else:
        dest.insert(0, layer)

    assert [child.name for child in donor] == ["Group 2"]
    # The defect itself: the flat record list the donor will write.
    layer_info = donor._record.layer_and_mask_information.layer_info
    assert layer_info is not None
    assert not any(record.name == "Background" for record in layer_info.layer_records)
    # Rebuilding also marks the donor updated, which is what makes its
    # ``save()`` regenerate a preview that no longer shows the layer.
    assert donor.is_updated()

    donor_path = tmp_path / "donor.psd"
    donor.save(donor_path)
    assert [child.name for child in PSDImage.open(donor_path)] == ["Group 2"]

    dest_path = tmp_path / "dest.psd"
    dest.save(dest_path)
    assert [child.name for child in PSDImage.open(dest_path)] == ["Background"]


@pytest.mark.parametrize(
    "fixture_name", ["16bit5x5.psd", "16bit5x5.psb", "32bit5x5.psd", "32bit5x5.psb"]
)
@pytest.mark.parametrize("edit", ["remove", "pop", "clear", "create_group"])
def test_a_structural_edit_to_a_deep_document_survives_a_save(
    tmp_path: Path, fixture_name: str, edit: str
) -> None:
    """A 16- or 32-bit document must save the layer set it actually holds (#861).

    Such a document keeps its flat record list in the ``Lr16``/``Lr32`` tagged
    block and leaves the layer info section below it empty, which is what
    :py:meth:`PSD._get_layer_info` reads. ``_update_record()`` rebuilt the
    empty section instead, and the writer emits both, so the file went out
    carrying a rebuilt list nobody reads beside the stale block everybody
    does. The in-memory tree was already right, so only a save and reopen
    sees this.

    All four container methods are exercised because the defect is in the
    rebuild they share, not in any one of them, and both PSD and PSB because
    the two write the section's length field at different widths. 8-bit
    documents were never affected -- they have no such block, and the section
    *is* authoritative.

    The reopened document is deliberately never composited: a save of an
    edited 16- or 32-bit document writes an 8-bit preview into the image data
    section, so ``topil()`` on the result raises for reasons that have nothing
    to do with this fix.
    """
    psd = PSDImage.open(full_name(fixture_name))
    assert [child.name for child in psd] == [
        "Background",
        "Background copy",
        "Background copy 2",
    ]

    if edit == "remove":
        psd.remove(psd[0])
    elif edit == "pop":
        psd.pop(0)
    elif edit == "clear":
        psd.clear()
    else:
        psd.create_group()
    expected = [layer.name for layer in psd.descendants()]

    output = tmp_path / f"edited{Path(fixture_name).suffix}"
    psd.save(output)
    reopened = PSDImage.open(output)
    assert [layer.name for layer in reopened.descendants()] == expected

    # The defect itself: which of the two lists the rebuild landed in.
    lmi = reopened._record.layer_and_mask_information
    assert lmi.layer_info is not None
    assert lmi.layer_info.layer_count == 0
    assert len(lmi.layer_info.layer_records) == 0
    authoritative = reopened._record._get_layer_info()
    assert authoritative is not None
    assert authoritative is not lmi.layer_info
    assert authoritative.layer_count == len(authoritative.layer_records)


def test_a_cross_document_move_between_deep_documents_survives_a_save(
    tmp_path: Path,
) -> None:
    """A layer moved between two 16-bit documents lands in exactly one (#861).

    This is the case the review of #860 raised. #841 widened ``extend()`` to
    rebuild the donor as well as the receiver; at 16 bits both rebuilds went
    to the section the reader ignores, so on ``main`` the layer stayed in the
    donor's file and never reached the receiver's -- a move that loses the
    layer from both sides at once.

    The receiver is a shipped PSB rather than a ``PSDImage.new()`` document so
    that it carries an ``Lr16`` block of its own; a new one has none, and its
    half of the move would then exercise the 8-bit path that was never broken.
    The moved layer is renamed first because both fixtures ship the same three
    layer names.
    """
    donor = PSDImage.open(full_name("16bit5x5.psd"))
    dest = PSDImage.open(full_name("16bit5x5.psb"))
    layer = donor[0]
    layer.name = "Moved"

    dest.append(layer)

    assert [child.name for child in donor] == ["Background copy", "Background copy 2"]
    assert [child.name for child in dest][-1] == "Moved"

    donor_path = tmp_path / "donor.psd"
    donor.save(donor_path)
    assert [child.name for child in PSDImage.open(donor_path)] == [
        "Background copy",
        "Background copy 2",
    ]

    dest_path = tmp_path / "dest.psb"
    dest.save(dest_path)
    assert [child.name for child in PSDImage.open(dest_path)] == [
        "Background",
        "Background copy",
        "Background copy 2",
        "Moved",
    ]


@pytest.mark.parametrize(
    ("bg_type", "expected"),
    [(2, (1.0, 1.0, 1.0, 1.0)), (3, (1.0, 1.0, 1.0, 0.0))],
)
def test_artboard_background_is_canvas_space_on_a_cmyk_document(
    bg_type: int, expected: tuple[float, ...]
) -> None:
    """A white artboard background composited black on a CMYK document (#747).

    The branch spelled white as ``(0, 0, 0, 0)`` -- no ink -- into arrays that
    count what is *left*, where that is every ink at full strength. The RGB,
    grayscale and Lab branches beside it were already canvas-space, so CMYK was
    the odd one out.

    ``artboard-bgcolor.psd`` is an RGB document whose artboards both use the
    custom-colour type, so neither the colour mode nor the background type
    under test can be reached from a shipped fixture; both are forged here.
    """
    psd = PSDImage.open(full_name("artboard-bgcolor.psd"))
    artboard = psd[0]
    assert isinstance(artboard, Artboard)

    for key in (Tag.ARTBOARD_DATA1, Tag.ARTBOARD_DATA2, Tag.ARTBOARD_DATA3):
        if key in artboard.tagged_blocks:
            artboard.tagged_blocks.get_data(key)[b"artboardBackgroundType"] = Integer(
                bg_type
            )
    psd._record.header.color_mode = ColorMode.CMYK
    assert psd.color_mode == ColorMode.CMYK

    color, alpha = artboard._artboard_background_defaults()
    assert alpha == 1.0
    assert color == expected

    # The polarity is only meaningful against what the PIL exit does with it.
    image = Image.fromarray(
        np.full((2, 2, 4), 255 * np.array(color, dtype=np.float32), dtype=np.uint8),
        "CMYK",
    )
    rendered = post_process(image, None, None).convert("RGB").getpixel((0, 0))
    assert rendered == ((255, 255, 255) if bg_type == 2 else (0, 0, 0))


@pytest.mark.parametrize("bg_type", [2, 3])
def test_artboard_background_chroma_is_offset_encoded_on_a_lab_document(
    bg_type: int,
) -> None:
    """A neutral Lab a/b is 128/255, not 0.5 (#743).

    The two are half a code value apart, which would be beneath notice if the
    exit rounded -- but ``composite_pil()`` casts with
    ``(255 * color).astype(np.uint8)``, which truncates, so 0.5 lands on byte
    127 where Photoshop writes 128 for every neutral. Asserting the tuple alone
    would not separate them at any sane tolerance, so the byte is asserted too.

    Forged the same way as the CMYK case above, and for the same reason: no
    shipped fixture is a Lab document with a white or black artboard.
    """
    psd = PSDImage.open(full_name("artboard-bgcolor.psd"))
    artboard = psd[0]
    assert isinstance(artboard, Artboard)

    for key in (Tag.ARTBOARD_DATA1, Tag.ARTBOARD_DATA2, Tag.ARTBOARD_DATA3):
        if key in artboard.tagged_blocks:
            artboard.tagged_blocks.get_data(key)[b"artboardBackgroundType"] = Integer(
                bg_type
            )
    psd._record.header.color_mode = ColorMode.LAB
    assert psd.color_mode == ColorMode.LAB

    color, alpha = artboard._artboard_background_defaults()
    assert alpha == 1.0
    assert color == (1.0 if bg_type == 2 else 0.0, 128 / 255, 128 / 255)
    chroma = (255 * np.array(color, dtype=np.float32)).astype(np.uint8)
    assert chroma[1] == 128


# ---------------------------------------------------------------------------
# Cached bounding boxes (#814)
#
# Every test below arms the cache *before* mutating, and asserts the recomputed
# box differs from the armed one. That ordering matters: a test written the way
# the issue's repro is -- create a group, add to it, then read -- cannot fail on
# Python >= 3.12, because a fresh group only gets ``(0, 0, 0, 0)`` cached when
# ``_update_children()``'s ``isinstance(layer, GroupMixin)`` executes the
# ``bbox`` descriptor, and CPython 3.12 made ``isinstance()`` against a
# ``runtime_checkable`` protocol use ``inspect.getattr_static()`` instead of
# ``hasattr()``. Read-then-mutate has no such dependency and fails on every
# supported interpreter.
# ---------------------------------------------------------------------------


def _mutate(group: Group, op: str, donor: Any) -> None:
    if op == "append":
        group.append(donor)
    elif op == "extend":
        group.extend([donor])
    elif op == "extend_duplicate":
        # Same layer twice: de-duplication must not drop the donor with the
        # second mention of it (#820).
        group.extend([donor, donor])
    elif op == "insert":
        group.insert(0, donor)
    elif op == "remove":
        group.remove(group[0])
    elif op == "clear":
        group.clear()
    elif op == "delitem":
        del group[0]
    elif op == "setitem":
        group[0] = donor
    elif op == "pop":
        group.pop(0)
    else:  # pragma: no cover - guards the parametrization itself
        raise AssertionError(f"unknown op {op}")


@pytest.mark.parametrize(
    ("op", "expected"),
    [
        ("append", (0, -73, 360, 200)),
        ("extend", (0, -73, 360, 200)),
        ("extend_duplicate", (0, -73, 360, 200)),
        ("insert", (0, -73, 360, 200)),
        ("remove", (50, 44, 174, 113)),
        ("clear", (0, 0, 0, 0)),
        ("delitem", (50, 44, 174, 113)),
        ("setitem", (0, 0, 360, 200)),
        # ``pop(0)``, not ``pop()``: the topmost layer here does not move the
        # union, so popping it would leave the box legitimately unchanged and
        # the assertion below could not fail.
        ("pop", (50, 44, 174, 113)),
    ],
)
def test_every_group_mutator_invalidates_the_cached_bbox(
    op: str, expected: Tuple[int, int, int, int]
) -> None:
    """Mutating a group's contents must drop the box it cached beforehand."""
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    group = psd[1]
    assert isinstance(group, Group)
    donor = psd[0]

    armed = group.bbox
    assert armed == (50, -73, 288, 146)

    _mutate(group, op, donor)

    assert group.bbox == expected
    # Not coverage -- both sides are literals from this test, so it reduces to
    # ``expected != armed``. It is here to reject a future parametrization row
    # whose op leaves the box unchanged, which would assert nothing.
    assert expected != armed


def test_moving_a_layer_out_invalidates_the_donors_bbox() -> None:
    """The group a layer is taken *from* is never touched by the caller.

    ``extend()`` and ``insert()`` pull a layer out of its old parent with
    ``layer.parent._layers.remove(layer)``, which bypasses ``remove()``, so the
    donor's cache has to be dropped by the receiving group (#814).
    """
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    donor = psd[1]
    assert isinstance(donor, Group)
    armed = donor.bbox
    assert armed == (50, -73, 288, 146)

    recipient = psd.create_group(name="Recipient")
    recipient.append(donor[0])

    assert donor.bbox == (50, 44, 174, 113)
    assert donor.bbox != armed


def test_a_mutation_invalidates_every_box_above_it() -> None:
    """A nested group, its parent and the document all cache a box of their own.

    Driven by a ``clear()`` rather than an addition: moving a layer between
    containers within one document leaves the *document's* union unchanged, so
    an addition would make the outermost assertion vacuous.
    """
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    outer = psd[1]
    assert isinstance(outer, Group)
    inner = outer[0]
    assert isinstance(inner, Group)

    armed = (inner.bbox, outer.bbox, psd.bbox)
    assert armed == ((103, -73, 288, 146), (50, -73, 288, 146), (0, -73, 360, 200))

    inner.clear()

    assert (inner.bbox, outer.bbox, psd.bbox) == (
        (0, 0, 0, 0),
        (50, 44, 174, 113),
        (0, 0, 360, 200),
    )
    assert outer.bbox != armed[1]
    assert psd.bbox != armed[2]


def test_the_document_bbox_follows_a_top_level_visibility_change() -> None:
    """``PSDImage`` caches a box too, and is not a ``Layer``.

    ``Layer._invalidate_bbox()`` used to recurse only into ``Group`` and
    ``Artboard``, so the walk stopped one level short of the document (#814).
    """
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    armed = psd.bbox
    assert armed == (0, -73, 360, 200)

    psd[0].visible = False

    assert psd.bbox == (50, -73, 288, 146)
    assert psd.bbox != armed


def test_a_group_built_through_the_editing_api_reports_its_contents() -> None:
    """The issue's own repro (#814).

    Pre-fix this failed on Python <= 3.11 only, for the seeding reason spelled
    out above; it is the user-facing statement of the bug, not the guard.
    ``test_every_group_mutator_invalidates_the_cached_bbox`` is the guard.
    """
    psd = PSDImage.open(full_name("effects/outside-stroke.psd"))
    layer = psd[0]
    assert layer.bbox == (8, 8, 24, 24)

    group = psd.create_group([layer], name="G")

    assert group.bbox == (8, 8, 24, 24)
    assert group.bbox == Group.extract_bbox(group)


def test_a_group_knows_which_container_it_sits_in() -> None:
    """``Group.parent`` resolves to ``Layer.parent``, not to a protocol stub.

    ``GroupMixin`` inherits ``GroupMixinProtocol``, and both precede ``Layer``
    in ``Group``'s MRO, so anything with a body defined on either of them
    shadows the real implementation for every group. Declaring ``parent`` on
    the protocol as a ``...`` property did exactly that, and silently handed
    every group a ``None`` parent -- which in turn breaks the invalidation walk
    this module's other tests rely on.
    """
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    outer = psd[1]
    assert isinstance(outer, Group)
    inner = outer[0]
    assert isinstance(inner, Group)

    assert inner.parent is outer
    assert outer.parent is psd
    assert psd.parent is None


def _hidden_tree(psd: PSDImage) -> Tuple[Group, Group, Group]:
    """A ``Mover`` holding ``Inner``, both parked under a hidden container."""
    hidden = psd.create_group(name="Hidden")
    mover = psd.create_group(name="Mover")
    inner = psd.create_group(name="Inner")
    hidden.append(mover)
    mover.append(inner)
    inner.append(psd[0])
    hidden.visible = False
    assert mover.bbox == (0, 0, 0, 0)  # armed while hidden
    assert inner.bbox == (0, 0, 0, 0)
    return hidden, mover, inner


@pytest.mark.parametrize("how", ["append", "insert", "remove", "clear"])
def test_reparenting_a_group_invalidates_the_subtree_it_carries(how: str) -> None:
    """A group's box depends on its ancestors' visibility, not only its contents.

    ``Group.extract_bbox()`` filters children through ``is_visible()``, which
    walks *up* the parent chain. So taking a group out of a hidden container
    changes the box of every group in the subtree it carries -- none of which
    the upward walk in ``_invalidate_bbox()`` ever reaches.
    """
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    hidden, mover, inner = _hidden_tree(psd)

    if how == "append":
        psd.create_group(name="Dest").append(mover)
    elif how == "insert":
        psd.create_group(name="Dest").insert(0, mover)
    elif how == "remove":
        hidden.remove(mover)
    else:
        hidden.clear()

    # Visible again, so both boxes have to come back -- including the nested
    # one, which a single level of invalidation would leave behind.
    assert mover.bbox == (0, 0, 360, 200)
    assert inner.bbox == (0, 0, 360, 200)


@pytest.mark.parametrize("nested", [False, True])
def test_moving_a_shape_to_another_document_rescales_its_bbox(nested: bool) -> None:
    """A vector-mask-only shape's box is scaled by its *document's* size.

    ``ShapeLayer.bbox`` multiplies the mask's normalized bounds by
    ``self._psd.width`` and ``height``, so a cross-document move repoints
    ``_psd`` at a canvas of a different size and the cached box no longer
    describes anything. Nested inside a moved group, it is reached by the same
    subtree walk that reaches the groups.
    """
    source = PSDImage.open(full_name("vector-mask.psd"))
    target = PSDImage.open(full_name("note.psd"))
    assert (source.width, source.height) == (100, 150)
    assert (target.width, target.height) == (300, 300)

    shape = source[1]
    assert isinstance(shape, ShapeLayer)
    moved: Any = shape
    if nested:
        moved = source.create_group([shape], name="G")

    assert shape.bbox == (12, 42, 53, 83)  # armed against the 100x150 canvas

    target.append(moved)

    assert shape.bbox == (35, 85, 159, 166)


# ---------------------------------------------------------------------------
# Cached bounding boxes, the downward half (#819)
#
# ``Group.extract_bbox()`` filters children through ``is_visible()``, which
# walks *up* the parent chain -- so a container's box is a function of its
# ancestors' ``visible`` flags, and hiding a group has to drop the boxes cached
# *beneath* it as well as the unions above it.
#
# No *visibility-dependent* cache is consulted on the way down: for a group
# child ``_get_bbox()`` recurses through ``Group.extract_bbox()`` rather than
# reading ``child.bbox``. It does read ``child.bbox`` for a non-group child,
# and ``ShapeLayer`` caches that -- but no ``visible`` flag feeds it, only the
# document's size. So a parent's box stays correct and ``psd.composite()`` is
# unaffected. What goes wrong is a *direct* read of the descendant -- ``bbox``,
# and the
# ``left``/``top``/``right``/``bottom``/``width``/``height`` that ``Group``
# overrides to read it -- and ``layer.composite()``, which takes that same box
# as the viewport it renders on.
#
# Every test below arms the cache before hiding, for the reason given in the
# #814 section above.
# ---------------------------------------------------------------------------


def test_hiding_a_group_drops_the_boxes_cached_beneath_it() -> None:
    """The issue's repro (#819): a child reporting a box its hidden parent does not."""
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    outer, inner = psd[1], psd[1][0]  # type: ignore[index]
    assert isinstance(outer, Group) and isinstance(inner, Group)

    armed = inner.bbox
    assert armed == (103, -73, 288, 146)

    outer.visible = False

    # Compared against ``extract_bbox()`` rather than a second literal: the
    # cache has to agree with what the tree actually says, not with a number
    # chosen here.
    assert inner.bbox == Group.extract_bbox(inner) == (0, 0, 0, 0)


def test_hiding_reaches_every_level_beneath_not_just_the_first() -> None:
    """The walk recurses; dropping the direct children's boxes is not enough.

    This fixture ships three nested groups that all have a non-empty box, so
    the innermost sits two levels below the one being hidden: a one-level fix
    leaves it stale while making the level above it look correct. Built from a
    fixture rather than with ``create_group()`` so that #818's reparenting
    invalidation stays out of the setup and only the ``visible`` walk is under
    test.
    """
    psd = PSDImage.open(full_name("adjustments/adjustment_nested_composition_4.psd"))
    outer = psd[2]
    assert isinstance(outer, Group) and outer.name == "Group 1 copy 2"
    middle = outer[0]
    assert isinstance(middle, Group) and middle.name == "Group 1 copy"
    inner = middle[0]
    assert isinstance(inner, Group) and inner.name == "Group 1"

    assert outer.bbox == middle.bbox == inner.bbox == (0, 0, 32, 32)

    outer.visible = False

    assert middle.bbox == (0, 0, 0, 0)  # one level down
    assert inner.bbox == Group.extract_bbox(inner) == (0, 0, 0, 0)  # two levels down


def test_showing_a_group_again_restores_the_boxes_beneath_it() -> None:
    """Invalidation does not depend on which way the flag moved."""
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    outer, inner = psd[1], psd[1][0]  # type: ignore[index]
    assert isinstance(outer, Group) and isinstance(inner, Group)
    armed = inner.bbox

    outer.visible = False
    assert inner.bbox == (0, 0, 0, 0)  # re-armed, now with the hidden box

    outer.visible = True

    assert inner.bbox == Group.extract_bbox(inner) == armed


def test_a_hidden_ancestor_reads_the_same_whichever_order_it_is_read() -> None:
    """Every accessor that reads the cache, not just ``bbox``.

    ``Group`` overrides ``left``/``top``/``right``/``bottom`` to read
    ``self.bbox`` and ``width``/``height`` derive from those, so the stale
    value surfaces through seven properties -- the surface the changelog
    names, and one no other test here reads. Both sides come from the same
    file, so this compares the two read orders against each other rather than
    against numbers chosen here.

    Ranked as coverage rather than a guard: no mutant of this fix kills it
    that ``..._drops_the_boxes_cached_beneath_it`` does not already kill.
    """

    def read(arm: bool) -> Tuple[Any, ...]:
        psd = PSDImage.open(full_name("clipping-mask.psd"))
        inner = psd[1][0]  # type: ignore[index]
        if arm:
            _ = inner.bbox  # armed while the ancestor is still visible
        psd[1].visible = False
        return (
            inner.bbox,
            inner.left,
            inner.top,
            inner.right,
            inner.bottom,
            inner.width,
            inner.height,
        )

    assert read(arm=True) == read(arm=False)


def test_setting_visible_to_the_value_it_already_has_keeps_the_cache() -> None:
    """A write that changes nothing invalidates nothing.

    Reads ``_bbox`` directly because that is the only way to tell a surviving
    cache from one that was dropped and then recomputed to the same answer.
    """
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    group = psd[1]
    assert isinstance(group, Group)
    armed = group.bbox

    group.visible = group.visible

    assert group._bbox == armed


def test_hiding_an_artboard_drops_its_descendants_but_not_its_own_box() -> None:
    """An ``Artboard`` is a ``Group``, so the walk passes through it.

    Its own box is the ``artboardRect`` out of its tagged blocks, which no
    visibility flag feeds -- so hiding it leaves that unchanged, while the
    group nested inside it, whose box *is* filtered through ``is_visible()``,
    has to be dropped.
    """
    psd = PSDImage.open(full_name("artboard.psd"))
    artboard = psd[0]
    assert isinstance(artboard, Artboard)
    frame = artboard.bbox
    assert frame == (238, 77, 1154, 1061)

    # 'border' is drawn to the artboard's edges, so ``nested``'s union below
    # coincidentally equals ``frame`` -- same tuple, unrelated sources: one is
    # the artboardRect, the other a union over record offsets.
    nested = psd.create_group([artboard[2]], name="Nested")
    artboard.append(nested)
    armed = nested.bbox
    assert armed == (238, 77, 1154, 1061)

    artboard.visible = False

    assert nested.bbox == Group.extract_bbox(nested) == (0, 0, 0, 0)
    # An invariant, not a guard on this fix: ``Artboard.bbox`` reads a tagged
    # block, so no implementation here could move it. Kept to pin that
    # exemption if an artboard's own box is ever made to follow its children.
    assert artboard.bbox == frame


@pytest.mark.composite
def test_hiding_a_group_changes_what_a_descendant_renders_onto() -> None:
    """The stale box is not just a reported number -- it is a render viewport.

    ``layer.composite()`` renders onto the layer's own ``bbox``, so before the
    fix a descendant of a newly hidden group was composited onto the box it
    had while visible: 185x219 of content where a freshly read document gives
    the 360x200 viewbox fallback. ``psd.composite()`` never differed, because
    it re-derives through the visibility filter instead of reading a
    descendant's cache.
    """

    def render(arm: bool) -> Any:
        psd = PSDImage.open(full_name("clipping-mask.psd"))
        outer, inner = psd[1], psd[1][0]  # type: ignore[index]
        if arm:
            _ = inner.bbox  # armed while the ancestor is still visible
        outer.visible = False
        return inner.composite(force=True), psd.composite()

    (armed_layer, armed_doc), (fresh_layer, fresh_doc) = render(True), render(False)

    # The control goes first so that it is actually reached: the layer
    # assertions below fail under the bug, and this one holds either way --
    # ``psd.composite()`` never differed. It documents the scope rather than
    # guarding it.
    assert armed_doc.tobytes() == fresh_doc.tobytes()

    # Both sides are rendered from the same file, so these compare the two read
    # orders against each other rather than against bytes committed here.
    assert armed_layer.size == fresh_layer.size
    assert armed_layer.tobytes() == fresh_layer.tobytes()


@pytest.mark.parametrize("error", [ValueError, RuntimeError], ids=["narrow", "wide"])
def test_repr_drops_an_annotation_it_cannot_read(
    monkeypatch: pytest.MonkeyPatch, error: type[Exception]
) -> None:
    """A repr reports what it can read and says nothing about the rest (#828).

    Driven by making ``has_effects()`` raise rather than by a forged file, so
    it pins the repr on its own: the effects block #828 was reported for is
    now skipped in ``Effects`` instead, one layer down, and a test that went
    through such a file would pass on that fix alone.

    Parametrized over an exception the compositor's ``_UNREADABLE`` holds and
    one it does not, because the choice of ``except Exception`` over that
    tuple is the decision under test. ``print()``, pdb, a logging handler and
    pytest's own assertion rewriting all call this, and none of them asked
    about effects.
    """

    def raises(*args: Any, **kwargs: Any) -> bool:
        raise error("forged")

    layer = PSDImage.open(full_name("layer_effects.psd"))[10]
    assert " effects" in repr(layer)

    monkeypatch.setattr(Layer, "has_effects", raises)
    assert repr(layer) == "TypeLayer('Stroke' size=232x48)"


def test_repr_of_an_artboard_missing_its_data_drops_the_size() -> None:
    """The same defect one class away from the one #828 reports.

    ``Artboard.bbox`` raises outright when no artboard tagged block is there
    to read, and ``__repr__`` reaches it through ``self.width`` -- so a repr
    could raise for a reason that has nothing to do with effects, and did so
    before the annotation was guarded. Not reachable from a file Photoshop
    wrote, so the block is deleted here.

    Whether such a *document* composites is deliberately not asserted: it
    raises on Python <= 3.11 and renders on 3.12, because the
    ``isinstance(layer, GroupMixin)`` in ``_resolve_source()`` runs
    ``hasattr(x, "bbox")`` on the older protocol implementation, and
    ``hasattr`` swallows only ``AttributeError``. That is the footgun
    ``_accepts()`` already documents, not anything about the repr.
    """
    psd = PSDImage.open(full_name("artboard.psd"))
    artboard = psd[0]
    assert isinstance(artboard, Artboard)
    assert " size=" in repr(artboard)

    for key in (Tag.ARTBOARD_DATA1, Tag.ARTBOARD_DATA2, Tag.ARTBOARD_DATA3):
        if key in artboard.tagged_blocks:
            del artboard.tagged_blocks[key]
    artboard._bbox = None

    assert repr(artboard) == "Artboard('Artboard 1')"
