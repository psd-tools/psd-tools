import io
import logging
import struct
from typing import Any

import pytest

from psd_tools.constants import LinkedLayerType, Tag
from psd_tools.psd import PSD
from psd_tools.psd.descriptor import DescriptorBlock
from psd_tools.psd.linked_layer import LinkedLayer, LinkedLayers
from psd_tools.psd.tagged_blocks import TaggedBlock

from ..utils import check_read_write, check_write_read, full_name

logger = logging.getLogger(__name__)

LINKED_TAGS = (Tag.LINKED_LAYER1, Tag.LINKED_LAYER2, Tag.LINKED_LAYER3)


def _unicode(text: str) -> bytes:
    return struct.pack(">I", len(text)) + text.encode("utf-16-be")


CONTENT_ID = "09fa029c-5678-144b-ac0b-0bf317151bde\x00"

# A version 8 entry as Photoshop writes it for an embedded smart object: the
# version 7 fields, then a descriptor holding a contentID.
V8_DATA_ENTRY = (
    b"liFD"
    + struct.pack(">I", 8)
    + b"\x24a4041d1d-df72-8b45-be8f-9f022e23f5ec"
    + _unicode("smart_object.ai\x00")
    + b"PDF ART5"
    + struct.pack(">QB", 4, 0)
    + b"\x01\x02\x03\x04"
    + _unicode("uuid:2c48394e-dad7-4f05-8977-c2004f54380e\x00")
    + struct.pack(">dB", 0.0, 0)
    + struct.pack(">I", 16)
    + _unicode("\x00")
    + struct.pack(">I", 0)
    + b"null"
    + struct.pack(">I", 1)
    + struct.pack(">I", 9)
    + b"contentIDTEXT"
    + _unicode(CONTENT_ID)
)


def test_linked_layer_v8_keeps_content_descriptor() -> None:
    check_read_write(LinkedLayer, V8_DATA_ENTRY)
    descriptor = LinkedLayer.frombytes(V8_DATA_ENTRY).content_descriptor
    assert descriptor is not None
    assert descriptor[b"contentID"].value == CONTENT_ID


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"kind": LinkedLayerType.DATA, "data": b"\x01\x02\x03\x04"},
        {"kind": LinkedLayerType.ALIAS},
        {
            "kind": LinkedLayerType.EXTERNAL,
            "data": None,
            "filesize": 4,
            "linked_file": DescriptorBlock(),
            "version": 1,
        },
        {
            "kind": LinkedLayerType.EXTERNAL,
            "data": b"\x01\x02\x03\x04",
            "filesize": 4,
            "linked_file": DescriptorBlock(),
            "version": 2,
        },
        {
            "kind": LinkedLayerType.EXTERNAL,
            "data": b"\x01\x02\x03\x04",
            "filesize": 4,
            "linked_file": DescriptorBlock(),
            "version": 3,
        },
        {
            "kind": LinkedLayerType.EXTERNAL,
            "data": b"\x01\x02\x03\x04",
            "filesize": 4,
            "linked_file": DescriptorBlock(),
            "version": 7,
            "timestamp": (2000, 1, 1, 0, 0, 0.0),
            "child_id": "",
            "mod_time": 200000.1,
            "lock_state": 1,
            "open_file": DescriptorBlock(),
        },
    ],
)
def test_linked_layer_wr(kwargs: dict[str, Any]) -> None:
    check_write_read(LinkedLayer(**kwargs))


def test_linked_layers_wr() -> None:
    linked_layers = LinkedLayers(
        [
            LinkedLayer(),  # type: ignore[list-item]
            LinkedLayer(kind=LinkedLayerType.DATA, data=b"\x01\x02\x03\x04"),  # type: ignore[list-item]
            LinkedLayer(kind=LinkedLayerType.ALIAS),  # type: ignore[list-item]
            LinkedLayer(  # type: ignore[list-item]
                kind=LinkedLayerType.EXTERNAL,
                data=None,
                filesize=4,
                linked_file=DescriptorBlock(),
                version=1,
            ),
            LinkedLayer(  # type: ignore[list-item]
                kind=LinkedLayerType.EXTERNAL,
                data=b"\x01\x02\x03\x04",
                filesize=4,
                linked_file=DescriptorBlock(),
                version=2,
            ),
            LinkedLayer(  # type: ignore[list-item]
                kind=LinkedLayerType.EXTERNAL,
                data=b"\x01\x02\x03\x04",
                filesize=4,
                linked_file=DescriptorBlock(),
                version=3,
            ),
            LinkedLayer(  # type: ignore[list-item]
                kind=LinkedLayerType.EXTERNAL,
                data=b"\x01\x02\x03\x04",
                filesize=4,
                linked_file=DescriptorBlock(),
                version=7,
                timestamp=(2000, 1, 1, 0, 0, 0.0),
                child_id="",
                mod_time=200000.1,
                lock_state=1,
                open_file=DescriptorBlock(),
            ),
        ]
    )
    check_write_read(linked_layers)


