"""A tagged block that failed to parse reads as missing, not as a crash."""

import contextlib
import io
import struct
from typing import Any

import pytest

from psd_tools import PSDImage
from psd_tools.api.layers import Artboard, ShapeLayer, SmartObjectLayer, TypeLayer
from psd_tools.api.shape import Stroke
from psd_tools.api.smart_object import SmartObject
from psd_tools.constants import Tag, TextType
from psd_tools.psd.engine_data import Integer, Property
from psd_tools.psd.tagged_blocks import TaggedBlock
from psd_tools.psd.vector import ClosedPath, Knot

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


def _patched_type_layers(filename: str, offset: int, value: int) -> list[TypeLayer]:
    data = bytearray(open(full_name(filename), "rb").read())
    data[offset] = value
    psd = PSDImage.open(io.BytesIO(data))
    layers = [x for x in psd.descendants() if isinstance(x, TypeLayer)]
    assert layers
    return layers


@pytest.mark.parametrize(
    "filename, offset, value",
    [
        ("clip-adjustment.psd", 21766, 0x07),
        ("transparency/fill-opacity.psd", 28844, 0x41),
        ("masks.psd", 57869, 0xDF),
    ],
)
def test_a_type_layer_with_unreadable_text_data_degrades(
    filename: str, offset: int, value: int
) -> None:
    for layer in _patched_type_layers(filename, offset, value):
        assert isinstance(layer.text, str)
        assert layer.text_type in (None, *TextType)
        layer.engine_dict, layer.resource_dict, layer.document_resources
        assert isinstance(layer.font_names, list)
        layer.typesetting


def test_a_type_layer_without_engine_data_has_empty_dicts() -> None:
    layers = _patched_type_layers("transparency/fill-opacity.psd", 28844, 0x41)
    for layer in layers:
        assert not layer.engine_dict
        assert not layer.resource_dict
        assert not layer.document_resources
        assert layer.text_type is None
        assert layer.font_names == []


def test_a_type_layer_without_text_has_empty_text() -> None:
    layers = _patched_type_layers("masks.psd", 57869, 0xDF)
    assert [layer.text for layer in layers].count("") >= 1


def _type_layer() -> TypeLayer:
    psd = PSDImage.open(full_name("clip-adjustment.psd"))
    return next(x for x in psd.descendants() if isinstance(x, TypeLayer))


def test_a_type_layer_with_a_non_string_text_has_empty_text() -> None:
    layer = _type_layer()
    layer._data.text_data[b"Txt "].value = 5
    assert layer.text == ""


def test_a_type_layer_with_a_scalar_engine_dict_degrades() -> None:
    layer = _type_layer()
    layer._data.text_data[b"EngineData"].value[Property("EngineDict")] = Integer(1)
    assert not layer.engine_dict
    assert layer.text_type is None


def _patched(filename: str, offset: int, value: int) -> PSDImage:
    data = bytearray(open(full_name(filename), "rb").read())
    data[offset] = value
    return PSDImage.open(io.BytesIO(data))


def _strokes(psd: PSDImage) -> list[Stroke]:
    strokes = [x.stroke for x in psd.descendants() if hasattr(x, "stroke") and x.stroke]
    assert strokes
    return strokes


def test_a_shape_with_an_unreadable_origination_bbox_uses_the_path() -> None:
    psd = _patched("masks/2.psd", 20034, 0x07)
    layers = [x for x in psd.descendants() if isinstance(x, ShapeLayer)]
    unreadable = [
        x
        for x in layers
        if x.has_origination() and any(o._read_bbox() is None for o in x.origination)
    ]
    assert unreadable
    for layer in unreadable:
        assert layer.vector_mask is not None
        box = layer.vector_mask.bbox
        assert layer.bbox == (
            round(box[0] * psd.width),
            round(box[1] * psd.height),
            round(box[2] * psd.width),
            round(box[3] * psd.height),
        )
        assert (0.0, 0.0, 0.0, 0.0) in [o.bbox for o in layer.origination]


def _patched_document(filename: str, patches: dict[int, int]) -> PSDImage:
    data = bytearray(open(full_name(filename), "rb").read())
    for offset, value in patches.items():
        data[offset] = value
    return PSDImage.open(io.BytesIO(data))


