# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import pytest
from psd_tools.user_api import pil_support, pymaging_support
from .utils import decode_psd, tobytes


SINGLE_LAYER_FILES = [
    ['1layer.psd'],
    ['transparentbg-gimp.psd']
]

BACKENDS = [[pil_support], [pymaging_support]]


@pytest.mark.parametrize(["backend"], BACKENDS)
@pytest.mark.parametrize(["filename"], SINGLE_LAYER_FILES)
def test_single_layer(filename, backend):
    psd = decode_psd(filename)

    composite_image = backend.extract_composite_image(psd)
    layer_image = backend.extract_layer_image(psd, 0)

    assert len(psd.layer_and_mask_data.layers.layer_records) == 1
    assert tobytes(layer_image) == tobytes(composite_image)
    assert len(tobytes(layer_image))
