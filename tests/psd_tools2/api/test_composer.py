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


def _calculate_hash_error(image1, image2):
    assert isinstance(image1, Image)
    assert isinstance(image2, Image)
    hash1 = imagehash.average_hash(image1)
    hash2 = imagehash.average_hash(image2)
    error_count = np.sum(np.bitwise_xor(hash1.hash, hash2.hash))
    return error_count / float(hash1.hash.size)


@pytest.mark.parametrize(("filename",), QUALITY_TEST_FILES)
def test_compose_quality(filename):
    psd = PSDImage.open(full_name(filename))
    preview = psd.topil()
    rendered = psd.compose()
    assert _calculate_hash_error(preview, rendered) <= 0.1


@pytest.mark.parametrize('filename', [
    'smartobject-layer.psd',
    'type-layer.psd',
    'gradient-fill.psd',
    'shape-layer.psd',
    'pixel-layer.psd',
    'solid-color-fill.psd',
    'pattern-fill.psd',
])
def test_compose_minimal(filename):
    source = PSDImage.open(full_name('layers-minimal/' + filename)).compose()
    reference = PSDImage.open(full_name('layers/' + filename)).compose()
    assert _calculate_hash_error(source, reference) <= 0.15
