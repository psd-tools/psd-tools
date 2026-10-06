"""A tagged block that failed to parse reads as missing, not as a crash."""

import contextlib
import io
import struct
from typing import Any

import pytest

from psd_tools import PSDImage
from psd_tools.api.layers import SmartObjectLayer, TypeLayer
from psd_tools.constants import Tag

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
