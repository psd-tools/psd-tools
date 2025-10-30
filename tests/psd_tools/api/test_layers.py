import logging

import pytest
from PIL.Image import Image

from psd_tools.api.layers import Artboard, Group, PixelLayer, ShapeLayer
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
def pixel_layer():
    return PSDImage.open(full_name("layers/pixel-layer.psd"))[0]


@pytest.fixture
def adjustment_layer():
    return PSDImage.open(full_name("layers/brightness-contrast.psd"))[0]


@pytest.fixture
def fill_layer():
    return PSDImage.open(full_name("layers/solid-color-fill.psd"))[0]


@pytest.fixture
def shape_layer():
    return PSDImage.open(full_name("layers/shape-layer.psd"))[0]


@pytest.fixture
def smartobject_layer():
    return PSDImage.open(full_name("layers/smartobject-layer.psd"))[0]


@pytest.fixture
def type_layer():
    return PSDImage.open(full_name("layers/type-layer.psd"))[0]


@pytest.fixture
def group():
    return PSDImage.open(full_name("layers/group.psd"))[0]


ALL_FIXTURES = [
    "pixel_layer",
    "shape_layer",
    "smartobject_layer",
    "type_layer",
    "group",
    "adjustment_layer",
    "fill_layer",
]


def test_pixel_layer_properties(pixel_layer):
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


def test_pixel_layer_writable_properties(pixel_layer):
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


def test_layer_is_visible(pixel_layer):
    assert pixel_layer.is_visible()


@pytest.fixture(params=["pixel_layer", "group"])
def is_group_args(request):
    return (
        request.getfixturevalue(request.param),
        {"pixel_layer": False, "group": True}.get(request.param),
    )


def test_layer_is_group(is_group_args):
    layer, expected = is_group_args
    assert layer.is_group() == expected


def test_layer_has_mask(pixel_layer):
    assert pixel_layer.has_mask() is False


@pytest.fixture(params=ALL_FIXTURES)
def kind_args(request):
    expected = request.param.replace("_layer", "")
    expected = expected.replace("fill", "solidcolorfill")
    expected = expected.replace("adjustment", "brightnesscontrast")
    return (request.getfixturevalue(request.param), expected)


def test_layer_kind(kind_args):
    layer, expected = kind_args
    assert layer.kind == expected


def test_curves_with_vectormask():
    layer = PSDImage.open(full_name("layers/curves-with-vectormask.psd"))[0]
    assert layer.kind == "curves"


@pytest.fixture(params=ALL_FIXTURES)
def topil_args(request):
    is_image = request.param in {
        "pixel_layer",
        "smartobject_layer",
        "type_layer",
        "fill_layer",
        "shape_layer",
    }
    return (request.getfixturevalue(request.param), is_image)


def test_topil(topil_args):
    fixture, is_image = topil_args
    image = fixture.topil()

    channel_ids = [c.id for c in fixture._record.channel_info if c.id >= -1]
    for channel in channel_ids:
        fixture.topil(channel)

    assert isinstance(image, Image) if is_image else image is None


def test_clip_adjustment():
    psd = PSDImage.open(full_name("clip-adjustment.psd"))
    assert len(psd) == 2
    layer = psd[0]
    assert layer.kind == "type"
    assert len(layer.clip_layers) == 1


def test_nested_clipping():
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


def test_clip_stack():
    """Check if consecutive clipping layers are correctly identified."""
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    psd[1][1].clipping = True
    assert psd[1][0].has_clip_layers()
    assert psd[1][1].clipping
    assert psd[1][2].clipping
    assert not psd[1][1].has_clip_layers()
    assert not psd[1][2].has_clip_layers()


def test_type_layer(type_layer):
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


def test_group_writable_properties(group):
    assert group.blend_mode == BlendMode.PASS_THROUGH
    group.blend_mode = BlendMode.SCREEN
    assert group.blend_mode == BlendMode.SCREEN


def test_group_extract_bbox():
    psd = PSDImage.open(full_name("hidden-groups.psd"))
    assert Group.extract_bbox(psd[1:], False) == (40, 72, 83, 134)
    assert Group.extract_bbox(psd[1:], True) == (25, 34, 83, 134)


def test_sibling_layers():
    psd = PSDImage.open(full_name("hidden-groups.psd"))
    assert psd[0].next_sibling() is psd[1]
    assert psd[1].previous_sibling() is psd[0]
    assert psd[0].next_sibling(visible=True) is psd[2]
    assert psd[2].previous_sibling(visible=True) is psd[0]
    assert psd[1][0].next_sibling() is None
    assert psd[1][0].previous_sibling() is None


def test_shape_and_fill_layer():
    psd = PSDImage.open(full_name("vector-mask2.psd"))
    for i in range(8):
        assert isinstance(psd[i], ShapeLayer)
    for i in range(8, 10):
        assert isinstance(psd[i], PixelLayer)


