from __future__ import absolute_import, unicode_literals

import logging

import pytest

from psd_tools.api.psd_image import PSDImage
from ..utils import full_name

logger = logging.getLogger(__name__)


@pytest.fixture
def layer_mask_data():
    return PSDImage.open(full_name('layer_mask_data.psd'))


def test_layer_mask(layer_mask_data):
    from PIL.Image import Image
    for layer in layer_mask_data:
        if not layer.has_mask():
            continue

        mask = layer.mask
        mask.background_color
        mask.bbox
        mask.size
        mask.disabled
        mask.flags
        mask.parameters
        mask.real_flags
        repr(mask)
        assert isinstance(mask.topil(), Image)
