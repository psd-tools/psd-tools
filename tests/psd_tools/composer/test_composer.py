from __future__ import absolute_import, unicode_literals
import pytest
import logging

from PIL import Image
import imagehash
import numpy as np

from psd_tools.api.psd_image import PSDImage
from psd_tools.api.layers import Group

from ..utils import full_name

logger = logging.getLogger(__name__)

QUALITY_TEST_FILES = [
    # ('mask-index.psd',),  # Transparent region in preview image is wrong...
    (
        'background-red-opacity-80.psd',
    ),
    ('32bit.psd', ),
]


def _normalize_alpha(image):
    if image.mode.endswith('A'):
        return Image.alpha_composite(Image.new(image.mode, image.size), image)
    return image


def _calculate_hash_error(image1, image2):
    assert isinstance(image1, Image.Image)
    assert isinstance(image2, Image.Image)
    hash1 = imagehash.average_hash(_normalize_alpha(image1))
    hash2 = imagehash.average_hash(_normalize_alpha(image2))
    error_count = np.sum(np.bitwise_xor(hash1.hash, hash2.hash))
    return error_count / float(hash1.hash.size)


@pytest.mark.parametrize(("filename", ), QUALITY_TEST_FILES)
def test_compose_quality(filename, threshold=0.1):
    psd = PSDImage.open(full_name(filename))
    preview = psd.topil()
    rendered = psd.compose(force=True)
    assert _calculate_hash_error(preview, rendered) <= threshold


@pytest.mark.parametrize(("filename", ), [
    ('path-operations/combine.psd', ),
    ('path-operations/exclude-first.psd', ),
    ('path-operations/exclude.psd', ),
    ('path-operations/intersect-all.psd', ),
    ('path-operations/intersect-first.psd', ),
    ('path-operations/subtract-all.psd', ),
    ('path-operations/subtract-first.psd', ),
    ('path-operations/subtract-second.psd', ),
    ('stroke.psd', ),
])
def test_compose_quality_rgb(filename):
    psd = PSDImage.open(full_name(filename))
    preview = psd.topil().convert('RGB')
    rendered = psd.compose(force=True).convert('RGB')
    assert _calculate_hash_error(preview, rendered) <= 0.1


@pytest.mark.parametrize(
    'filename', [
        'smartobject-layer.psd',
        'type-layer.psd',
        'gradient-fill.psd',
        'shape-layer.psd',
        'pixel-layer.psd',
        'solid-color-fill.psd',
        'pattern-fill.psd',
    ]
)
def test_compose_minimal(filename):
    source = PSDImage.open(full_name('layers-minimal/' + filename)).compose()
    reference = PSDImage.open(full_name('layers/' + filename)).compose(True)
    assert _calculate_hash_error(source, reference) <= 0.172


@pytest.mark.parametrize(
    'colormode, depth', [
        ('cmyk', 8),
        ('duotone', 8),
        ('grayscale', 8),
        ('index_color', 8),
        ('rgb', 8),
        ('rgba', 8),
        ('lab', 8),
        ('cmyk', 16),
        ('grayscale', 16),
        ('multichannel', 16),
        ('lab', 16),
        ('rgb', 16),
        ('grayscale', 32),
        ('rgb', 32),
    ]
)
def test_compose_colormodes(colormode, depth):
    filename = 'colormodes/4x4_%gbit_%s.psd' % (depth, colormode)
    psd = PSDImage.open(full_name(filename))
    assert isinstance(psd.compose(), Image.Image)


def test_compose_artboard():
    psd = PSDImage.open(full_name('artboard.psd'))
    document_image = psd.compose()
    assert document_image.size == psd.size
    artboard = psd[0]
    artboard_image = artboard.compose()
    assert artboard_image.size == artboard.size
    assert artboard.size != Group.extract_bbox(artboard)


def test_apply_icc_profile():
    filepath = full_name('colorprofiles/north_america_newspaper.psd')
    psd = PSDImage.open(filepath)
    no_icc = psd.compose(apply_icc=False)
    with_icc = psd.compose(apply_icc=True)
    assert no_icc.getextrema() != with_icc.getextrema()


def test_compose_bbox():
    psd = PSDImage.open(full_name('layers/smartobject-layer.psd'))
    bbox = (1, 1, 31, 31)
    size = (bbox[2] - bbox[0], bbox[3] - bbox[1])
    assert psd.compose().size == psd.size
    assert psd.compose(bbox=bbox).size == size
    assert psd[0].compose().size == psd[0].size
    assert psd[0].compose(bbox=bbox).size == size


def test_apply_mask():
    psd = PSDImage.open(full_name('masks/2.psd'))
    image = Image.open(full_name('masks/2.png'))
    rendered = psd.compose()
    assert image.size == rendered.size
    assert _calculate_hash_error(image, rendered) <= 0.1

    for i, layer in enumerate(psd):
        image = Image.open(full_name('masks/2-ellipse{}.png'.format(i + 1)))
        image = image
        rendered = layer.compose()
        assert image.size == rendered.size
        assert _calculate_hash_error(image, rendered) <= 0.1


def test_apply_opacity():
    psd = PSDImage.open(full_name('opacity-fill.psd'))
    image = psd.compose(force=True)
    assert image.getpixel((0, 0))[-1] == psd.compose().getpixel((0, 0))[-1]
