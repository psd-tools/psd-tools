from __future__ import absolute_import, unicode_literals
import pytest
import logging
import os

from psd_tools2.api.psd_image import PSDImage
from psd_tools2.api.layers import Layer
from psd_tools2.constants import BlendMode

from ..utils import full_name


logger = logging.getLogger(__name__)


@pytest.fixture
def pixel_layer():
    return PSDImage.open(full_name('layers/pixel-layer.psd'))[0]


@pytest.fixture
def adjustment_layer():
    return PSDImage.open(full_name('layers/brightness-contrast.psd'))[0]


@pytest.fixture
def fill_layer():
    return PSDImage.open(full_name('layers/solid-color-fill.psd'))[0]


@pytest.fixture
def shape_layer():
    return PSDImage.open(full_name('layers/shape-layer.psd'))[0]


@pytest.fixture
def smartobject_layer():
    return PSDImage.open(full_name('layers/smartobject-layer.psd'))[0]


@pytest.fixture
def type_layer():
    return PSDImage.open(full_name('layers/type-layer.psd'))[0]


@pytest.fixture
def group():
    return PSDImage.open(full_name('layers/group.psd'))[0]


ALL_FIXTURES = [
    'pixel_layer', 'shape_layer', 'smartobject_layer', 'type_layer', 'group',
    'adjustment_layer', 'fill_layer',
]


def test_pixel_layer_properties(pixel_layer):
    layer = pixel_layer
    assert layer.name == 'Pixel', 'layer.name = %s' % type(layer.name)
    assert layer.kind == 'pixel'
    assert layer.visible is True
    assert layer.opacity == 255
    assert isinstance(layer.parent, PSDImage)
    assert isinstance(layer.blend_mode, BlendMode)
    assert layer.left == 1
    assert layer.top == 1
    assert layer.right == 30
    assert layer.bottom == 30
    assert layer.width == 29
    assert layer.height == 29
    assert layer.size == (29, 29)
    assert layer.bbox == (1, 1, 30, 30)
    assert layer.clip_layers == []
    assert layer.tagged_blocks is not None
    assert layer.layer_id == 3


def test_pixel_layer_writable_properties(pixel_layer):
    layer = pixel_layer
    layer.name = 'foo'
    assert layer.name == 'foo'
    layer.name = u'\ud83d\udc7d'
    assert layer.name == u'\ud83d\udc7d'

    layer.visible = False
    assert layer.visible is False

    layer.opacity = 128
    assert layer.opacity == 128

    layer.blend_mode = 'linear_dodge'
    assert layer.blend_mode == BlendMode.LINEAR_DODGE

    layer.left = 2
    assert layer.left == 2
    layer.top = 2
    assert layer.top == 2
    assert layer.size == (29, 29)

    layer.offset = (1, 1)
    assert layer.offset == (1, 1)
    assert layer.size == (29, 29)


def test_layer_is_visible(pixel_layer):
    assert pixel_layer.is_visible()


@pytest.fixture(params=['pixel_layer', 'group'])
def is_group_args(request):
    return (
        request.getfixturevalue(request.param),
        {'pixel_layer': False, 'group': True}.get(request.param)
    )


def test_layer_is_group(is_group_args):
    layer, expected = is_group_args
    assert layer.is_group() == expected


def test_layer_has_mask(pixel_layer):
    assert pixel_layer.has_mask() is False


@pytest.fixture(params=ALL_FIXTURES)
def kind_args(request):
    expected = request.param.replace('_layer', '')
    expected = expected.replace('fill', 'solidcolorfill')
    expected = expected.replace('adjustment', 'brightnesscontrast')
    return (request.getfixturevalue(request.param), expected)


def test_layer_kind(kind_args):
    layer, expected = kind_args
    assert layer.kind == expected


@pytest.fixture(params=ALL_FIXTURES)
def topil_args(request):
    is_image = request.param in {
        'pixel_layer', 'smartobject_layer', 'type_layer', 'fill_layer',
        'shape_layer',
    }
    return (request.getfixturevalue(request.param), is_image)


def test_topil(topil_args):
    from PIL.Image import Image
    fixture, is_image = topil_args
    image = fixture.topil()
    assert isinstance(image, Image) if is_image else image is None


def test_clip_adjustment():
    psd = PSDImage.open(full_name('clip-adjustment.psd'))
    assert len(psd) == 1
    layer = psd[0]
    assert layer.kind == 'type'
    assert len(layer.clip_layers) == 1


def test_vector_mask():
    psd = PSDImage.open(full_name('vector-mask2.psd'))
    for index in range(len(psd)):
        layer = psd[index]
        assert layer.has_vector_mask() is True
        assert layer.vector_mask
        expected = index in (1, 2, 3, 5, 9)
        assert layer.has_origination() is expected
        if expected:
            assert layer.origination
        else:
            assert layer.origination is None
        if layer.kind == 'shape':
            expected = index in (2, 4)
            assert layer.has_stroke() is expected
            assert layer.has_stroke_content() is expected
            if expected:
                assert layer.stroke is not None
                assert layer.stroke_content is not None
            else:
                assert layer.stroke is None
                assert layer.stroke_content is None
