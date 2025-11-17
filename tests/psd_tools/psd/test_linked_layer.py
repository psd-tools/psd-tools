from typing import Any, Dict
import logging

import pytest

from psd_tools.constants import LinkedLayerType
from psd_tools.psd.descriptor import DescriptorBlock
from psd_tools.psd.linked_layer import LinkedLayer, LinkedLayers

from ..utils import check_write_read

logger = logging.getLogger(__name__)


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
