# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import pytest
from psd_tools.user_api import pil_support, pymaging_support
from .utils import decode_psd, with_psb

def _tobytes(image):
    try:
        return image.tobytes() # Pillow at Python 3
    except AttributeError:
        try:
            return image.tostring() # PIL
        except AttributeError:
            return image.pixels.data.tostring() # pymaging

SINGLE_LAYER_FILES = with_psb([
    ['1layer.psd'],
    ['transparentbg-gimp.psd']
])

BACKENDS = [[pil_support], [pymaging_support]]

@pytest.mark.parametrize(["backend"], BACKENDS)
@pytest.mark.parametrize(["filename"], SINGLE_LAYER_FILES)
def test_single_layer(filename, backend):
    psd = decode_psd(filename)

    composite_image = backend.extract_composite_image(psd)
    layer_image = backend.extract_layer_image(psd, 0)

    assert len(psd.layer_and_mask_data.layers.layer_records) == 1
    assert _tobytes(layer_image) == _tobytes(composite_image)
    assert len(_tobytes(layer_image))
