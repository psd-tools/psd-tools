from __future__ import absolute_import, unicode_literals

import logging

import imagehash
import numpy as np
import pytest
from PIL.Image import Image

from psd_tools.api.psd_image import PSDImage
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
    rendered = psd.compose(force=True)
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
    reference = PSDImage.open(full_name('layers/' + filename)).compose(True)
    assert _calculate_hash_error(source, reference) <= 0.172


@pytest.mark.parametrize('colormode, depth', [
    ('cmyk', 8),
    ('duotone', 8),
    ('grayscale', 8),
    ('index_color', 8),
    ('rgb', 8),
    ('lab', 8),
    ('cmyk', 16),
    ('grayscale', 16),
    ('multichannel', 16),
    ('lab', 16),
    ('rgb', 16),
    ('grayscale', 32),
    ('rgb', 32),
])
def test_compose_colormodes(colormode, depth):
    filename = 'colormodes/4x4_%gbit_%s.psd' % (depth, colormode)
    psd = PSDImage.open(full_name(filename))
    assert isinstance(psd.compose(), Image)
