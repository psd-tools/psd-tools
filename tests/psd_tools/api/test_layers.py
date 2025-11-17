import logging
from typing import Any, Optional, Tuple

import pytest
from PIL import Image

from psd_tools.api.layers import (
    AdjustmentLayer,
    Artboard,
    Group,
    PixelLayer,
    ShapeLayer,
    SmartObjectLayer,
    TypeLayer,
)
from psd_tools.api.pil_io import get_pil_channels, get_pil_depth
from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import (
    BlendMode,
    CompatibilityMode,
    ProtectedFlags,
    SectionDivider,
    Tag,
)

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
    layer.name = "\ud83d\udc7d"
    assert layer.name == "\ud83d\udc7d"
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
    assert psd[1][1].has_clip_layers()
    assert psd[1][2].clipping
    assert psd[0].has_clip_layers()


def test_clip_stack() -> None:
    """Check if consecutive clipping layers are correctly identified."""
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    psd[1][1].clipping = True
    assert psd[1][0].has_clip_layers()
    assert psd[1][1].clipping
    assert psd[1][2].clipping
    assert not psd[1][1].has_clip_layers()
    assert not psd[1][2].has_clip_layers()


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
    assert Group.extract_bbox(psd[1:], False) == (40, 72, 83, 134)
    assert Group.extract_bbox(psd[1:], True) == (25, 34, 83, 134)
    with pytest.raises(TypeError):
        Group.extract_bbox(psd[1][0])


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
    assert psd[1][0].next_sibling() is None
    assert psd[1][0].previous_sibling() is None


def test_shape_and_fill_layer() -> None:
    psd = PSDImage.open(full_name("vector-mask2.psd"))
    for i in range(8):
        assert isinstance(psd[i], ShapeLayer)
    for i in range(8, 10):
        assert isinstance(psd[i], PixelLayer)


def test_has_effects() -> None:
    psd = PSDImage.open(full_name("effects/effects-enabled.psd"))
    assert not psd[0].has_effects()
    assert psd[1].has_effects()
    assert psd[1].has_effects(name="ColorOverlay")
    assert not psd[1].has_effects(name="DropShadow")
    assert not psd[2].has_effects()
    assert psd[2].has_effects(enabled=False)
    assert not psd[3].has_effects()
    assert psd[3].has_effects(enabled=False)
    logger.error("Checking disabled effects")
    assert psd[3].has_effects(enabled=False, name="ColorOverlay")
    assert not psd[3].has_effects(enabled=False, name="DropShadow")


def test_bbox_updates() -> None:
    psd = PSDImage.open(full_name("hidden-groups.psd"))
    group1 = psd[1]
    group1.visible = False
    assert group1.bbox == (0, 0, 0, 0)
    group1.visible = True
    assert group1.bbox == (25, 34, 80, 88)


def test_new_group(group: Group) -> None:
    test_group = Group.new(group, "Test Group")
    assert test_group._parent is group
    assert (
        test_group._record.tagged_blocks.get_data(Tag.SECTION_DIVIDER_SETTING).kind
        is SectionDivider.OPEN_FOLDER
    )
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
    image = Image.new(mode, (30, 30))
    layer = PixelLayer.frompil(image, psdimage, name="Test Layer")
    assert len(psdimage) == 1

    image = image.convert(psdimage.pil_mode)
    assert (
        len(layer._record.channel_info) == get_pil_channels(image.mode.rstrip("A")) + 1
    )
    assert len(layer._channels) == get_pil_channels(image.mode.rstrip("A")) + 1

    for channel in range(get_pil_channels(image.mode.rstrip("A"))):
        assert (
            layer._channels[channel + 1].get_data(
                image.width, image.height, get_pil_depth(image.mode.rstrip("A"))
            )
            == image.getchannel(channel).tobytes()
        )


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
        pixel_layer.reference_point = (10.5,)

    with pytest.raises(ValueError, match=r".* sequence of two floats.*"):
        pixel_layer.reference_point = (10.5, 20.5, 30.5)


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
