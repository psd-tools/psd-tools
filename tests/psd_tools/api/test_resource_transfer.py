"""Patterns and linked smart objects follow a layer to another document (#1000)."""

import io
from typing import Any

import numpy as np
import pytest

from psd_tools.api._resources import ResourceTransfer
from psd_tools.api.layers import Layer, SmartObjectLayer, _layer_records
from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import Tag
from psd_tools.psd.descriptor import String
from psd_tools.psd.patterns import Patterns
from psd_tools.psd.tagged_blocks import TaggedBlock
from psd_tools.terminology import Enum, Key

from ..utils import full_name

PATTERN_TAGS = (Tag.PATTERNS1, Tag.PATTERNS2, Tag.PATTERNS3)
LINKED_TAGS = (
    Tag.LINKED_LAYER1,
    Tag.LINKED_LAYER2,
    Tag.LINKED_LAYER3,
    Tag.LINKED_LAYER_EXTERNAL,
)


def _patterns(psd: PSDImage) -> list[Any]:
    if psd.tagged_blocks is None:
        return []
    return [p for tag in PATTERN_TAGS for p in psd.tagged_blocks.get_data(tag) or []]


def _linked(psd: PSDImage) -> list[Any]:
    if psd.tagged_blocks is None:
        return []
    return [p for tag in LINKED_TAGS for p in psd.tagged_blocks.get_data(tag) or []]


def _pattern_ref(layer: Layer) -> String:
    """The ``Idnt`` string of the pattern a pattern-fill layer names."""
    block = layer._record.tagged_blocks.get_data(Tag.PATTERN_FILL_SETTING)
    ref = block[Enum.Pattern][Key.ID]
    assert isinstance(ref, String)
    return ref


def _pixels(layer: Layer) -> np.ndarray:
    pytest.importorskip("aggdraw")
    pytest.importorskip("scipy")
    image = layer.composite(force=True)
    assert image is not None
    return np.asarray(image)


def _pattern_source() -> tuple[PSDImage, Layer]:
    psd = PSDImage.open(full_name("layers/pattern-fill.psd"))
    return psd, psd[0]


def _smart_source() -> tuple[PSDImage, SmartObjectLayer]:
    psd = PSDImage.open(full_name("layers/smartobject-layer.psd"))
    layer = psd[0]
    assert isinstance(layer, SmartObjectLayer)
    return psd, layer


def test_copy_carries_the_pattern_a_layer_uses() -> None:
    source, layer = _pattern_source()
    dest = PSDImage.new("RGB", source.size)

    copy = layer.copy_to(dest)

    assert [p.pattern_id for p in _patterns(dest)] == [
        p.pattern_id for p in _patterns(source)
    ]
    assert _patterns(dest)[0] is not _patterns(source)[0]
    assert _patterns(dest)[0] == _patterns(source)[0]
    assert _pattern_ref(copy) == _pattern_ref(layer)
    np.testing.assert_array_equal(_pixels(copy), _pixels(layer))


def test_copy_carries_only_the_patterns_a_layer_uses() -> None:
    source = PSDImage.open(full_name("patterns.psd"))
    assert len(_patterns(source)) > 2
    counts = []
    for layer in source.descendants():
        dest = PSDImage.new("RGB", source.size)
        layer.copy_to(dest)
        counts.append(len(_patterns(dest)))

    assert max(counts) >= 1
    assert max(counts) < len(_patterns(source))


def test_a_pattern_the_destination_already_holds_is_not_duplicated() -> None:
    _source, layer = _pattern_source()
    dest = PSDImage.open(full_name("layers/pattern-fill.psd"))
    before = list(_patterns(dest))

    layer.copy_to(dest)

    assert _patterns(dest) == before


def test_a_clashing_pattern_id_is_remapped_with_its_format_kept() -> None:
    source, layer = _pattern_source()
    dest = PSDImage.open(full_name("layers/pattern-fill.psd"))
    dest_pattern = _patterns(dest)[0]
    dest_pattern.name = "unrelated"
    old = _pattern_ref(layer)

    copy = layer.copy_to(dest)

    new = _pattern_ref(copy)
    assert new != old and new.value.endswith("\x00")
    assert len(_patterns(dest)) == 2
    transferred = dest._get_pattern(new.value.rstrip("\x00"))
    assert transferred is not None
    assert transferred.name == _patterns(source)[0].name
    assert dest_pattern.pattern_id == old.value.rstrip("\x00")
    assert _pattern_ref(layer) == old
    np.testing.assert_array_equal(_pixels(copy), _pixels(layer))


@pytest.mark.parametrize("operation", ["extend", "group"])
def test_layers_sharing_a_clashing_pattern_share_one_transfer(operation: str) -> None:
    source, layer = _pattern_source()
    twin = layer.duplicate()
    dest = PSDImage.open(full_name("layers/pattern-fill.psd"))
    _patterns(dest)[0].name = "unrelated"

    if operation == "extend":
        dest.extend([layer, twin])
        copies = [layer, twin]
    else:
        group = source.create_group([layer, twin], name="G")
        copies = list(group.copy_to(dest))

    assert len(_patterns(dest)) == 2
    assert len({_pattern_ref(c).value for c in copies}) == 1


def test_a_move_carries_the_pattern_and_leaves_none_shared() -> None:
    source, layer = _pattern_source()
    dest = PSDImage.new("RGB", source.size)
    original = _patterns(source)[0]

    dest.append(layer)

    assert _patterns(dest)[0] == original
    assert _patterns(dest)[0] is not original


