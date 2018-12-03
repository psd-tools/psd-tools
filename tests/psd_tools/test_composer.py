# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import pytest

from PIL.Image import Image
import imagehash
import numpy as np
from psd_tools.user_api.psd_image import PSDImage
from .utils import decode_psd, full_name


CLIP_FILES = [
    ('clipping-mask.psd',),
    ('clipping-mask2.psd',)
]

QUALITY_TEST_FILES = [
    ('mask-index.psd',),
    ('background-red-opacity-80.psd',),
    ('32bit.psd',),
]


@pytest.mark.parametrize(("filename",), CLIP_FILES)
def test_render_clip_layers(filename):
    psd = PSDImage.load(full_name(filename))
    image1 = psd.as_PIL()
    image2 = psd.as_PIL(render=True)
    assert isinstance(image1, Image)
    assert isinstance(image2, Image)


@pytest.mark.parametrize(("filename",), QUALITY_TEST_FILES)
def test_render_quality(filename):
    psd = PSDImage.load(full_name(filename))
    preview = psd.as_PIL()
    rendered = psd.as_PIL(render=True)
    assert isinstance(preview, Image)
    assert isinstance(rendered, Image)
    preview_hash = imagehash.average_hash(preview)
    rendered_hash = imagehash.average_hash(rendered)
    error_count = np.sum(
        np.bitwise_xor(preview_hash.hash, rendered_hash.hash))
    error_rate = error_count / float(preview_hash.hash.size)
    assert error_rate <= 0.1
