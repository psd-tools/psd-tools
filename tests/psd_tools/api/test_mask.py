import logging

import pytest
from PIL import Image

from psd_tools.api.psd_image import PSDImage
from psd_tools.psd.layer_and_mask import MaskData

from ..utils import full_name

logger = logging.getLogger(__name__)


@pytest.fixture
def layer_mask_data() -> PSDImage:
    return PSDImage.open(full_name("layer_mask_data.psd"))


@pytest.mark.parametrize("real", [True, False])
def test_layer_mask(layer_mask_data: PSDImage, real: bool) -> None:
    mask = layer_mask_data[4].mask
    assert mask is not None
    assert mask.real_flags is not None
    mask.real_flags.parameters_applied = real
    mask.background_color
    mask.bbox
    mask.size
    mask.disabled
    mask.flags
    mask.parameters
    mask.real_flags
    repr(mask)
    assert mask.topil()


def test_mask_topil_layer_sized_background_color() -> None:
    """Regression test for issue #389: layer_sized=True must apply background_color."""
    psdimage = PSDImage.new(mode="RGB", size=(100, 100))
    layer = psdimage.create_pixel_layer(Image.new("RGB", (100, 100)))
    # Create a 40x30 black mask patch
    layer.create_mask(Image.new("L", (40, 30), 0))

    # Simulate inverted mask: bbox at (10, 20)–(50, 50), background=255
    mask_data = layer._record.mask_data
    assert isinstance(mask_data, MaskData)
    mask_data.top = 20
    mask_data.left = 10
    mask_data.bottom = 50
    mask_data.right = 50
    mask_data.background_color = 255

    mask = layer.mask
    assert mask is not None

    # Raw topil() still returns bbox-sized image (backward compat)
    raw = mask.topil(layer_sized=False)
    assert raw is not None
    assert raw.size == (40, 30)

    # layer_sized=True returns full layer image with background fill
    img = mask.topil(layer_sized=True)
    assert img is not None
    assert img.size == layer.size  # (100, 100)
    assert img.getpixel((0, 0)) == 255  # outside bbox → background_color
    assert img.getpixel((99, 99)) == 255  # outside bbox → background_color
    assert img.getpixel((10, 20)) == 0  # top-left of pasted mask data


def test_mask_disabled_setter() -> None:
    psdimage = PSDImage.new(mode="RGB", size=(30, 30))
    layer = psdimage.create_pixel_layer(Image.new("RGB", (30, 30)))
    layer.create_mask(Image.new("L", (30, 30), 200))

    mask = layer.mask
    assert mask is not None
    assert not mask.disabled

    mask.disabled = True
    assert mask.disabled

    mask.disabled = False
    assert not mask.disabled