def test_has_effects():
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


def test_bbox_updates():
    psd = PSDImage.open(full_name("hidden-groups.psd"))
    group1 = psd[1]
    group1.visible = False
    assert group1.bbox == (0, 0, 0, 0)
    group1.visible = True
    assert group1.bbox == (25, 34, 80, 88)


def test_new_group(group):
    test_group = Group.new("Test Group", parent=group)

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

    test_group = Group.new("Test Group 2", open_folder=False)

    assert test_group._parent is None

    assert (
        test_group._record.tagged_blocks.get_data(Tag.SECTION_DIVIDER_SETTING).kind
        is SectionDivider.CLOSED_FOLDER
    )
    assert (
        test_group._bounding_record.tagged_blocks.get_data(
            Tag.SECTION_DIVIDER_SETTING
        ).kind
        is SectionDivider.BOUNDING_SECTION_DIVIDER
    )

    assert (
        test_group._record.tagged_blocks.get_data(Tag.UNICODE_LAYER_NAME)
        == "Test Group 2"
    )
    assert (
        test_group._bounding_record.tagged_blocks.get_data(Tag.UNICODE_LAYER_NAME)
        == "</Layer group>"
    )


def test_group_layers(
    group, pixel_layer, smartobject_layer, fill_layer, adjustment_layer
):
    pix_old_parent = pixel_layer._parent
    pix_old_psd = pixel_layer._psd

    test_group = Group.group_layers(
        [pixel_layer, smartobject_layer, fill_layer, adjustment_layer]
    )

    assert len(test_group) == 4

    assert test_group[0] is pixel_layer
    assert test_group[1] is smartobject_layer
    assert test_group[2] is fill_layer
    assert test_group[3] is adjustment_layer

    assert test_group[0]._parent is test_group
    assert test_group[1]._parent is test_group
    assert test_group[2]._parent is test_group
    assert test_group[3]._parent is test_group

    assert test_group._parent is pix_old_parent
    assert test_group._psd is pix_old_psd

    assert test_group._psd is not None
    assert test_group[0]._psd is not None

    test_group = Group.group_layers(
        [pixel_layer, smartobject_layer, fill_layer, adjustment_layer], parent=group
    )

    assert len(test_group) == 4

    assert test_group._parent is group
    assert test_group._psd is group._psd

    assert test_group._psd is not None
    assert test_group[0]._psd is not None


def test_pixel_layer_frompil():
    import PIL

    pil_rgb = PIL.Image.new("RGB", (30, 30))
    pil_rgb_a = PIL.Image.new("RGBA", (30, 30))
    pil_lab = PIL.Image.new("LAB", (30, 30))
    pil_grayscale_a = PIL.Image.new("LA", (30, 30))
    pil_grayscale = PIL.Image.new("L", (30, 30))
    pil_bitmap = PIL.Image.new("1", (30, 30))
    pil_cmyk = PIL.Image.new("CMYK", (30, 30))

    images = [
        pil_rgb,
        pil_rgb_a,
        pil_lab,
        pil_grayscale_a,
        pil_grayscale,
        pil_bitmap,
        pil_cmyk,
    ]
    layers = [PixelLayer.frompil(pil_im, None) for pil_im in images]

    for layer, image in zip(layers, images):
        # Bitmap image gets converted to grayscale during layer creation so we have to convert here too
        if image.mode == "1":
            image = image.convert("L")

        # CMYK Images needs to be inverted, for some reason
        if image.mode == "CMYK":
            from PIL import ImageChops

            image = ImageChops.invert(image)

        assert (
            len(layer._record.channel_info)
            == get_pil_channels(image.mode.rstrip("A")) + 1
        )
        assert len(layer._channels) == get_pil_channels(image.mode.rstrip("A")) + 1

        for channel in range(get_pil_channels(image.mode.rstrip("A"))):
            assert (
                layer._channels[channel + 1].get_data(
                    image.width, image.height, get_pil_depth(image.mode.rstrip("A"))
                )
                == image.getchannel(channel).tobytes()
            )


def test_layer_fill_opacity(pixel_layer):
    assert pixel_layer.fill_opacity == 255

    pixel_layer.fill_opacity = 128
    assert pixel_layer.fill_opacity == 128

    pixel_layer.fill_opacity = 0
    assert pixel_layer.fill_opacity == 0


def test_layer_reference_point(pixel_layer):
    assert pixel_layer.reference_point == (15.0, 15.0)

    pixel_layer.reference_point = (10.5, 20.5)
    assert pixel_layer.reference_point == (10.5, 20.5)

    with pytest.raises(ValueError, match=r".* sequence of two floats.*"):
        pixel_layer.reference_point = (10.5,)

    with pytest.raises(ValueError, match=r".* sequence of two floats.*"):
        pixel_layer.reference_point = (10.5, 20.5, 30.5)


