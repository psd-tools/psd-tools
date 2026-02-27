import logging

import pytest
from PIL import Image

from psd_tools.api.psd_image import PSDImage

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
