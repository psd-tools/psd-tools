import logging

import pytest

from psd_tools import PSDImage
from psd_tools.api.layers import Group
from psd_tools.composite import composite
from psd_tools.composite.paint import (
    draw_gradient_fill,
    draw_pattern_fill,
    draw_solid_color_fill,
)
from psd_tools.constants import Tag
from psd_tools.psd.descriptor import Double
from psd_tools.terminology import Enum, Key, Type

from ..utils import full_name
from .test_composite import _mse, check_composite_quality

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    ("filename",),
    [
        ("path-operations/combine.psd",),
        ("path-operations/combine-group.psd",),
        ("path-operations/exclude-first.psd",),
        ("path-operations/exclude.psd",),
        ("path-operations/exclude-group.psd",),
        ("path-operations/intersect-all.psd",),
        ("path-operations/intersect-first.psd",),
        ("path-operations/intersect-group.psd",),
        ("path-operations/subtract-all.psd",),
        ("path-operations/subtract-first.psd",),
        ("path-operations/subtract-second.psd",),
        ("path-operations/subtract-group.psd",),
    ],
)
def test_path_operations(filename: str) -> None:
    check_composite_quality(filename, 0.02)


@pytest.mark.parametrize(
    ("filename",),
    [
        ("stroke.psd",),
    ],
)
def test_draw_stroke(filename: str) -> None:
    check_composite_quality(filename, 0.01, force=True)


@pytest.mark.parametrize(
    ("filename",),
    [
        ("effects/stroke-composite.psd",),  # Fix me!
    ],
)
@pytest.mark.xfail
def test_draw_stroke_fail(filename: str) -> None:
    check_composite_quality(filename, 0.01, force=True)


def test_draw_solid_color_fill() -> None:
    psd = PSDImage.open(full_name("layers-minimal/solid-color-fill.psd"))
    desc = psd[0].tagged_blocks.get_data(Tag.SOLID_COLOR_SHEET_SETTING)
    draw_solid_color_fill(psd.viewbox, psd.color_mode, desc)


@pytest.mark.parametrize(
    "filename", ["layers-minimal/pattern-fill.psd", "layers/pattern-fill.psb"]
)
def test_draw_pattern_fill(filename: str) -> None:
    psd = PSDImage.open(full_name(filename))
    desc = psd[0].tagged_blocks.get_data(Tag.PATTERN_FILL_SETTING)
    draw_pattern_fill(psd.viewbox, psd, desc)
    desc[b"Scl "] = Double(50.0)
    desc[b"Opct"] = Double(67.0)
    draw_pattern_fill(psd.viewbox, psd, desc)


def test_draw_gradient_fill() -> None:
    psd = PSDImage.open(full_name("layers-minimal/gradient-fill.psd"))
    desc = psd[0].tagged_blocks.get_data(Tag.GRADIENT_FILL_SETTING)
    draw_gradient_fill(psd.viewbox, psd.color_mode, desc)
    for angle in (-90.0, 0.0, 90.0, 180.0):
        desc.get(Key.Angle.value).value = angle
        draw_gradient_fill(psd.viewbox, psd.color_mode, desc)
    desc.get(b"Type").enum = Enum.Radial.value
    draw_gradient_fill(psd.viewbox, psd.color_mode, desc)


@pytest.mark.parametrize(
    ("filename",),
    [
        ("gradient-styles.psd",),
        ("gradient-sizes.psd",),
    ],
)
def test_gradient_styles(filename: str) -> None:
    psd = PSDImage.open(full_name(filename))
    for artboard in psd:
        assert isinstance(artboard, Group)
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


# The threshold is per fixture rather than shared. A single loose one hid #743:
# the Lab file passed at 0.05 while sitting at 0.033, an error big enough that
# a near-neutral mid-tone was rendering as a dark saturated colour. Correcting
# the normalization takes it to 0.0013, and 0.01 catches that regression with
# 3x to spare.
#
# Not tighter, because what is left is not a rounding floor: 98% of the residual
# MSE comes from the ~12% of pixels along the stroke edges, which is
# rasterization geometry and moves with the aggdraw and Pillow versions CI
# happens to resolve. The tight bound on this normalization lives in
# test_paint.py instead, on a fixture of solid fills with no edges to raster --
# there it is 2/255 on the worst pixel.
#
# The other three fixtures are untouched by that change and keep the old bound.
@pytest.mark.parametrize(
    ("filename", "threshold"),
    [
        ("descriptors/stroke-color-descriptors-rgb.psd", 0.05),
        ("descriptors/stroke-color-descriptors-gray.psd", 0.05),
        ("descriptors/stroke-color-descriptors-lab.psd", 0.01),
        ("descriptors/stroke-color-descriptors-hsb-with-rgb-mode.psd", 0.05),
    ],
)
def test_stroke_color(filename: str, threshold: float) -> None:
    check_composite_quality(filename, threshold, force=True)