def test_delete_layer(pixel_layer):
    pixel_layer.delete_layer()

    assert pixel_layer not in pixel_layer._parent


def test_move_to_group(group, pixel_layer):
    pix_old_parent = pixel_layer._parent

    pixel_layer.move_to_group(group)

    assert pixel_layer in group
    assert pixel_layer._parent is group
    assert pixel_layer._psd is group._psd

    assert pixel_layer not in pix_old_parent


def test_move_up(
    group, pixel_layer, type_layer, smartobject_layer, fill_layer, adjustment_layer
):
    test_group = Group.group_layers(
        [pixel_layer, smartobject_layer, fill_layer, adjustment_layer], parent=group
    )

    test_group.move_up(50)

    assert test_group._parent.index(test_group) == 0

    pixel_layer.move_up(2)

    assert test_group.index(smartobject_layer) == 0
    assert test_group.index(fill_layer) == 1
    assert test_group.index(pixel_layer) == 2
    assert test_group.index(adjustment_layer) == 3

    smartobject_layer.move_up(30)

    assert test_group.index(fill_layer) == 0
    assert test_group.index(pixel_layer) == 1
    assert test_group.index(adjustment_layer) == 2
    assert test_group.index(smartobject_layer) == 3


def test_move_down(
    group, pixel_layer, type_layer, smartobject_layer, fill_layer, adjustment_layer
):
    test_group = Group.group_layers(
        [pixel_layer, smartobject_layer, fill_layer, adjustment_layer], parent=group
    )

    test_group.move_up(50)

    assert test_group._parent.index(test_group) == 0

    fill_layer.move_down(2)

    assert test_group.index(fill_layer) == 0
    assert test_group.index(pixel_layer) == 1
    assert test_group.index(smartobject_layer) == 2
    assert test_group.index(adjustment_layer) == 3

    smartobject_layer.move_down(30)

    assert test_group.index(smartobject_layer) == 0
    assert test_group.index(fill_layer) == 1
    assert test_group.index(pixel_layer) == 2
    assert test_group.index(adjustment_layer) == 3


def test_append(group, pixel_layer):
    group.append(pixel_layer)

    assert pixel_layer in group
    assert pixel_layer._parent is group
    assert pixel_layer._psd is group._psd


def test_extend(group, pixel_layer, type_layer, smartobject_layer, fill_layer):
    group.extend([pixel_layer, type_layer, smartobject_layer, fill_layer])

    for layer in [pixel_layer, type_layer, smartobject_layer, fill_layer]:
        assert layer in group
        assert layer._parent is group
        assert layer._psd is group._psd


def test_insert(group, pixel_layer, type_layer, smartobject_layer, fill_layer):
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


def test_remove(group, pixel_layer, type_layer, smartobject_layer, fill_layer):
    group.extend([pixel_layer, type_layer, smartobject_layer])

    group.remove(pixel_layer)
    assert pixel_layer not in group

    group.remove(smartobject_layer)
    assert smartobject_layer not in group

    with pytest.raises(ValueError, match=r".* x not in list"):
        group.remove(pixel_layer)

    with pytest.raises(ValueError, match=r".* x not in list"):
        group.remove(fill_layer)


def test_pop(group, pixel_layer, type_layer, smartobject_layer, fill_layer):
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


def test_clear(group, pixel_layer, type_layer, smartobject_layer, fill_layer):
    group.extend([pixel_layer, type_layer, smartobject_layer, fill_layer])
    assert len(group) == 4

    group.clear()
    assert len(group) == 0


def test_index(group, pixel_layer, type_layer, smartobject_layer, fill_layer):
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


def test_count(group, pixel_layer, type_layer, smartobject_layer, fill_layer):
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

    group.append(pixel_layer)
    group.append(pixel_layer)
    group.append(pixel_layer)

    assert group.count(pixel_layer) == 3


def test_artboard_move(group):
    artboard = Artboard._move(group)

    assert artboard._channels is group._channels
    assert artboard._record is group._record
    assert artboard._bounding_channels is group._bounding_channels
    assert artboard._bounding_record is group._bounding_record


def test_lock_layer(pixel_layer):
    pixel_layer.lock(
        ProtectedFlags.TRANSPARENCY | ProtectedFlags.COMPOSITE | ProtectedFlags.POSITION
    )

    assert pixel_layer.locks.transparency
    assert pixel_layer.locks.composite
    assert pixel_layer.locks.position
    assert not pixel_layer.locks.nesting

    pixel_layer.lock(ProtectedFlags.NESTING)

    assert not pixel_layer.locks.transparency
    assert not pixel_layer.locks.composite
    assert not pixel_layer.locks.position
    assert pixel_layer.locks.nesting

    pixel_layer.unlock()

    assert pixel_layer.locks.value == 0

    pixel_layer.lock()

    assert pixel_layer.locks.complete
