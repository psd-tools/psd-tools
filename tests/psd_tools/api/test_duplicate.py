"""Layer duplication and serialization tests."""

from pathlib import Path
from uuid import UUID

import numpy as np
import pytest
from PIL import Image

from psd_tools import PSDImage
from psd_tools.api.layers import (
    Artboard,
    Group,
    Layer,
    ShapeLayer,
    SmartObjectLayer,
    TypeLayer,
)
from psd_tools.constants import BlendMode, Resource, Tag
from psd_tools.psd.image_resources import ImageResource, Integer
from psd_tools.psd.tagged_blocks import TaggedBlock

from tests.conftest import skip_without_composite

from ..utils import full_name


@pytest.mark.parametrize(
    "filename",
    [
        "layers/pixel-layer.psd",
        "layers/type-layer.psd",
        "layers/shape-layer.psd",
        "layers/smartobject-layer.psd",
        "layers/brightness-contrast.psd",
        "layers/solid-color-fill.psd",
        "layers/gradient-fill.psd",
        "layers/pattern-fill.psd",
        "layers/group.psd",
        "artboard.psd",
    ],
)
def test_duplicate_preserves_layer_type_and_data(filename: str) -> None:
    psd = PSDImage.open(full_name(filename))
    source = psd[0]
    original_layers = list(psd)
    original_ids = [layer.layer_id for layer in psd.descendants()]
    source_bytes = source._record.tobytes()
    channel_bytes = source._channels.tobytes()
    duplicate = source.duplicate()

    assert type(duplicate) is type(source)
    assert duplicate is not source
    assert list(psd) == [source, duplicate, *original_layers[1:]]
    assert duplicate.parent is psd
    assert duplicate._psd is psd
    assert duplicate.name == source.name
    assert duplicate.bbox == source.bbox
    assert duplicate.opacity == source.opacity
    assert duplicate.visible == source.visible
    assert duplicate.blend_mode == source.blend_mode
    assert duplicate.clipping == source.clipping
    assert duplicate._channels.tobytes() == channel_bytes
    assert source._record.tobytes() == source_bytes
    assert duplicate._record is not source._record
    assert duplicate._record.flags is not source._record.flags
    assert duplicate._record.tagged_blocks is not source._record.tagged_blocks
    assert duplicate._channels is not source._channels
    assert all(a is not b for a, b in zip(duplicate._channels, source._channels))
    assert duplicate.layer_id > 0
    assert duplicate.layer_id not in original_ids
    assert psd.is_updated()

    duplicate.name = "Copy"
    duplicate.visible = not source.visible
    duplicate.opacity = 73
    duplicate.blend_mode = BlendMode.MULTIPLY
    assert source._record.tobytes() == source_bytes


def test_duplicate_pixel_and_mask_edits_are_independent() -> None:
    psd = PSDImage.new("RGB", (8, 8))
    source = psd.create_pixel_layer(Image.new("RGB", (4, 4), "red"))
    source.create_mask(Image.new("L", (4, 4), 128))
    mask = source.mask
    pixels = source.topil().tobytes()  # type: ignore[union-attr]
    duplicate = source.duplicate(name="独立副本")
    assert duplicate.name == "独立副本"
    assert duplicate.mask is not mask
    assert duplicate.mask is not None and mask is not None
    assert duplicate.mask._layer is duplicate
    assert duplicate.mask._data is duplicate._record.mask_data
    assert duplicate.mask.topil().tobytes() == mask.topil().tobytes()  # type: ignore[union-attr]

    duplicate.mask.disabled = True
    duplicate.update_mask(Image.new("L", (4, 4), 255))
    duplicate._channels[1].data = bytes(len(duplicate._channels[1].data))
    duplicate.offset = (3, 2)
    assert not mask.disabled
    assert mask.topil().getextrema() == (128, 128)  # type: ignore[union-attr]
    assert source.topil().tobytes() == pixels  # type: ignore[union-attr]
    assert source.offset == (0, 0)


