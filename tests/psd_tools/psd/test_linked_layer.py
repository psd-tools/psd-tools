import io
import logging
import struct
from typing import Any

import pytest

from psd_tools.constants import LinkedLayerType, Tag
from psd_tools.psd import PSD
from psd_tools.psd.descriptor import DescriptorBlock
from psd_tools.psd.linked_layer import LinkedLayer, LinkedLayers

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