_NON_KNOT_PATCHES = [
    ("blend-modes/overlay.psd", {21747: 0x00, 21748: 0x00}),
    ("descriptors/stroke-color-descriptors-rgb.psd", {22157: 0x00, 22159: 0x01}),
]


@pytest.mark.parametrize("filename, patches", _NON_KNOT_PATCHES)
def test_a_vector_mask_with_non_knot_records_skips_them(
    filename: str, patches: dict[int, int]
) -> None:
    psd = _patched_document(filename, patches)
    masks = [x.vector_mask for x in psd.descendants() if x.vector_mask is not None]
    assert any(not isinstance(k, Knot) for m in masks for p in m.paths for k in p)
    for mask in masks:
        left, top, right, bottom = mask.bbox
        assert left <= right and top <= bottom


def test_a_vector_mask_bbox_ignores_non_knot_records() -> None:
    psd = _patched_document("blend-modes/overlay.psd", _NON_KNOT_PATCHES[0][1])
    layer = next(x for x in psd.descendants() if x.name == "Ellipse 3")
    assert layer.vector_mask is not None
    assert layer.vector_mask.bbox == pytest.approx(
        (0.125, 0.25, 0.875, 0.78033), abs=1e-5
    )


@pytest.mark.parametrize("filename, patches", _NON_KNOT_PATCHES)
def test_a_forced_composite_skips_non_knot_records(
    filename: str, patches: dict[int, int]
) -> None:
    if filename.startswith("descriptors/"):
        pytest.importorskip("aggdraw")
    psd = _patched_document(filename, patches)
    for layer in psd.descendants():
        if layer.kind == "shape":
            layer.composite(force=True)
    psd.composite(force=True)


def test_a_stroke_with_unreadable_line_width_defaults() -> None:
    psd = _patched("layers-minimal/shape-layer.psd", 22561, 0x00)
    assert [s.line_width for s in _strokes(psd)] == [1.0]


def test_a_stroke_with_unreadable_cap_type_defaults() -> None:
    psd = _patched("layers/shape-layer.psd", 21860, 0xFF)
    assert [s.line_cap_type for s in _strokes(psd)] == ["butt"]


def test_a_stroke_with_unreadable_join_type_defaults() -> None:
    psd = _patched("layers/shape-layer.psd", 21932, 0x03)
    assert [s.line_join_type for s in _strokes(psd)] == ["miter"]


def test_a_smart_object_with_an_unreadable_id_raises_value_error() -> None:
    psd = _patched("layers-minimal/smartobject-layer.psd", 22588, 0xF8)
    layer = next(x for x in psd.descendants() if isinstance(x, SmartObjectLayer))
    smart_object = layer.smart_object
    with pytest.raises(ValueError, match="identifier"):
        smart_object.unique_id
    with pytest.raises(ValueError):
        smart_object.data


def test_an_external_smart_object_without_full_path_falls_back_to_rel_path(
    tmp_path: Any,
) -> None:
    psd = _patched("placedLayer.psd", 85175, 0x00)
    layer = next(x for x in psd.descendants() if x.name == "linked-png")
    assert isinstance(layer, SmartObjectLayer)
    (tmp_path / "linked-layer.png").write_bytes(b"png")
    with layer.smart_object.open(external_dir=tmp_path) as f:
        assert f.read() == b"png"


def test_an_external_smart_object_without_any_path_raises_value_error() -> None:
    psd = PSDImage.open(full_name("placedLayer.psd"))
    layer = next(x for x in psd.descendants() if x.name == "linked-png")
    assert isinstance(layer, SmartObjectLayer)
    assert layer.smart_object._data is not None
    linked_file = layer.smart_object._data.linked_file
    for key in (b"fullPath", b"relPath"):
        del linked_file[key]
    with pytest.raises(ValueError, match="no readable path"):
        layer.smart_object.data


def test_a_forced_stroke_skips_non_knot_records() -> None:
    pytest.importorskip("aggdraw")
    psd = PSDImage.open(full_name("layers/shape-layer.psd"))
    layer = next(x for x in psd.descendants() if x.kind == "shape" and x.stroke)
    assert layer.vector_mask is not None
    layer.vector_mask.paths[0].insert(1, ClosedPath())
    layer.composite(force=True)
