# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import pytest

from psd_tools import PSDImage, Layer, Group

from .utils import decode_psd

PIXEL_COLORS = (
    # filename                  probe point    pixel value
    ('1layer.psd',              (5, 5),       (0x27, 0xBA, 0x0F)),
    ('2layers.psd',             (70, 30),     (0xF1, 0xF3, 0xC1)), # why gimp shows it as F2F4C2 ?
    ('clipping-mask.psd',       (182, 68),    (0xDA, 0xE6, 0xF7)), # this is a clipped point
    ('group.psd',               (10, 20),     (0xFF, 0xFF, 0xFF)),
    ('hidden-groups.psd',       (60, 100),    (0xE1, 0x0B, 0x0B)),
    ('hidden-layer.psd',        (0, 0),       (0xFF, 0xFF, 0xFF)),
    ('history.psd',             (70, 85),     (0x24, 0x26, 0x29)),
    ('mask.psd',                (87, 7),      (0xFF, 0xFF, 0xFF)), # mask truncates the layer here
#    ('note.psd',                (30, 30),     (0, 0, 0)), # what is it?
    ('smart-object-slice.psd',  (70, 80),     (0xAC, 0x19, 0x19)), # XXX: what is this test about?
    ('transparentbg-gimp.psd',  (14, 14),     (0xFF, 0xFF, 0xFF, 0x13)),
)

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
    ('32bit5x5.psd',            (0, 0),       (235, 241, 250)),
    ('32bit5x5.psd',            (4, 0),       (0, 0, 0)),
    ('32bit5x5.psd',            (1, 3),       (46, 196, 104)),
)

PIXEL_COLORS_16BIT = (
    ('16bit5x5.psd', (0, 0), (236, 242, 251)),
    ('16bit5x5.psd', (4, 0), (0, 0, 0)),
    ('16bit5x5.psd', (1, 3), (46, 196, 104)),
)


def _assert_image_pixel(filename, point, color):
    psd = PSDImage(decode_psd(filename))
    image = psd.composite_image()
    assert image.getpixel(point) == color

@pytest.mark.parametrize(["filename", "point", "color"], PIXEL_COLORS)
def test_composite_image_pixels(filename, point, color):
    _assert_image_pixel(filename, point, color)

@pytest.mark.parametrize(["filename", "point", "color"], PIXEL_COLORS_32BIT)
def test_composite_image_pixels_32bit(filename, point, color):
    _assert_image_pixel(filename, point, color)

@pytest.mark.parametrize(["filename", "point", "color"], PIXEL_COLORS_16BIT)
def test_composite_16bit(filename, point, color):
    _assert_image_pixel(filename, point, color)
