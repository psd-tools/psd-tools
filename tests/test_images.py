# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import pytest

from psd_tools import PSDImage
from psd_tools.user_api.layers import composite_image_to_PIL, layer_to_PIL
from psd_tools.constants import BlendMode

from .utils import decode_psd

def _tobytes(pil_image):
    try:
        return pil_image.tobytes()
    except AttributeError:
        return pil_image.tostring()

SINGLE_LAYER_FILES = [['1layer.psd'], ['transparentbg-gimp.psd']]


@pytest.mark.parametrize(["filename"], SINGLE_LAYER_FILES)
def test_single_layer(filename):
    psd = decode_psd(filename)
    composite_image = composite_image_to_PIL(psd)
    layer_image = layer_to_PIL(psd, 0)

    assert len(psd.layer_and_mask_data.layers.layer_records) == 1
    assert _tobytes(layer_image) == _tobytes(composite_image)

def test_api():
    image = PSDImage(decode_psd('1layer.psd'))
    assert len(image.layers) == 1

    layer = image.layers[0]
    assert layer.name == 'Фон'
    assert layer.bbox == (0, 0, 101, 55)
    assert layer.visible
    assert layer.opacity == 255
    assert layer.blend_mode == BlendMode.NORMAL

