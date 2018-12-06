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
    return PSDImage.open(full_name('layers/adjustment-layer.psd'))[0]


@pytest.fixture
def fill_layer():
    return PSDImage.open(full_name('layers/fill-layer.psd'))[0]


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


def test_pixel_layer_properties(pixel_layer):
    layer = pixel_layer
    assert layer.name == 'Pixel', 'layer.name = %s' % type(layer.name)
    assert layer.kind == 'pixel'
    assert layer.visible == True
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


def test_pixel_layer_writable_properties(pixel_layer):
    layer = pixel_layer
    layer.name = 'foo'
    assert layer.name == 'foo'
    layer.name = u'\ud83d\udc7d'
    assert layer.name == u'\ud83d\udc7d'

    layer.visible = False
    assert layer.visible == False

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


@pytest.fixture(params=['pixel', 'group'])
def is_group_args(request):
    return (
        request.getfixturevalue(request.param),
        {'pixel': False, 'group': True}.get(request.param)
    )


def test_layer_is_group(is_group_args):
    layer, expected = is_group_args
    assert layer.is_group() == expected


def test_layer_is_group(pixel_layer):
    assert pixel_layer.has_mask() == False
