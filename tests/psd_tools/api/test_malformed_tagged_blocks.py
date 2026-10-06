"""A tagged block that failed to parse reads as missing, not as a crash."""

import contextlib
import io
import struct
from typing import Any

import pytest

from psd_tools import PSDImage
from psd_tools.api.layers import Artboard, SmartObjectLayer, TypeLayer
from psd_tools.api.smart_object import SmartObject
from psd_tools.constants import Tag
from psd_tools.psd.tagged_blocks import TaggedBlock

from ..utils import full_name


def _corrupt(psd: PSDImage, tag: Tag) -> None:
    """Replace every parsed ``tag`` block with the bytes a failed parse leaves."""
    all_blocks: list[Any] = [layer._record.tagged_blocks for layer in psd.descendants()]
    all_blocks.append(psd.tagged_blocks)
    count = 0
    for blocks in all_blocks:
        if blocks is not None and tag in blocks:
            blocks[tag].data = b"\xff\xff"
            count += 1
    assert count


@pytest.mark.parametrize(
    "fixture, tag",
    [
        ("adjustment-fillers.psd", Tag.SOLID_COLOR_SHEET_SETTING),
        ("adjustment-fillers.psd", Tag.GRADIENT_FILL_SETTING),
        ("adjustment-fillers.psd", Tag.PATTERN_FILL_SETTING),
        ("adjustment-fillers.psd", Tag.PATTERNS1),
        ("adjustment-fillers.psd", Tag.VECTOR_STROKE_DATA),
        ("adjustment-fillers.psd", Tag.VECTOR_ORIGINATION_DATA),
        ("adjustment-fillers.psd", Tag.TYPE_TOOL_OBJECT_SETTING),
        ("advanced-blending.psd", Tag.VECTOR_MASK_SETTING1),
        ("advanced-blending.psd", Tag.OBJECT_BASED_EFFECTS_LAYER_INFO),
        ("opacity-fill.psd", Tag.BLEND_FILL_OPACITY),
        ("blend-modes/cmyk-blend-modes.psd", Tag.LINKED_LAYER2),
        ("blend-modes/cmyk-blend-modes.psd", Tag.SMART_OBJECT_LAYER_DATA1),
        ("blend-modes/cmyk-blend-modes.psd", Tag.PLACED_LAYER2),
    ],
)
def test_a_malformed_block_does_not_break_rendering(fixture: str, tag: Tag) -> None:
    pytest.importorskip("aggdraw")
    pytest.importorskip("scipy")
    psd = PSDImage.open(full_name(fixture))
    _corrupt(psd, tag)
    for layer in psd.descendants():
        layer.bbox
        layer.composite()
        if isinstance(layer, SmartObjectLayer):
            with contextlib.suppress(ValueError):
                layer.smart_object
    psd.composite()


def _document(layer_block: bytes) -> io.BytesIO:
    header = b"8BPS" + struct.pack(">H", 1) + b"\0" * 6
    header += struct.pack(">HIIHH", 3, 4, 4, 8, 3)
    section = struct.pack(">I", 0) + layer_block
    layers = struct.pack(">I", len(section)) + section
    image = struct.pack(">H", 0) + b"\x80" * 48
    return io.BytesIO(header + struct.pack(">I", 0) * 2 + layers + image)


@pytest.mark.parametrize("key", [b"Lr16", b"Lr32"])
def test_a_malformed_layer_block_raises_on_open(key: bytes) -> None:
    body = b"\xff" * 4
    block = b"8BIM" + key + struct.pack(">I", len(body)) + body
    with pytest.raises((OSError, ValueError)):
        PSDImage.open(_document(block))


