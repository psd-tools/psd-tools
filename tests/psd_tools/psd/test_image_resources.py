from typing import Any, Type
import os

import pytest

from psd_tools.psd import PSD
from psd_tools.constants import Resource, ColorMode
from psd_tools.psd.image_resources import (
    AlphaChannelMode,
    ImageResource,
    ImageResources,
    Slices,
    TransferFunction,
    TransferFunctions,
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
def test_image_resource_from_to(fixture: ImageResource) -> None:
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
def test_image_resource_rw(kls: Type[Any], filename: str) -> None:
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


NULL_CURVE = [0, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, 1000]


@pytest.mark.parametrize(
    "curve, override",
    [
        # Adobe spec NULL curve: intermediate points are -1 (no point), exercises signed values
        (NULL_CURVE, 0),
        # All points explicitly set (fully-defined curve, all positive)
        ([0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950, 975, 1000], 0),
        # Mixed -1 (no-point) with defined midpoints; also checks override is preserved
        ([0, 250, -1, 500, -1, 750, -1, -1, -1, -1, -1, -1, 1000], 1),
    ],
)
def test_transfer_function_write_read(curve: list, override: int) -> None:
    check_write_read(TransferFunction(curve=curve, override=override))


def test_transfer_functions_write_read() -> None:
    null_fn = TransferFunction(curve=NULL_CURVE, override=0)  # type: ignore[arg-type]
    # 1 function (grayscale)
    check_write_read(TransferFunctions([null_fn]))  # type: ignore[list-item]
    # 4 functions (duotone / CMYK / color)
    check_write_read(TransferFunctions([null_fn] * 4))  # type: ignore[list-item]


@pytest.mark.parametrize(
    "psd_path, resource_key",
    [
        (
            os.path.join("colormodes", "4x4_8bit_duotone.psd"),
            Resource.DUOTONE_TRANSFER_FUNCTION,
        ),
        (
            os.path.join("colormodes", "4x4_8bit_grayscale.psd"),
            Resource.GRAYSCALE_TRANSFER_FUNCTION,
        ),
        (
            os.path.join("colormodes", "4x4_16bit_grayscale.psd"),
            Resource.GRAYSCALE_TRANSFER_FUNCTION,
        ),
    ],
)
def test_transfer_functions_rw_from_psd(psd_path: str, resource_key: Resource) -> None:
    filepath = os.path.join(TEST_ROOT, "psd_files", psd_path)
    with open(filepath, "rb") as f:
        psd = PSD.read(f)
    check_write_read(psd.image_resources[resource_key].data)


@pytest.mark.parametrize(
    "psd_path, resource_key, expected_count",
    [
        (
            os.path.join("colormodes", "4x4_8bit_duotone.psd"),
            Resource.DUOTONE_TRANSFER_FUNCTION,
            4,
        ),
        (
            os.path.join("colormodes", "4x4_8bit_grayscale.psd"),
            Resource.GRAYSCALE_TRANSFER_FUNCTION,
            1,
        ),
    ],
)
def test_transfer_functions_values(
    psd_path: str, resource_key: Resource, expected_count: int
) -> None:
    """Decoded values must match the Adobe spec NULL curve with signed -1 sentinel."""
    filepath = os.path.join(TEST_ROOT, "psd_files", psd_path)
    with open(filepath, "rb") as f:
        psd = PSD.read(f)
    tf = psd.image_resources[resource_key].data
    assert len(tf) == expected_count
    for fn in tf:
        assert list(fn.curve) == NULL_CURVE
        assert fn.override == 0


def test_display_info_channel_type() -> None:
    filepath = os.path.join(TEST_ROOT, "psd_files", "cmyk-alpha-spot.psd")
    with open(filepath, "rb") as f:
        psd = PSD.read(f)

    assert psd.header.color_mode == ColorMode.CMYK
    info = psd.image_resources[Resource.DISPLAY_INFO].data
    assert len(info.alpha_channels) == 2
    assert info.alpha_channels[0].mode == AlphaChannelMode.SPOT
    assert info.alpha_channels[1].mode == AlphaChannelMode.INVERTED_ALPHA
