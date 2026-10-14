from typing import Any, Dict
import logging
import struct

import pytest

from psd_tools.constants import LinkedLayerType
from psd_tools.psd.descriptor import DescriptorBlock
from psd_tools.psd.linked_layer import LinkedLayer, LinkedLayers

from ..utils import check_read_write, check_write_read

logger = logging.getLogger(__name__)


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
        dict(),
        dict(kind=LinkedLayerType.DATA, data=b"\x01\x02\x03\x04"),
        dict(kind=LinkedLayerType.ALIAS),
        dict(
            kind=LinkedLayerType.EXTERNAL,
            data=None,
            filesize=4,
            linked_file=DescriptorBlock(),
            version=1,
        ),
        dict(
            kind=LinkedLayerType.EXTERNAL,
            data=b"\x01\x02\x03\x04",
            filesize=4,
            linked_file=DescriptorBlock(),
            version=2,
        ),
        dict(
            kind=LinkedLayerType.EXTERNAL,
            data=b"\x01\x02\x03\x04",
            filesize=4,
            linked_file=DescriptorBlock(),
            version=3,
        ),
        dict(
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
    ],
)
def test_linked_layer_wr(kwargs: Dict[str, Any]) -> None:
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
