from __future__ import absolute_import, unicode_literals
import pytest
import logging

from PIL.Image import Image
import imagehash
import numpy as np

from psd_tools2.api.psd_image import PSDImage

from ..utils import full_name


logger = logging.getLogger(__name__)


QUALITY_TEST_FILES = [
    # ('mask-index.psd',),  # Transparent region in preview image is wrong...
    ('background-red-opacity-80.psd',),
    ('32bit.psd',),
]


@pytest.mark.parametrize(("filename",), QUALITY_TEST_FILES)
def test_compose_quality(filename):
    psd = PSDImage.open(full_name(filename))
    preview = psd.topil()
    rendered = psd.compose()
    assert isinstance(preview, Image)
    assert isinstance(rendered, Image)
    preview_hash = imagehash.average_hash(preview)
    rendered_hash = imagehash.average_hash(rendered)
    error_count = np.sum(
        np.bitwise_xor(preview_hash.hash, rendered_hash.hash))
    error_rate = error_count / float(preview_hash.hash.size)
    assert error_rate <= 0.1