def test_duplicate_nested_group_and_divider_records() -> None:
    psd = PSDImage.new("RGB", (10, 10))
    group = psd.create_group(name="Root")
    nested = Group.new(group, name="Nested")
    pixel = psd.create_pixel_layer(Image.new("RGB", (2, 2), "red"))
    nested.append(pixel)
    pixel.clipping = True
    nested.visible = False
    group.tagged_blocks.set_data(Tag.LAYER_ID, 1)
    nested.tagged_blocks.set_data(Tag.LAYER_ID, 3)
    pixel.tagged_blocks.set_data(Tag.LAYER_ID, 9)
    assert group._bounding_record is not None
    group._bounding_record.tagged_blocks.set_data(Tag.LAYER_ID, 2)
    duplicate = group.duplicate(name="Root copy")

    assert len(group) == len(duplicate) == 1
    assert duplicate[0] is not nested
    assert isinstance(duplicate[0], Group)
    assert duplicate[0].parent is duplicate
    assert duplicate[0][0].parent is duplicate[0]
    assert duplicate[0][0] is not pixel
    assert duplicate[0][0].clipping
    assert not duplicate[0].visible
    assert duplicate._bounding_record is not group._bounding_record
    assert duplicate._bounding_channels is not group._bounding_channels
    assert duplicate._bounding_record is not None
    clone_ids = [duplicate.layer_id, *(x.layer_id for x in duplicate.descendants())]
    clone_ids.append(duplicate._bounding_record.tagged_blocks.get_data(Tag.LAYER_ID))
    assert len(set(clone_ids)) == len(clone_ids)
    assert min(clone_ids) == 10
    assert psd.image_resources.get_data(Resource.IDS_SEED_NUMBER) == max(clone_ids)
    duplicate[0][0].name = "Changed"
    duplicate[0].append(psd.create_pixel_layer(Image.new("RGB", (1, 1))))
    assert pixel.name != "Changed"
    assert len(nested) == 1


@pytest.mark.parametrize("index", [None, 0, 1, -1, -2])
def test_duplicate_destination_and_index(index: int | None) -> None:
    psd = PSDImage.new("RGB", (8, 8))
    source = psd.create_pixel_layer(Image.new("RGB", (2, 2)), name="Source")
    destination = psd.create_group()
    first = psd.create_pixel_layer(Image.new("RGB", (1, 1)), name="First")
    destination.append(first)
    expected: list[Layer] = [first]
    duplicate = source.duplicate(destination, index=index)
    target = len(expected) if index is None else index % (len(expected) + 1)
    expected.insert(target, duplicate)
    assert list(destination) == expected
    assert destination.index(duplicate) == target
    assert duplicate.parent is destination
    assert source.parent is psd
    assert source in psd


def test_duplicate_into_source_descendant_is_finite() -> None:
    psd = PSDImage.new("RGB", (8, 8))
    source = psd.create_group()
    descendant = Group.new(source)
    duplicate = source.duplicate(descendant)
    assert list(descendant) == [duplicate]
    assert len(duplicate) == 1
    assert isinstance(duplicate[0], Group)
    assert len(duplicate[0]) == 0
    assert len(list(psd.descendants())) == 4


def test_duplicate_detached_source() -> None:
    psd = PSDImage.open(full_name("layers/pixel-layer.psd"))
    source = psd.pop()
    with pytest.raises(ValueError, match="detached"):
        source.duplicate()
    duplicate = source.duplicate(psd)
    assert list(psd) == [duplicate]
    assert source.parent is None
    assert duplicate.layer_id != source.layer_id


def test_duplicate_repeatedly_allocates_unique_ids() -> None:
    psd = PSDImage.open(full_name("layers/group.psd"))
    source = psd[0]
    first = source.duplicate()
    second = first.duplicate()
    assert isinstance(first, Group) and isinstance(second, Group)
    copies = [first, *first.descendants(), second, *second.descendants()]
    ids = [layer.layer_id for layer in copies]
    assert len(set(ids)) == len(ids)
    assert all(layer_id > 0 for layer_id in ids)


def test_duplicate_into_hidden_group_invalidates_cached_bounds() -> None:
    psd = PSDImage.new("RGB", (8, 8))
    source = psd.create_group()
    pixel = psd.create_pixel_layer(Image.new("RGB", (2, 2)), left=2, top=3)
    source.append(pixel)
    destination = psd.create_group()
    destination.visible = False
    assert source.bbox == psd.bbox == (2, 3, 4, 5)
    assert destination.bbox == (0, 0, 0, 0)
    duplicate = source.duplicate(destination)
    assert duplicate.bbox == (0, 0, 0, 0)
    assert source.bbox == psd.bbox == (2, 3, 4, 5)
    destination.visible = True
    assert duplicate.bbox == destination.bbox == (2, 3, 4, 5)


