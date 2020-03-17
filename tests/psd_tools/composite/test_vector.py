import pytest
import logging

from psd_tools import PSDImage
from psd_tools.constants import Tag
from psd_tools.psd.descriptor import Double
from psd_tools.terminology import Enum, Key, Type
from psd_tools.composite import composite
from psd_tools.composite.vector import (
    draw_solid_color_fill, draw_pattern_fill, draw_gradient_fill
)

from ..utils import full_name
from .test_composite import check_composite_quality, _mse

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(("filename", ), [
    ('path-operations/combine.psd', ),
    ('path-operations/combine-group.psd', ),
    ('path-operations/exclude-first.psd', ),
    ('path-operations/exclude.psd', ),
    ('path-operations/exclude-group.psd', ),
    ('path-operations/intersect-all.psd', ),
    ('path-operations/intersect-first.psd', ),
    ('path-operations/intersect-group.psd', ),
    ('path-operations/subtract-all.psd', ),
    ('path-operations/subtract-first.psd', ),
    ('path-operations/subtract-second.psd', ),
    ('path-operations/subtract-group.psd', ),
])
def test_path_operations(filename):
    check_composite_quality(filename, 0.02)


@pytest.mark.parametrize(("filename", ), [
    ('stroke.psd', ),
])
def test_draw_stroke(filename):
    check_composite_quality(filename, 0.01, force=True)


@pytest.mark.parametrize(("filename", ), [
    ('effects/stroke-composite.psd', ),  # Fix me!
])
@pytest.mark.xfail
def test_draw_stroke_fail(filename):
    check_composite_quality(filename, 0.01, force=True)


def test_draw_solid_color_fill():
    psd = PSDImage.open(full_name('layers-minimal/solid-color-fill.psd'))
    desc = psd[0].tagged_blocks.get_data(Tag.SOLID_COLOR_SHEET_SETTING)
    draw_solid_color_fill(psd.viewbox, desc)


@pytest.mark.parametrize('filename', [
    'layers-minimal/pattern-fill.psd',
    'layers/pattern-fill.psb'
])
def test_draw_pattern_fill(filename):
    psd = PSDImage.open(full_name(filename))
    desc = psd[0].tagged_blocks.get_data(Tag.PATTERN_FILL_SETTING)
    draw_pattern_fill(psd.viewbox, psd, desc)
    desc[b'Scl '] = Double(50.)
    desc[b'Opct'] = Double(67.)
    draw_pattern_fill(psd.viewbox, psd, desc)


def test_draw_gradient_fill():
    psd = PSDImage.open(full_name('layers-minimal/gradient-fill.psd'))
    desc = psd[0].tagged_blocks.get_data(Tag.GRADIENT_FILL_SETTING)
    draw_gradient_fill(psd.viewbox, desc)
    for angle in (-90., 0., 90., 180.):
        desc.get(Key.Angle.value).value = angle
        draw_gradient_fill(psd.viewbox, desc)
    desc.get(b'Type').enum = Enum.Radial.value
    draw_gradient_fill(psd.viewbox, desc)


@pytest.mark.parametrize(("filename", ), [
    ('gradient-styles.psd', ),
    ('gradient-sizes.psd', ),
])
def test_gradient_styles(filename):
    psd = PSDImage.open(full_name(filename))
    for artboard in psd:
        for layer in artboard:
            desc = layer.tagged_blocks.get_data(Tag.GRADIENT_FILL_SETTING)
            form = desc.get(Key.Gradient).get(Type.GradientForm).enum
            reference = composite(layer)[0]
            result = composite(layer, force=True)[0]
            if form == Enum.CustomStops:
                assert _mse(reference, result) <= 0.08
            elif form == Enum.ColorNoise:
                # Noise gradient is not of good quality.
                assert _mse(reference, result) <= 0.2
