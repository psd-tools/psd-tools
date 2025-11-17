import os

import pytest

from psd_tools.psd import PSD
from psd_tools.constants import Resource, ColorMode
from psd_tools.psd.image_resources import (
    ImageResource,
    ImageResources,
    Slices,
    AlphaChannelMode,
)

from ..utils import TEST_ROOT, check_read_write, check_write_read


def test_image_resources_from_to() -> None:
    check_read_write(ImageResources, b"\x00\x00\x00\x00")


def test_image_resources_exception() -> None:
    with pytest.raises(IOError):
        ImageResources.frombytes(b"\x00\x00\x00\x01")


def test_image_resources_dict() -> None:
    image_resources = ImageResources.new()
    assert image_resources.get_data(Resource.VERSION_INFO)
    assert image_resources.get_data(Resource.OBSOLETE1) is None
    assert len([1 for key in image_resources if key == Resource.VERSION_INFO]) == 1


@pytest.mark.parametrize(
    ["fixture"],
    [
        (ImageResource(name="", data=b"\x01\x04\x02"),),
        (ImageResource(name="foo", data=b"\x01\x04\x02"),),
    ],
)
def test_image_resource_from_to(fixture) -> None:
    check_write_read(fixture)


def test_image_resource_exception() -> None:
    with pytest.raises(IOError):
        ImageResource.frombytes(b"\x00\x00\x00\x01")


@pytest.mark.parametrize(
    "kls, filename",
    [
        (Slices, "slices_0.dat"),
    ],
)
def test_image_resource_rw(kls, filename) -> None:
    filepath = os.path.join(TEST_ROOT, "image_resources", filename)
    with open(filepath, "rb") as f:
        fixture = f.read()
    check_read_write(kls, fixture)


def test_display_info() -> None:
    filepath = os.path.join(TEST_ROOT, "psd_files", "cmyk-spot.psd")
    with open(filepath, "rb") as f:
        psd = PSD.read(f)
    assert psd.header.color_mode == ColorMode.CMYK
    info = psd.image_resources[Resource.DISPLAY_INFO].data
    assert len(info.alpha_channels) == 3
    expected_colors = [
        # RGB in uint16, with an extra zero because the color space can be CMYK
        [0, 30840, 49087, 0],
        [65535, 18504, 45232, 0],
        [65535, 59624, 0, 0],
    ]
    for i, c in enumerate(info.alpha_channels):
        assert c.mode == AlphaChannelMode.SPOT
        assert c.color_space == 0  # RGB color space
        assert [c.c1, c.c2, c.c3, c.c4] == expected_colors[i]


def test_display_info_channel_type() -> None:
    filepath = os.path.join(TEST_ROOT, "psd_files", "cmyk-alpha-spot.psd")
    with open(filepath, "rb") as f:
        psd = PSD.read(f)

    assert psd.header.color_mode == ColorMode.CMYK
    info = psd.image_resources[Resource.DISPLAY_INFO].data
    assert len(info.alpha_channels) == 2
    assert info.alpha_channels[0].mode == AlphaChannelMode.SPOT
    assert info.alpha_channels[1].mode == AlphaChannelMode.INVERTED_ALPHA