@pytest.mark.parametrize(
    "kwargs, error",
    [
        ({"parent": object()}, TypeError),
        ({"index": 1.5}, TypeError),
        ({"index": "0"}, TypeError),
        ({"index": -3}, IndexError),
        ({"index": 2}, IndexError),
        ({"index": -100}, IndexError),
        ({"index": 100}, IndexError),
        ({"name": 123}, TypeError),
        ({"name": "a" * 256}, ValueError),
    ],
)
def test_duplicate_validation_is_atomic(kwargs: dict, error: type[Exception]) -> None:
    psd = PSDImage.open(full_name("layers/pixel-layer.psd"))
    source = psd[0]
    records = psd._record.tobytes()
    with pytest.raises(error):
        source.duplicate(**kwargs)
    assert list(psd) == [source]
    assert source.parent is psd
    assert psd._record.tobytes() == records
    assert not psd.is_updated()


def test_duplicate_rejects_another_document() -> None:
    source_psd = PSDImage.open(full_name("layers/pixel-layer.psd"))
    destination_psd = PSDImage.new("RGB", (8, 8))
    group = destination_psd.create_group()
    with pytest.raises(ValueError, match="another document"):
        source_psd[0].duplicate(group)
    assert len(source_psd) == 1
    assert len(group) == 0
    assert not source_psd.is_updated()


@pytest.mark.parametrize("index", [None, 1, -3])
@pytest.mark.parametrize("group_base", [False, True])
def test_duplicate_clip_base_releases_clipped_layers(
    index: int | None, group_base: bool
) -> None:
    psd = PSDImage.new("RGB", (8, 8))
    base = (
        psd.create_group()
        if group_base
        else psd.create_pixel_layer(Image.new("RGB", (2, 2)))
    )
    clips = [psd.create_pixel_layer(Image.new("RGB", (2, 2))) for _ in range(2)]
    for layer in clips:
        layer.clipping = True
    assert base.clip_layers == clips
    copy = base.duplicate(index=index)
    assert list(psd) == [base, copy, *clips]
    assert not any(layer.clipping for layer in clips)
    assert not base.clip_layers and not copy.clip_layers


def test_duplicate_clipped_layer_preserves_clipping() -> None:
    psd = PSDImage.new("RGB", (8, 8))
    base, first, second = [
        psd.create_pixel_layer(Image.new("RGB", (2, 2))) for _ in range(3)
    ]
    first.clipping = second.clipping = True
    copy = first.duplicate()
    assert list(psd) == [base, first, copy, second]
    assert copy.clipping and first.clipping and second.clipping
    assert base.clip_layers == [first, copy, second]


@pytest.mark.parametrize("other_parent", [False, True])
def test_duplicate_clip_base_elsewhere_preserves_clipping(other_parent: bool) -> None:
    psd = PSDImage.new("RGB", (8, 8))
    base = psd.create_pixel_layer(Image.new("RGB", (2, 2)))
    clip = psd.create_pixel_layer(Image.new("RGB", (2, 2)))
    clip.clipping = True
    destination = psd.create_group() if other_parent else psd
    base.duplicate(destination, index=0)
    assert clip.clipping
    assert base.clip_layers == [clip]


def test_duplicate_artboard_rejects_group_destination_without_mutation() -> None:
    psd = PSDImage.open(full_name("artboard.psd"))
    source = next(layer for layer in psd if isinstance(layer, Artboard))
    destination = psd.create_group()
    before = psd._record.tobytes()
    with pytest.raises(ValueError, match="document root"):
        source.duplicate(destination)
    assert psd._record.tobytes() == before
    assert len(destination) == 0