def test_a_type_layer_without_parsed_data_raises_value_error() -> None:
    pytest.importorskip("aggdraw")
    pytest.importorskip("scipy")
    psd = PSDImage.open(full_name("adjustment-fillers.psd"))
    _corrupt(psd, Tag.TYPE_TOOL_OBJECT_SETTING)
    buffer = io.BytesIO()
    psd.save(buffer)
    buffer.seek(0)

    reopened = PSDImage.open(buffer)
    type_layers = [x for x in reopened.descendants() if isinstance(x, TypeLayer)]
    assert type_layers
    for layer in type_layers:
        for name in ("text", "transform", "warp", "engine_dict", "typesetting"):
            with pytest.raises(ValueError):
                getattr(layer, name)
        layer.bbox
        layer.composite()


@pytest.mark.parametrize(
    "first, second, attribute",
    [
        (Tag.SMART_OBJECT_LAYER_DATA1, Tag.SMART_OBJECT_LAYER_DATA2, "_config"),
        (Tag.PLACED_LAYER1, Tag.PLACED_LAYER2, "_placed_layer"),
    ],
)
def test_a_malformed_smart_object_block_does_not_shadow_the_fallback(
    first: Tag, second: Tag, attribute: str
) -> None:
    psd = PSDImage.open(full_name("blend-modes/cmyk-blend-modes.psd"))
    layer = next(
        x
        for x in psd.descendants()
        if isinstance(x, SmartObjectLayer)
        and (first in x.tagged_blocks or second in x.tagged_blocks)
    )
    blocks = layer._record.tagged_blocks
    expected = blocks[first if first in blocks else second].data
    blocks[second] = TaggedBlock(key=second, data=expected)
    blocks[first] = TaggedBlock(key=first, data=b"\xff\xff")

    assert getattr(SmartObject(layer), attribute) is expected


def test_moving_a_layer_tolerates_a_malformed_pattern_block() -> None:
    source = PSDImage.open(full_name("adjustment-fillers.psd"))
    _corrupt(source, Tag.PATTERNS1)
    target = PSDImage.new("RGB", (30, 30))
    target.append(source[0])
    assert target[0]._psd is target


def test_copying_patterns_keeps_a_malformed_target_block() -> None:
    source = PSDImage.open(full_name("adjustment-fillers.psd"))
    target = PSDImage.open(full_name("adjustment-fillers.psd"))
    _corrupt(target, Tag.PATTERNS1)
    source._copy_patterns(target)
    assert target.tagged_blocks is not None
    assert target.tagged_blocks[Tag.PATTERNS1].data == b"\xff\xff"


def test_a_malformed_later_artboard_block_does_not_hide_a_valid_one() -> None:
    psd = PSDImage.open(full_name("advanced-blending.psd"))
    artboard = next(x for x in psd.descendants() if isinstance(x, Artboard))
    blocks = artboard._record.tagged_blocks
    expected = artboard.bbox
    valid = next(
        k
        for k in (Tag.ARTBOARD_DATA1, Tag.ARTBOARD_DATA2, Tag.ARTBOARD_DATA3)
        if k in blocks
    )
    later = Tag.ARTBOARD_DATA3 if valid != Tag.ARTBOARD_DATA3 else Tag.ARTBOARD_DATA2
    blocks[later] = TaggedBlock(key=later, data=b"\xff\xff")
    artboard._bbox = None

    assert artboard.bbox == expected
    artboard._artboard_background_defaults()


def test_a_malformed_first_effects_block_does_not_hide_a_valid_one() -> None:
    psd = PSDImage.open(full_name("advanced-blending.psd"))
    layer = next(
        x
        for x in psd.descendants()
        if Tag.OBJECT_BASED_EFFECTS_LAYER_INFO in x.tagged_blocks and x.effects.enabled
    )
    blocks = layer._record.tagged_blocks
    expected = len(list(layer.effects))
    assert expected
    blocks[Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V0] = blocks[
        Tag.OBJECT_BASED_EFFECTS_LAYER_INFO
    ]
    blocks[Tag.OBJECT_BASED_EFFECTS_LAYER_INFO] = TaggedBlock(
        key=Tag.OBJECT_BASED_EFFECTS_LAYER_INFO, data=b"\xff\xff"
    )

    assert len(list(layer.effects)) == expected
