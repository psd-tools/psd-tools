import logging
import pprint
from pathlib import Path
from typing import Any, Tuple, Union

import pytest
from PIL import Image

from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import BlendMode, ColorMode, Compression

from ..utils import full_name

logger = logging.getLogger(__name__)


@pytest.fixture
def fixture() -> PSDImage:
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
def test_new(args: Tuple[str, Tuple[int, int], Tuple[int, ...]]) -> None:
    PSDImage.new(*args)  # type: ignore[arg-type]


def test_frompil_psb() -> None:
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
def test_open(filename: Union[str, Path]) -> None:
    input_path = full_name(str(filename))
    PSDImage.open(input_path)
    with open(input_path, "rb") as f:
        PSDImage.open(f)


def test_save(fixture: PSDImage, tmp_path: Path) -> None:
    output_path = tmp_path / "output.psd"
    fixture.save(str(output_path))
    fixture.save(output_path)
    with open(output_path, "wb") as f:
        fixture.save(f)


def test_pilio(fixture: PSDImage) -> None:
    image = fixture.topil()
    for i in range(fixture.channels):
        fixture.topil(channel=i)
    assert image is not None
    psd = PSDImage.frompil(image, compression=Compression.RAW)
    assert psd._record.header == fixture._record.header
    assert psd._record.image_data == fixture._record.image_data


def test_properties(fixture: PSDImage) -> None:
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


def test_version() -> None:
    assert PSDImage.open(full_name("gray0.psb")).version == 2


def test_is_visible(fixture: PSDImage) -> None:
    assert fixture.is_visible() is True


def test_is_group(fixture: PSDImage) -> None:
    assert fixture.is_group() is True


def test_has_preview(fixture: PSDImage) -> None:
    assert fixture.has_preview() is True


def test_thumnail(fixture: PSDImage) -> None:
    assert fixture.has_thumbnail() is True
    assert fixture.thumbnail()


def test_repr_pretty(fixture: PSDImage) -> None:
    fixture.__repr__()
    pprint.pprint(fixture)


@pytest.mark.parametrize(
    "filename",
    [str(Path("third-party-psds") / "cactus_top.psd")],
)
def test_open2(filename: str) -> None:
    assert isinstance(PSDImage.open(full_name(filename)), PSDImage)


def test_create_pixel_layer() -> None:
    psdimage = PSDImage.new(mode="RGB", size=(100, 100))
    layer = psdimage.create_pixel_layer(
        Image.new("RGB", (50, 50), (255, 0, 0)),
        name="Red Layer",
        top=10,
        left=20,
        compression=Compression.RLE,
        opacity=128,
        blend_mode=BlendMode.MULTIPLY,
    )
    assert layer.name == "Red Layer"
    assert layer.top == 10
    assert layer.left == 20
    assert layer.opacity == 128
    assert layer.blend_mode == BlendMode.MULTIPLY
    assert len(psdimage) == 1
    assert psdimage[0] is layer


def test_create_group() -> None:
    psdimage = PSDImage.new(mode="RGB", size=(100, 100))
    layer_list = [
        psdimage.create_pixel_layer(
            Image.new("RGB", (50, 50), (0, 255, 0)),
            name="Green Layer",
        ),
    ]
    group = psdimage.create_group(
        layer_list,
        name="My Group",
        open_folder=False,
        opacity=128,
        blend_mode=BlendMode.SCREEN,
    )
    assert group.name == "My Group"
    assert group.open_folder is False
    assert len(psdimage) == 1
    assert psdimage[0] is group
    assert len(group) == 1
    assert group[0] is layer_list[0]
    assert group.opacity == 128
    assert group.blend_mode == BlendMode.SCREEN


def test_update_record(fixture: PSDImage) -> None:
    pixel_layer = PSDImage.open(full_name("layers/pixel-layer.psd"))[0]
    fill_layer = PSDImage.open(full_name("layers/solid-color-fill.psd"))[0]
    shape_layer = PSDImage.open(full_name("layers/shape-layer.psd"))[0]
    smart_layer = PSDImage.open(full_name("layers/smartobject-layer.psd"))[0]
    type_layer = PSDImage.open(full_name("layers/type-layer.psd"))[0]
    group_layer = PSDImage.open(full_name("layers/group.psd"))[0]

    group_layer.extend([pixel_layer, fill_layer, shape_layer, smart_layer, type_layer])
    fixture.append(group_layer)
    layer_info = fixture._record.layer_and_mask_information.layer_info
    assert layer_info is not None

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


def test_is_updated() -> None:
    psd = PSDImage.open(full_name("hidden-groups.psd"))
    assert not psd.is_updated()
    psd[0].visible = False
    assert psd.is_updated()

    psd = PSDImage.open(full_name("clipping-mask.psd"))
    assert not psd.is_updated()
    psd[1][2].clipping = False
    assert psd.is_updated()


def test_save_without_composite_dependencies(tmp_path: Path, caplog: Any) -> None:
    """Test that save works gracefully without composite dependencies."""
    from unittest.mock import patch

    # Create a simple PSD and modify it
    psdimage = PSDImage.new(mode="RGB", size=(100, 100))
    psdimage.create_pixel_layer(
        Image.new("RGB", (50, 50), (255, 0, 0)),
        name="Test Layer",
    )

    # Mark as updated
    assert psdimage.is_updated()

    output_path = tmp_path / "test_no_composite.psd"

    # Mock composite() to raise ImportError (simulating missing dependencies)
    def mock_composite(*args: Any, **kwargs: Any) -> None:
        raise ImportError("No module named 'scipy'")

    with patch.object(psdimage, "composite", side_effect=mock_composite):
        # Should not raise, should log warning
        with caplog.at_level(logging.WARNING):
            psdimage.save(str(output_path))

    # Verify file was saved
    assert output_path.exists()

    # Verify warning was logged
    assert "Failed to update preview image" in caplog.text
    assert "pip install 'psd-tools[composite]'" in caplog.text

    # Verify saved file can be read back
    loaded = PSDImage.open(output_path)
    assert len(loaded) == 1
    assert loaded[0].name == "Test Layer"


def test_save_rgba_pixel_layer(tmp_path: Path):
    # create an RGBA PSD with a layer
    psd = PSDImage.new("RGBA", (32, 48))
    psd.create_pixel_layer(Image.linear_gradient("L").resize(psd.size), "layer1")
    psd.save(tmp_path / "tmp.psd")

    # check that the updated preview image has the expected number of channels
    assert len(psd._record.image_data.get_data(psd._record.header)) == 4