@pytest.mark.parametrize("seed", [0, 4, 100, 0x7FFFFFFF])
def test_duplicate_advances_id_seed(seed: int, tmp_path: Path) -> None:
    psd = PSDImage.open(full_name("layers/smartobject-layer.psd"))
    source = psd[0]
    psd.image_resources[Resource.IDS_SEED_NUMBER] = ImageResource(
        key=Resource.IDS_SEED_NUMBER,
        data=Integer(seed),  # type: ignore[arg-type]
    )
    expected = max(seed, source.layer_id) + 1
    copy = source.duplicate()
    assert copy.layer_id == expected
    assert (
        psd.image_resources.get_data(Resource.IDS_SEED_NUMBER) & 0xFFFFFFFF == expected
    )
    psd.remove(copy)
    copy = source.duplicate()
    assert copy.layer_id == expected + 1
    path = tmp_path / "seed.psd"
    psd.save(path)
    saved = PSDImage.open(path)
    assert (
        saved.image_resources.get_data(Resource.IDS_SEED_NUMBER) & 0xFFFFFFFF
        == expected + 1
    )
    assert saved[0].duplicate().layer_id == expected + 2


def test_duplicate_id_exhaustion_is_atomic() -> None:
    psd = PSDImage.open(full_name("layers/pixel-layer.psd"))
    source = psd[0]
    source.tagged_blocks.set_data(Tag.LAYER_ID, 0xFFFFFFFF)
    before = psd._record.tobytes()
    with pytest.raises(ValueError, match="No unused layer IDs"):
        source.duplicate()
    assert psd._record.tobytes() == before
    assert list(psd) == [source]
    assert not psd.is_updated()


@pytest.mark.parametrize("nested", [False, True])
def test_duplicate_smart_object_instance_id(nested: bool, tmp_path: Path) -> None:
    psd = PSDImage.open(full_name("layers/smartobject-layer.psd"))
    source = psd[0]
    config = source.tagged_blocks.get_data(Tag.SMART_OBJECT_LAYER_DATA1)
    original_instance = config.data[b"placed"].value
    original_content = config.data[b"Idnt"].value
    if nested:
        group = psd.create_group([source])
        duplicate = group.duplicate()[0]
    else:
        duplicate = source.duplicate()
    duplicate.name = "Smart copy"
    data = duplicate.tagged_blocks.get_data(Tag.SMART_OBJECT_LAYER_DATA1).data
    assert data[b"Idnt"].value == original_content
    assert data[b"placed"].value != original_instance
    assert UUID(data[b"placed"].value).version == 4
    assert config.data[b"placed"].value == original_instance
    path = tmp_path / "instance.psd"
    psd.save(path)
    saved = PSDImage.open(path).find("Smart copy")
    assert saved is not None
    saved_data = saved.tagged_blocks.get_data(Tag.SMART_OBJECT_LAYER_DATA1).data
    assert saved_data[b"placed"] == data[b"placed"]
    assert saved_data[b"Idnt"].value == original_content


def test_duplicate_uses_fresh_type_shape_and_smart_object_wrappers() -> None:
    psd = PSDImage.open(full_name("layers/type-layer.psd"))
    source = psd[0]
    assert isinstance(source, TypeLayer)
    typesetting = source.typesetting
    text = source.text
    duplicate = source.duplicate()
    assert duplicate.typesetting is not typesetting
    assert duplicate._data is duplicate.tagged_blocks.get_data(
        Tag.TYPE_TOOL_OBJECT_SETTING
    )
    duplicate._data.text_data[b"Txt "].value = "Changed"
    assert duplicate.text == "Changed"
    assert source.text == text

    psd = PSDImage.open(full_name("layers/shape-layer.psd"))
    shape = psd[0]
    assert isinstance(shape, ShapeLayer)
    vector_mask = shape.vector_mask
    shape_copy = shape.duplicate()
    assert vector_mask is not None
    assert shape_copy.vector_mask is not vector_mask
    assert shape_copy.vector_mask is not None
    assert shape_copy.vector_mask.bbox == vector_mask.bbox

    psd = PSDImage.open(full_name("layers/smartobject-layer.psd"))
    smart = psd[0]
    assert isinstance(smart, SmartObjectLayer)
    smart_object = smart.smart_object
    smart_copy = smart.duplicate()
    assert smart_copy.smart_object is not smart_object
    assert smart_copy.smart_object._config is not smart_object._config
    assert smart_copy.smart_object._data is smart_object._data
    assert smart_copy.smart_object.unique_id == smart_object.unique_id


