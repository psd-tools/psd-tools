from __future__ import absolute_import, unicode_literals
import pytest
import logging

from psd_tools.api.psd_image import PSDImage
from psd_tools.api.layers import Group
from psd_tools.constants import BlendMode

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
    'pixel_layer',
    'shape_layer',
    'smartobject_layer',
    'type_layer',
    'group',
    'adjustment_layer',
    'fill_layer',
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
    layer._record.tobytes()
    layer.name = u'\ud83d\udc7d'
    assert layer.name == u'\ud83d\udc7d'
    layer._record.tobytes()

    layer.visible = False
    assert layer.visible is False

    layer.opacity = 128
    assert layer.opacity == 128

    layer.blend_mode = BlendMode.LINEAR_DODGE
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
        request.getfixturevalue(request.param), {
            'pixel_layer': False,
            'group': True
        }.get(request.param)
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
        'pixel_layer',
        'smartobject_layer',
        'type_layer',
        'fill_layer',
        'shape_layer',
    }
    return (request.getfixturevalue(request.param), is_image)


def test_topil(topil_args):
    from PIL.Image import Image
    fixture, is_image = topil_args
    image = fixture.topil()

    channel_ids = [c.id for c in fixture._record.channel_info if c.id >= -1]
    for channel in channel_ids:
        fixture.topil(channel)

    assert isinstance(image, Image) if is_image else image is None


def test_clip_adjustment():
    psd = PSDImage.open(full_name('clip-adjustment.psd'))
    assert len(psd) == 1
    layer = psd[0]
    assert layer.kind == 'type'
    assert len(layer.clip_layers) == 1


def test_type_layer(type_layer):
    assert type_layer.text == 'A'
    assert type_layer.transform == (
        1.0000000000000002, 0.0, 0.0, 1.0, 0.0, 4.978787878787878
    )
    assert type_layer.engine_dict
    assert type_layer.resource_dict
    assert type_layer.document_resources
    assert type_layer.warp


def test_group_writable_properties(group):
    assert group.blend_mode == BlendMode.PASS_THROUGH
    group.blend_mode = BlendMode.SCREEN
    assert group.blend_mode == BlendMode.SCREEN


def test_group_extract_bbox():
    psd = PSDImage.open(full_name('hidden-groups.psd'))
    assert Group.extract_bbox(psd[1:], False) == (40, 72, 83, 134)
    assert Group.extract_bbox(psd[1:], True) == (25, 34, 83, 134)