def test_linked_layer_v8_survives_save() -> None:
    # smart-object-v8.psd: an embedded smart object as Photoshop 27 writes it.
    with open(full_name("smart-object-v8.psd"), "rb") as f:
        psd = PSD.read(f)

    def entries(psd: PSD) -> list[LinkedLayer]:
        blocks = psd.layer_and_mask_information.tagged_blocks
        assert blocks is not None
        return [e for tag in LINKED_TAGS if tag in blocks for e in blocks.get_data(tag)]

    before = entries(psd)
    assert [e.version for e in before] == [8]
    assert before[0].content_descriptor is not None

    buffer = io.BytesIO()
    psd.write(buffer)
    buffer.seek(0)
    after = entries(PSD.read(buffer))
    assert [e.tobytes() for e in after] == [e.tobytes() for e in before]


def _lnk2_block(body: bytes, version: int) -> bytes:
    fmt = ("I", "Q")[version - 1]
    return b"8BIM" + Tag.LINKED_LAYER2.value + struct.pack(">" + fmt, len(body)) + body


_SIBLING = b"8BIM" + b"zzzz" + struct.pack(">I", 4) + b"data"


def test_linked_layers_reads_every_item_from_the_framed_block() -> None:
    """Each item is parsed from a bounded substream.

    The list consumes its block exactly, so the next structure starts where
    the framing says (#899).
    """
    items = LinkedLayers(
        [
            LinkedLayer(),  # type: ignore[list-item]
            LinkedLayer(  # type: ignore[list-item]
                kind=LinkedLayerType.DATA, data=b"\x01\x02\x03\x04"
            ),
            LinkedLayer(kind=LinkedLayerType.ALIAS),  # type: ignore[list-item]
        ]
    )
    body = items.tobytes()
    stream = io.BytesIO(body)
    assert LinkedLayers.read(stream) == items
    assert stream.tell() == len(body)


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("padding", [1, 4])
def test_streamed_block_reads_past_its_sibling(version: int, padding: int) -> None:
    """The streamed read leaves the parent stream at the block's end.

    A following block still parses, padding included (#899).
    """
    items = LinkedLayers(
        [LinkedLayer(kind=LinkedLayerType.DATA, data=b"\x01\x02")]  # type: ignore[list-item]
    )
    stream = io.BytesIO(_lnk2_block(items.tobytes(), version) + _SIBLING)
    first = TaggedBlock.read(stream, version=version, padding=padding)
    assert isinstance(first.data, LinkedLayers)
    assert first.data == items
    second = TaggedBlock.read(stream, version=version, padding=padding)
    assert second.key == b"zzzz"
    assert second.data == b"data"


def test_streamed_block_rejects_a_truncated_payload() -> None:
    """A declared length the file cannot hold raises before anything is read."""
    body = LinkedLayers(
        [LinkedLayer(kind=LinkedLayerType.DATA, data=b"abcd")]  # type: ignore[list-item]
    ).tobytes()
    block = _lnk2_block(body, 1)[:-8]
    with pytest.raises(OSError):
        TaggedBlock.read(io.BytesIO(block), version=1)


def test_streamed_block_rejects_a_forged_length() -> None:
    """A forged length is rejected by the bound check, not by an allocation."""
    stream = io.BytesIO(b"8BIM" + Tag.LINKED_LAYER2.value + struct.pack(">Q", 1 << 30))
    with pytest.raises(OSError):
        TaggedBlock.read(stream, version=2)


def test_linked_layers_rejects_an_item_that_under_consumes() -> None:
    """A byte inside the item's window the parser did not read is leftover.

    It is unexplained, not padding, so the item read fails (#899).
    """
    item = LinkedLayer(kind=LinkedLayerType.DATA, data=b"abcd").tobytes()
    stream = io.BytesIO(struct.pack(">Q", len(item) + 1) + item + b"\x00")
    with pytest.raises(ValueError, match="consumed"):
        LinkedLayers.read(stream)


def test_streamed_block_falls_back_to_raw_bytes_and_keeps_alignment() -> None:
    """An unreadable item falls back to the block's raw bytes.

    That is what any other tagged block does, and the stream stays aligned
    for what follows (#899).
    """
    body = struct.pack(">Q", 4) + b"\xff\xff\xff\xff"
    block = _lnk2_block(body, 1)
    stream = io.BytesIO(block + _SIBLING)
    parsed = TaggedBlock.read(stream, version=1)
    assert parsed.data == body
    assert TaggedBlock.read(stream, version=1).data == b"data"
    assert stream.tell() == len(block + _SIBLING)


def test_streamed_block_rejects_a_short_trailing_tail() -> None:
    """A tail too short to frame another item is unexplained leftover.

    The block reads as raw bytes instead of a silently partial list (#899).
    """
    items = LinkedLayers(
        [LinkedLayer(kind=LinkedLayerType.DATA, data=b"abcd")]  # type: ignore[list-item]
    )
    body = items.tobytes() + b"\x00\x00"
    parsed = TaggedBlock.read(io.BytesIO(_lnk2_block(body, 1)), version=1)
    assert parsed.data == body
