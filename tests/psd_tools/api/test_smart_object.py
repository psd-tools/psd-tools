import logging
from pathlib import Path
from typing import Iterator

import pytest

from psd_tools.api.psd_image import PSDImage
from psd_tools.api.layers import SmartObjectLayer
from psd_tools.api.smart_object import SmartObject

from ..utils import full_name

logger = logging.getLogger(__name__)


@pytest.fixture
def embedded_object() -> Iterator[SmartObject]:
    psdimage = PSDImage.open(full_name("placedLayer.psd"))
    layer = psdimage[3]
    assert isinstance(layer, SmartObjectLayer)
    yield layer.smart_object


@pytest.fixture
def external_object() -> Iterator[SmartObject]:
    psdimage = PSDImage.open(full_name("placedLayer.psd"))
    layer = psdimage[1]
    assert isinstance(layer, SmartObjectLayer)
    yield layer.smart_object


@pytest.fixture
def linked_layer_png() -> Iterator[bytes]:
    with open(full_name("linked-layer.png"), "rb") as f:
        yield f.read()


def test_smart_object_data(
    embedded_object: SmartObject, linked_layer_png: bytes, tmp_path: Path
) -> None:
    assert embedded_object.kind in "data"
    assert embedded_object.filename == "linked-layer.png"
    assert embedded_object.filetype == "png"
    assert embedded_object.unique_id == "5a96c404-ab9c-1177-97ef-96ca454b82b7"
    assert embedded_object.is_psd() is False
    assert embedded_object.warp
    assert embedded_object.resolution == 144.0
    assert embedded_object.filesize == 17272
    assert embedded_object.data == linked_layer_png
    with embedded_object.open() as f:
        assert f.read() == linked_layer_png
    tmppath = tmp_path / embedded_object.filename
    embedded_object.save(str(tmppath))


def test_smart_object_external(
    external_object: SmartObject, linked_layer_png: bytes
) -> None:
    assert external_object.kind in "external"
    assert external_object.filename == "linked-layer.png"
    assert external_object.filetype == "png"
    assert external_object.unique_id == "5a96c402-ab9c-1177-97ef-96ca454b82b7"
    assert external_object.is_psd() is False
    assert external_object.warp
    assert external_object.resolution == 144.0
    assert external_object.filesize == 17272
    with external_object.open(full_name("")) as f:
        assert f.read() == linked_layer_png
