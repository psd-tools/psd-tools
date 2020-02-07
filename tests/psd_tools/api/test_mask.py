from __future__ import absolute_import, unicode_literals
import pytest
import logging

from psd_tools.api.psd_image import PSDImage

from ..utils import full_name

logger = logging.getLogger(__name__)


@pytest.fixture
def layer_mask_data():
    return PSDImage.open(full_name('layer_mask_data.psd'))


@pytest.mark.parametrize('real', [True, False])
def test_layer_mask(layer_mask_data, real):
    mask = layer_mask_data[4].mask
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
