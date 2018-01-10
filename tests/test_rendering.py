# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import pytest

from PIL.Image import Image
from psd_tools.user_api.psd_image import PSDImage, merge_layers
from tests.utils import decode_psd, full_name


CLIP_FILES = [
    ('clipping-mask.psd',),
    ('clipping-mask2.psd',)
]


@pytest.mark.parametrize(("filename",), CLIP_FILES)
def test_render_clip_layers(filename):
    psd = PSDImage.load(full_name(filename))
    image1 = psd.as_PIL()
    image2 = psd.as_PIL_merged()
    assert isinstance(image1, Image)
    assert isinstance(image2, Image)
