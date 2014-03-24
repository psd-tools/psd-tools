# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import pytest

from psd_tools import PSDImage, Layer, Group

from .utils import full_name, FuzzyInt

PIXEL_COLORS = (
    # filename                  probe point    pixel value
    ('1layer.psd',              (5, 5),       (0x27, 0xBA, 0x0F)),
    ('group.psd',               (10, 20),     (0xFF, 0xFF, 0xFF)),
    ('hidden-groups.psd',       (60, 100),    (0xE1, 0x0B, 0x0B)),
    ('hidden-layer.psd',        (0, 0),       (0xFF, 0xFF, 0xFF)),
#    ('note.psd',                (30, 30),     (0, 0, 0)), # what is it?
    ('smart-object-slice.psd',  (70, 80),     (0xAC, 0x19, 0x19)), # XXX: what is this test about?
)

TRANSPARENCY_PIXEL_COLORS = (
    ('transparentbg-gimp.psd',  (14, 14),     (0xFF, 0xFF, 0xFF, 0x13)),
    ('2layers.psd',             (70, 30),     (0xF1, 0xF3, 0xC1)), # why gimp shows it as F2F4C2 ?
)

MASK_PIXEL_COLORS = (
    ('clipping-mask.psd',       (182, 68),    (0xDA, 0xE6, 0xF7)), # this is a clipped point
    ('mask.psd',                (87, 7),      (0xFF, 0xFF, 0xFF)), # mask truncates the layer here
)

NO_LAYERS_PIXEL_COLORS = (
    ('history.psd',             (70, 85),     (0x24, 0x26, 0x29)),
)


PIXEL_COLORS_8BIT = (PIXEL_COLORS + NO_LAYERS_PIXEL_COLORS +
                     MASK_PIXEL_COLORS + TRANSPARENCY_PIXEL_COLORS)

PIXEL_COLORS_32BIT = (
    ('32bit.psd',               (75, 15),     (136, 139, 145)),
    ('32bit.psd',               (95, 15),     (0, 0, 0)),
    ('300dpi.psd',              (70, 30),     (0, 0, 0)),
    ('300dpi.psd',              (50, 60),     (214, 59, 59)),
    ('gradient fill.psd',       (10, 15),     (235, 241, 250)), # background
    ('gradient fill.psd',       (70, 50),     (0, 0, 0)), # black circle
    ('gradient fill.psd',       (50, 50),     (205, 144, 110)), # filled ellipse
    ('pen-text.psd',            (50, 50),     (229, 93, 93)),
    ('pen-text.psd',            (170, 40),    (0, 0, 0)),
    ('vector mask.psd',         (10, 15),     (255, 255, 255)),
    ('vector mask.psd',         (50, 90),     (221, 227, 236)),
    ('transparentbg.psd',       (0, 0),       (255, 255, 255, 0)),
    ('transparentbg.psd',       (50, 50),     (0, 0, 0, 255)),
    ('32bit5x5.psd',            (0, 0),       (235, 241, 250)), # why not equal to 16bit5x5.psd?
    ('32bit5x5.psd',            (4, 0),       (0, 0, 0)),
    ('32bit5x5.psd',            (1, 3),       (46, 196, 104)),
    ('empty-layer.psd',         (0, 0),       (255, 255, 255)),
)

PIXEL_COLORS_16BIT = (
    ('16bit5x5.psd', (0, 0), (236, 242, 251)),
    ('16bit5x5.psd', (4, 0), (0, 0, 0)),
    ('16bit5x5.psd', (1, 3), (46, 196, 104)),
)

PIXEL_COLORS_GRAYSCALE = (
    # exact colors depend on Gray ICC profile chosen,
    # so allow a wide range for some of the values
    ('gray0.psd', (0, 0), (255, 0)),
    ('gray0.psd', (70, 57), (FuzzyInt(5, 250), 255)),
    ('gray0.psd', (322, 65), (FuzzyInt(5, 250), 190)),

    ('gray1.psd', (0, 0), 255),
    ('gray1.psd', (900, 500), 0),
    ('gray1.psd', (400, 600), FuzzyInt(5, 250)),
)


LAYER_COLORS = (
    ('1layer.psd',      0,  (5, 5),       (0x27, 0xBA, 0x0F)),
    ('2layers.psd',     1,  (5, 5),       (0x27, 0xBA, 0x0F)),
    ('2layers.psd',     1,  (70, 30),     (0x27, 0xBA, 0x0F)),
    ('2layers.psd',     0,  (0, 0),       (0, 0, 0, 0)),
    ('2layers.psd',     0,  (62, 26),     (0xF2, 0xF4, 0xC2, 0xFE)),
)

