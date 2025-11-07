import logging
import os
import pprint
from pathlib import Path

import pytest
from PIL import Image

from psd_tools.api import layers
from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import ColorMode, Compression

from ..utils import full_name

logger = logging.getLogger(__name__)


@pytest.fixture
def fixture():
    return PSDImage.open(full_name("colormodes/4x4_8bit_rgb.psd"))


@pytest.mark.parametrize(
    "args",
    [
        ("L", (16, 24), (0,)),
        ("LA", (16, 24), (0, 255)),
        ("RGB", (16, 24), (255, 128, 64)),
        ("RGBA", (16, 24), (255, 128, 64, 255)),
        ("CMYK", (16, 24), (255, 128, 64, 128)),
    ],
)
def test_new(args):
    PSDImage.new(*args)


def test_frompil_psb():
    image = Image.new("RGB", (30001, 24))
    psb = PSDImage.frompil(image)
    assert psb.version == 2


@pytest.mark.parametrize(
    "filename",
    [
        "colormodes/4x4_8bit_rgb.psd",
        Path("colormodes/4x4_8bit_rgb.psd"),
    ],
)
def test_open(filename):
    input_path = full_name(filename)
    PSDImage.open(input_path)
    with open(input_path, "rb") as f:
        PSDImage.open(f)


def test_save(fixture, tmpdir):
    output_path = os.path.join(str(tmpdir), "output.psd")
    fixture.save(output_path)
    fixture.save(Path(output_path))
    with open(output_path, "wb") as f:
        fixture.save(f)


def test_pilio(fixture):
    image = fixture.topil()
    for i in range(fixture.channels):
        fixture.topil(channel=i)
    psd = PSDImage.frompil(image, compression=Compression.RAW)
    assert psd._record.header == fixture._record.header
    assert psd._record.image_data == fixture._record.image_data


def test_properties(fixture):
    assert fixture.name == "Root"
    assert fixture.kind == "psdimage"
    assert fixture.visible is True
    assert fixture.parent is None
    assert fixture.left == 0
    assert fixture.top == 0
    assert fixture.right == 4
    assert fixture.bottom == 4
    assert fixture.width == 4
    assert fixture.height == 4
    assert fixture.size == (4, 4)
    assert fixture.bbox == (0, 0, 4, 4)
    assert fixture.viewbox == (0, 0, 4, 4)
    assert fixture.image_resources
    assert fixture.tagged_blocks
    assert fixture.color_mode == ColorMode.RGB
    assert fixture.version == 1


def test_version():
    assert PSDImage.open(full_name("gray0.psb")).version == 2


def test_is_visible(fixture):
    assert fixture.is_visible() is True


def test_is_group(fixture):
    assert fixture.is_group() is True


def test_has_preview(fixture):
    assert fixture.has_preview() is True


def test_thumnail(fixture):
    assert fixture.has_thumbnail() is True
    assert fixture.thumbnail()


def test_repr_pretty(fixture):
    fixture.__repr__()
    pprint.pprint(fixture)


@pytest.mark.parametrize(
    "filename",
    [os.path.join("third-party-psds", "cactus_top.psd")],
)
def test_open2(filename):
    assert isinstance(PSDImage.open(full_name(filename)), PSDImage)


def test_update_record(fixture):
    pixel_layer = PSDImage.open(full_name("layers/pixel-layer.psd"))[0]
    fill_layer = PSDImage.open(full_name("layers/solid-color-fill.psd"))[0]
    shape_layer = PSDImage.open(full_name("layers/shape-layer.psd"))[0]
    smart_layer = PSDImage.open(full_name("layers/smartobject-layer.psd"))[0]
    type_layer = PSDImage.open(full_name("layers/type-layer.psd"))[0]
    group_layer = PSDImage.open(full_name("layers/group.psd"))[0]

    group_layer.extend([pixel_layer, fill_layer, shape_layer, smart_layer, type_layer])

    fixture.append(group_layer)

    fixture._update_record()

    layer_info = fixture._record.layer_and_mask_information.layer_info

    assert layer_info.layer_count == 9

    assert layer_info.layer_records[0] is fixture[0]._record
    assert layer_info.layer_records[1] is fixture[1]._record

    assert layer_info.layer_records[2] is group_layer._bounding_record
    assert layer_info.layer_records[3] is pixel_layer._record
    assert layer_info.layer_records[4] is fill_layer._record
    assert layer_info.layer_records[5] is shape_layer._record
    assert layer_info.layer_records[6] is smart_layer._record
    assert layer_info.layer_records[7] is type_layer._record
    assert layer_info.layer_records[8] is group_layer._record

    assert layer_info.channel_image_data[0] is fixture[0]._channels
    assert layer_info.channel_image_data[1] is fixture[1]._channels

    assert layer_info.channel_image_data[2] is group_layer._bounding_channels
    assert layer_info.channel_image_data[3] is pixel_layer._channels
    assert layer_info.channel_image_data[4] is fill_layer._channels
    assert layer_info.channel_image_data[5] is shape_layer._channels
    assert layer_info.channel_image_data[6] is smart_layer._channels
    assert layer_info.channel_image_data[7] is type_layer._channels
    assert layer_info.channel_image_data[8] is group_layer._channels


def test_is_updated():
    psd = PSDImage.open(full_name("hidden-groups.psd"))
    assert not psd.is_updated()
    psd[0].visible = False
    assert psd.is_updated()

    psd = PSDImage.open(full_name("clipping-mask.psd"))
    assert not psd.is_updated()
    psd[1][2].clipping = False
    assert psd.is_updated()


def test_frompil_layers():
    psdimage = PSDImage.new(mode="RGB", size=(30, 30), color=(255, 255, 255))
    image = Image.new("RGB", size=(30, 30), color=(255, 0, 0))
    layers.PixelLayer.frompil(image, psdimage, name="Test Layer")
    assert len(psdimage) == 1
    assert psdimage[0].name == "Test Layer"
    rendered = psdimage.composite()
    assert isinstance(rendered, Image.Image)
    assert rendered.getpixel((0, 0)) == (255, 0, 0)
