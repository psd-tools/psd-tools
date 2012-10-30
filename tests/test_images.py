# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from psd_tools.user_api.layers import composite_image_to_PIL, layer_to_PIL
from .utils import decode_psd

def _tobytes(pil_image):
    try:
        return pil_image.tobytes()
    except AttributeError:
        return pil_image.tostring()


def test_single_layer():
    psd = decode_psd('1layer.psd')
    composite_image = composite_image_to_PIL(psd)
    layer_image = layer_to_PIL(psd, 0)

    assert len(psd.layer_and_mask_data.layers.layer_records) == 1
    assert _tobytes(layer_image) == _tobytes(composite_image)