LAYER_COLORS_MULTIBYTE = (
    ('16bit5x5.psd',    1,  (0, 0),     (236, 242, 251, 255)),
    ('16bit5x5.psd',    1,  (1, 3),     (46, 196, 104, 255)),
    ('32bit5x5.psd',    1,  (0, 0),     (235, 241, 250, 255)), # why not equal to 16bit5x5.psd?
    ('32bit5x5.psd',    1,  (1, 3),     (46, 196, 104, 255)),
    ('empty-layer.psd', 0,  (0, 0),     (255, 255, 255, 0)),
    ('semi-transparent-layers.psd', 0, (56, 44), (201, 54, 0, 0xFF)),
)

LAYER_COLORS_GRAYSCALE = (
    # gray0: layer 0 is shifted 35px to the right
    ('gray0.psd', 0, (0, 0), (255, 0)),
    ('gray0.psd', 0, (70-35, 57), (FuzzyInt(5, 250), 255)),
    ('gray0.psd', 0, (322-35, 65), (FuzzyInt(5, 250), 190)),

    # gray1: black ellipse
    ('gray1.psd', 0, (0, 0), (0, 0)),
    ('gray1.psd', 0, (500, 250), (0, 255)),

    # gray1: grey ellipse
    ('gray1.psd', 1, (0, 0), (FuzzyInt(5, 250), 0)),
    ('gray1.psd', 1, (700, 500), (FuzzyInt(5, 250), 255)),

    # gray1: background
    ('gray1.psd', 2, (0, 0), 255),
    ('gray1.psd', 2, (900, 500), 255),
    ('gray1.psd', 2, (400, 600), 255),
)


def color_PIL(psd, point):
    im = psd.as_PIL()
    return im.getpixel(point)


def color_pymaging(psd, point):
    im = psd.as_pymaging()
    return tuple(im.get_pixel(*point))

BACKENDS = [[color_PIL], [color_pymaging]]


@pytest.mark.parametrize(["get_color"], BACKENDS)
@pytest.mark.parametrize(["filename", "point", "color"], PIXEL_COLORS_8BIT)
def test_composite(filename, point, color, get_color):
    psd = PSDImage.load(full_name(filename))
    assert color == get_color(psd, point)


@pytest.mark.parametrize(["filename", "point", "color"], PIXEL_COLORS_32BIT)
def test_composite_32bit(filename, point, color):
    psd = PSDImage.load(full_name(filename))
    assert color == color_PIL(psd, point)


@pytest.mark.parametrize(["filename", "point", "color"], PIXEL_COLORS_16BIT)
def test_composite_16bit(filename, point, color):
    psd = PSDImage.load(full_name(filename))
    assert color == color_PIL(psd, point)


@pytest.mark.parametrize(["filename", "point", "color"], PIXEL_COLORS_GRAYSCALE)
def test_composite_grayscale(filename, point, color):
    psd = PSDImage.load(full_name(filename))
    assert color == color_PIL(psd, point)


@pytest.mark.parametrize(["get_color"], BACKENDS)
@pytest.mark.parametrize(["filename", "layer_num", "point", "color"], LAYER_COLORS)
def test_layer_colors(filename, layer_num, point, color, get_color):
    psd = PSDImage.load(full_name(filename))
    layer = psd.layers[layer_num]
    assert color == get_color(layer, point)


@pytest.mark.parametrize(["filename", "layer_num", "point", "color"], LAYER_COLORS_MULTIBYTE)
def test_layer_colors_multibyte(filename, layer_num, point, color):
    psd = PSDImage.load(full_name(filename))
    layer = psd.layers[layer_num]
    assert color == color_PIL(layer, point)


@pytest.mark.parametrize(["filename", "layer_num", "point", "color"], LAYER_COLORS_GRAYSCALE)
def test_layer_colors_grayscale(filename, layer_num, point, color):
    psd = PSDImage.load(full_name(filename))
    layer = psd.layers[layer_num]
    assert color == color_PIL(layer, point)


@pytest.mark.parametrize(["filename", "point", "color"], PIXEL_COLORS + MASK_PIXEL_COLORS + TRANSPARENCY_PIXEL_COLORS)
def test_layer_merging_size(filename, point, color):
    psd = PSDImage.load(full_name(filename))
    merged_image = psd.as_PIL_merged()
    assert merged_image.size == psd.as_PIL().size


@pytest.mark.parametrize(["filename", "point", "color"], PIXEL_COLORS)
def test_layer_merging_pixels(filename, point, color):
    psd = PSDImage.load(full_name(filename))
    merged_image = psd.as_PIL_merged()
    assert color[:3] == merged_image.getpixel(point)[:3]
    assert merged_image.getpixel(point)[3] == 255 # alpha channel


@pytest.mark.xfail
@pytest.mark.parametrize(["filename", "point", "color"], TRANSPARENCY_PIXEL_COLORS)
def test_layer_merging_pixels_transparency(filename, point, color):
    psd = PSDImage.load(full_name(filename))
    merged_image = psd.as_PIL_merged()
    assert color == merged_image.getpixel(point)
