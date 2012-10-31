# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import pytest

from psd_tools import PSDImage, Layer, Group

from .utils import decode_psd

PIXEL_VALUES = (
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

PIXEL_VALUES_32BIT = (
    ('32bit.psd',               (10, 15),     (0, 0, 0)),
    ('300dpi.psd',              (10, 15),     (0, 0, 0)),
    ('gradient fill.psd',       (10, 15),     (0, 0, 0)),
    ('pen-text.psd',            (30, 30),     (0, 0, 0)),
    ('vector mask.psd',         (10, 15),     (0, 0, 0)),
    ('transparentbg.psd',       (10, 15),     (0, 0, 0)),
)



def _assert_image_pixel(filename, probe_point, pixel_value):
    psd = PSDImage(decode_psd(filename))
    image = psd.composite_image()
    assert image.getpixel(probe_point) == pixel_value

@pytest.mark.parametrize(["filename", "probe_point", "pixel_value"], PIXEL_VALUES)
def test_composite_image_pixels(filename, probe_point, pixel_value):
    _assert_image_pixel(filename, probe_point, pixel_value)

@pytest.mark.xfail
@pytest.mark.parametrize(["filename", "probe_point", "pixel_value"], PIXEL_VALUES_32BIT)
def test_composite_image_pixels_32bit(filename, probe_point, pixel_value):
    _assert_image_pixel(filename, probe_point, pixel_value)

