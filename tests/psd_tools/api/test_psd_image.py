from __future__ import absolute_import, unicode_literals
import pytest
import logging
import os
from IPython.lib.pretty import pprint

from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import Compression, ColorMode
from ..utils import full_name

logger = logging.getLogger(__name__)


@pytest.fixture
def fixture():
    return PSDImage.open(full_name('colormodes/4x4_8bit_rgb.psd'))


@pytest.mark.parametrize(
    'args', [
        ('L', (16, 24), (0, )),
        ('LA', (16, 24), (0, 255)),
        ('RGB', (16, 24), (255, 128, 64)),
        ('RGBA', (16, 24), (255, 128, 64, 255)),
        ('CMYK', (16, 24), (255, 128, 64, 128)),
    ]
)
def test_new(args):
    PSDImage.new(*args)


@pytest.mark.parametrize('filename', [
    'colormodes/4x4_8bit_rgb.psd',
])
def test_open_save(filename, tmpdir):
    input_path = full_name(filename)
    PSDImage.open(input_path)
    with open(input_path, 'rb') as f:
        PSDImage.open(f)


def test_save(fixture, tmpdir):
    output_path = os.path.join(str(tmpdir), 'output.psd')
    fixture.save(output_path)
    with open(output_path, 'wb') as f:
        fixture.save(f)


def test_pilio(fixture):
    image = fixture.topil()
    for i in range(fixture.channels):
        fixture.topil(channel=i)
    psd = PSDImage.frompil(image, compression=Compression.RAW)
    assert psd._record.header == fixture._record.header
    assert psd._record.image_data == fixture._record.image_data


def test_properties(fixture):
    assert fixture.name == 'Root'
    assert fixture.kind == 'psdimage'
    assert fixture.visible is True
    assert fixture.parent is None
    assert fixture.left == 0
    assert fixture.top == 0
    assert fixture.right == 4
    assert fixture.bottom == 4
    assert fixture.width == 4
    assert fixture.height == 4
    assert fixture.size == (4, 4)
    assert fixture.bbox == (0, 0, 4, 4)
    assert fixture.viewbox == (0, 0, 4, 4)
    assert fixture.image_resources
    assert fixture.tagged_blocks
    assert fixture.color_mode == ColorMode.RGB
    assert fixture.version == 1


def test_version():
    PSDImage.open(full_name('gray0.psb')).version == 2


def test_is_visible(fixture):
    assert fixture.is_visible() is True


def test_is_group(fixture):
    assert fixture.is_group() is True


def test_has_preview(fixture):
    assert fixture.has_preview() is True


def test_thumnail(fixture):
    assert fixture.has_thumbnail() is True
    assert fixture.thumbnail()


def test_repr_pretty(fixture):
    fixture.__repr__()
    pprint(fixture)


@pytest.mark.parametrize('filename', [
    os.path.join('third-party-psds', 'cactus_top.psd'),
])
def test_open(filename):
    assert isinstance(PSDImage.open(full_name(filename)), PSDImage)