@pytest.mark.parametrize("tag", [Tag.PATTERNS2, Tag.PATTERNS3])
def test_a_pattern_keeps_the_tag_it_was_stored_under(tag: Tag) -> None:
    source, layer = _pattern_source()
    blocks = source.tagged_blocks
    assert blocks is not None
    data = blocks.get_data(Tag.PATTERNS1)
    del blocks[Tag.PATTERNS1]
    blocks.set_data(tag, data)
    dest = PSDImage.new("RGB", source.size)

    layer.copy_to(dest)

    assert dest.tagged_blocks is not None
    assert len(dest.tagged_blocks.get_data(tag)) == 1
    assert Tag.PATTERNS1 not in dest.tagged_blocks


def test_a_reference_the_source_cannot_resolve_is_left_alone() -> None:
    source, layer = _pattern_source()
    assert source.tagged_blocks is not None
    del source.tagged_blocks[Tag.PATTERNS1]
    dest = PSDImage.new("RGB", source.size)
    ref = _pattern_ref(layer)

    copy = layer.copy_to(dest)

    assert _pattern_ref(copy) == ref
    assert _patterns(dest) == []


def test_copy_carries_the_smart_object_data() -> None:
    source, layer = _smart_source()
    dest = PSDImage.new("RGB", source.size)

    copy = layer.copy_to(dest)

    assert copy.smart_object.unique_id == layer.smart_object.unique_id
    assert copy.smart_object.data == layer.smart_object.data
    assert copy.smart_object.filename == layer.smart_object.filename
    assert _linked(dest)[0] is not _linked(source)[0]
    assert layer.smart_object.data
    assert len(_linked(source)) == 1


def test_a_move_carries_the_smart_object_data() -> None:
    source, layer = _smart_source()
    expected = layer.smart_object.data
    original = _linked(source)[0]
    dest = PSDImage.new("RGB", source.size)

    dest.append(layer)

    assert layer.smart_object.data == expected
    assert layer.smart_object._data is _linked(dest)[0]
    assert layer.smart_object._data is not original


def test_a_clashing_smart_object_id_is_remapped() -> None:
    _source, layer = _smart_source()
    dest, other = _smart_source()
    forged = _linked(dest)[0]
    forged.filename = "forged.png"
    old = layer.smart_object.unique_id

    copy = layer.copy_to(dest)

    assert copy.smart_object.unique_id != old
    assert copy.smart_object.filename == layer.smart_object.filename
    assert other.smart_object.filename == "forged.png"
    assert len(_linked(dest)) == 2
    placed = copy._record.tagged_blocks.get_data(Tag.PLACED_LAYER2)
    assert placed.uuid.decode() == copy.smart_object.unique_id
    assert layer.smart_object.unique_id == old


def test_a_smart_object_the_destination_holds_is_not_duplicated() -> None:
    _source, layer = _smart_source()
    dest, _ = _smart_source()

    layer.copy_to(dest)

    assert len(_linked(dest)) == 1


def test_chained_copies_carry_resources_through_every_document() -> None:
    source, layer = _smart_source()
    b = PSDImage.new("RGB", source.size)
    c = PSDImage.new("RGB", source.size)

    layer.copy_to(b).copy_to(c)

    reopened = io.BytesIO()
    c.save(reopened)
    reopened.seek(0)
    copy = PSDImage.open(reopened)[0]
    assert isinstance(copy, SmartObjectLayer)
    assert copy.smart_object.data == layer.smart_object.data


def test_a_malformed_target_block_is_kept() -> None:
    source, layer = _pattern_source()
    dest = PSDImage.open(full_name("layers/pattern-fill.psd"))
    assert dest.tagged_blocks is not None
    del dest.tagged_blocks[Tag.PATTERNS1]
    dest.tagged_blocks[Tag.PATTERNS1] = TaggedBlock(key=Tag.PATTERNS1, data=b"\xff\xff")

    ResourceTransfer(dest).add(source, _layer_records(layer))

    assert dest.tagged_blocks is not None
    assert dest.tagged_blocks[Tag.PATTERNS1].data == b"\xff\xff"


def test_the_patterns_block_is_created_when_the_destination_has_none() -> None:
    _source, layer = _pattern_source()
    dest = PSDImage.open(full_name("2layers.psd"))
    assert not _patterns(dest)

    layer.copy_to(dest)

    assert dest.tagged_blocks is not None
    assert isinstance(dest.tagged_blocks.get_data(Tag.PATTERNS1), Patterns)


def test_a_clash_beside_a_malformed_target_block_does_not_bind_the_clashing_id() -> (
    None
):
    _source, layer = _pattern_source()
    dest = PSDImage.open(full_name("layers/pattern-fill.psd"))
    assert dest.tagged_blocks is not None
    unrelated = _patterns(dest)[0]
    unrelated.name = "unrelated"
    del dest.tagged_blocks[Tag.PATTERNS1]
    dest.tagged_blocks.set_data(Tag.PATTERNS2, [unrelated])
    dest.tagged_blocks[Tag.PATTERNS1] = TaggedBlock(key=Tag.PATTERNS1, data=b"\xff\xff")
    old = _pattern_ref(layer)

    copy = layer.copy_to(dest)

    assert _pattern_ref(copy).value.rstrip("\x00") != old.value.rstrip("\x00")
    assert dest.tagged_blocks[Tag.PATTERNS1].data == b"\xff\xff"