def test_duplicate_retains_unknown_tagged_blocks() -> None:
    psd = PSDImage.open(full_name("layers/pixel-layer.psd"))
    source = psd[0]
    source.tagged_blocks[b"TEST"] = TaggedBlock(key=b"TEST", data=b"opaque payload")
    duplicate = source.duplicate()
    assert duplicate.tagged_blocks[b"TEST"].data == b"opaque payload"
    assert duplicate.tagged_blocks[b"TEST"] is not source.tagged_blocks[b"TEST"]
    duplicate.tagged_blocks[b"TEST"].data = b"edited"
    assert source.tagged_blocks[b"TEST"].data == b"opaque payload"


@pytest.mark.parametrize(
    "filename",
    [
        "layers/type-layer.psd",
        "layers/shape-layer.psd",
        "layers/smartobject-layer.psd",
        "layers/brightness-contrast.psd",
        "layers/solid-color-fill.psd",
        "layers/gradient-fill.psd",
        "layers/pattern-fill.psd",
    ],
)
@pytest.mark.composite
@skip_without_composite
def test_duplicate_special_layer_roundtrip(filename: str, tmp_path: Path) -> None:
    psd = PSDImage.open(full_name(filename))
    source = psd[0]
    duplicate = source.duplicate(name="Saved copy")
    path = tmp_path / "copy.psd"
    psd.save(path)
    reopened = PSDImage.open(path)
    copy = reopened[1]
    assert type(copy) is type(source)
    assert copy.name == "Saved copy"
    assert copy.layer_id == duplicate.layer_id
    assert copy.layer_id != reopened[0].layer_id
    assert copy._channels.tobytes() == source._channels.tobytes()
    if isinstance(source, TypeLayer):
        assert isinstance(copy, TypeLayer)
        assert copy.text == source.text
    if isinstance(source, SmartObjectLayer):
        assert isinstance(copy, SmartObjectLayer)
        assert copy.smart_object.unique_id == source.smart_object.unique_id
        with source.smart_object.open() as original, copy.smart_object.open() as saved:
            assert original.read() == saved.read()


@pytest.mark.parametrize(
    "filename", ["clipping-mask.psd", "clipping-mask.psb", "artboard.psd"]
)
@pytest.mark.composite
@skip_without_composite
def test_duplicate_group_roundtrip(filename: str, tmp_path: Path) -> None:
    psd = PSDImage.open(full_name(filename))
    source = next(layer for layer in psd if isinstance(layer, Group))
    duplicate = source.duplicate(name="Saved copy")
    expected = list(duplicate.descendants())
    path = tmp_path / Path(filename).name
    psd.save(path)
    reopened = PSDImage.open(path)
    copy = reopened.find("Saved copy")
    assert isinstance(copy, type(source))
    assert isinstance(copy, Group)
    if isinstance(source, Artboard):
        assert copy.bbox == duplicate.bbox
    actual = list(copy.descendants())
    assert len(actual) == len(expected)
    for layer, original in zip(actual, expected):
        assert type(layer) is type(original)
        assert layer.name == original.name
        assert layer.layer_id == original.layer_id
        assert layer.clipping == original.clipping
        assert layer.visible == original.visible
        assert layer._channels.tobytes(
            version=reopened.version
        ) == original._channels.tobytes(version=psd.version)


@pytest.mark.parametrize(
    "filename",
    [
        "mask.psd",
        "mask.psb",
        "16bit5x5.psd",
        "16bit5x5.psb",
        "32bit5x5.psd",
        "32bit5x5.psb",
    ],
)
@pytest.mark.composite
@skip_without_composite
def test_duplicate_channel_roundtrip(filename: str, tmp_path: Path) -> None:
    psd = PSDImage.open(full_name(filename))
    source = next(layer for layer in psd.descendants() if not isinstance(layer, Group))
    pixels = source.numpy()
    duplicate = source.duplicate(name="Saved copy")
    path = tmp_path / Path(filename).name
    psd.save(path)
    reopened = PSDImage.open(path)
    copy = reopened.find("Saved copy")
    assert copy is not None
    assert type(copy) is type(source)
    assert copy.layer_id == duplicate.layer_id
    assert reopened.depth == psd.depth
    np.testing.assert_array_equal(copy.numpy(), pixels)
    np.testing.assert_array_equal(source.numpy(), pixels)
    if source.mask is not None:
        assert copy.mask is not None
        assert copy.mask.bbox == source.mask.bbox
        assert copy.mask.topil().tobytes() == source.mask.topil().tobytes()  # type: ignore[union-attr]
