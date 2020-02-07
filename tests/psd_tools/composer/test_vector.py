from __future__ import absolute_import, unicode_literals
import pytest
import logging

from psd_tools import PSDImage
from psd_tools.constants import Tag
from psd_tools.composer.vector import (
    draw_solid_color_fill, draw_pattern_fill, draw_gradient_fill
)
from psd_tools.psd.descriptor import Double
from psd_tools.terminology import Enum, Key, Type

from ..utils import full_name
from .test_composer import _calculate_hash_error

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(("filename", ), [
    ('path-operations/combine.psd', ),
    ('path-operations/exclude-first.psd', ),
    ('path-operations/exclude.psd', ),
    ('path-operations/intersect-all.psd', ),
    ('path-operations/intersect-first.psd', ),
    ('path-operations/subtract-all.psd', ),
    ('path-operations/subtract-first.psd', ),
    ('path-operations/subtract-second.psd', ),
])
def test_draw_vector_mask(filename):
    psd = PSDImage.open(full_name(filename))
    preview = psd.topil().convert('RGB')
    rendered = psd.compose(force=True).convert('RGB')
    assert _calculate_hash_error(preview, rendered) <= 0.1


@pytest.mark.xfail(reason='Low stroke quality')
@pytest.mark.parametrize(("filename", ), [
    ('stroke.psd', ),
])
def test_draw_stroke(filename):
    psd = PSDImage.open(full_name(filename))
    preview = psd.topil().convert('RGB')
    rendered = psd.compose(force=True).convert('RGB')
    assert _calculate_hash_error(preview, rendered) <= 0.1


def test_draw_solid_color_fill():
    psd = PSDImage.open(full_name('layers-minimal/solid-color-fill.psd'))
    setting = psd[0].tagged_blocks.get_data(Tag.SOLID_COLOR_SHEET_SETTING)
    draw_solid_color_fill(psd.size, setting)


def test_draw_pattern_fill():
    psd = PSDImage.open(full_name('layers-minimal/pattern-fill.psd'))
    setting = psd[0].tagged_blocks.get_data(Tag.PATTERN_FILL_SETTING)
    draw_pattern_fill(psd.size, psd, setting)
    setting[b'Scl '] = Double(50.)
    setting[b'Opct'] = Double(67.)
    draw_pattern_fill(psd.size, psd, setting)


def test_draw_gradient_fill():
    psd = PSDImage.open(full_name('layers-minimal/gradient-fill.psd'))
    setting = psd[0].tagged_blocks.get_data(Tag.GRADIENT_FILL_SETTING)
    draw_gradient_fill(psd.size, setting)

    for angle in (-90., 0., 90., 180.):
        setting.get(Key.Angle.value).value = angle
        draw_gradient_fill(psd.size, setting)

    setting.get(b'Type').enum = Enum.Radial.value
    draw_gradient_fill(psd.size, setting)


@pytest.mark.parametrize(("filename", ), [
    ('gradient-styles.psd', ),
    ('gradient-sizes.psd', ),
])
def test_gradient_styles(filename):
    psd = PSDImage.open(full_name(filename))
    for artboard in psd:
        for layer in artboard:
            setting = layer.tagged_blocks.get_data(Tag.GRADIENT_FILL_SETTING)
            form = setting.get(Key.Gradient).get(Type.GradientForm).enum
            reference = layer.compose().convert('RGB')
            rendered = layer.compose(force=True).convert('RGB')
            if form == Enum.CustomStops:
                assert _calculate_hash_error(reference, rendered) <= 0.1
            elif form == Enum.ColorNoise:
                # Noise gradient is not of good quality.
                with pytest.raises(AssertionError):
                    assert _calculate_hash_error(reference, rendered) <= 0.1
