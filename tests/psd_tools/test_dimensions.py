# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import pytest

from .utils import load_psd, decode_psd, with_psb

from psd_tools.user_api.psd_image import PSDImage, BBox
from psd_tools.decoder.image_resources import ResolutionInfo
from psd_tools.constants import (
    DisplayResolutionUnit, DimensionUnit, ImageResourceID
)

DIMENSIONS = with_psb((
    ('1layer.psd',              (101, 55)),
    ('2layers.psd',             (101, 55)),
    ('32bit.psd',               (100, 150)),
    ('300dpi.psd',              (100, 150)),
    ('clipping-mask.psd',       (360, 200)),
    ('gradient-fill.psd',       (100, 150)),
    ('group.psd',               (100, 200)),
    ('hidden-groups.psd',       (100, 200)),
    ('hidden-layer.psd',        (100, 150)),
    ('history.psd',             (100, 150)),
    ('mask.psd',                (100, 150)),
    ('note.psd',                (300, 300)),
    ('pen-text.psd',            (300, 300)),
    ('smart-object-slice.psd',  (100, 100)),
    ('transparentbg.psd',       (100, 150)),
    ('transparentbg-gimp.psd',  (40, 40)),
    ('vector-mask.psd',         (100, 150)),
    ('gray0.psd',               (400, 359)),
    ('gray1.psd',               (1800, 1200)),
    ('empty-layer.psd',         (100, 150)),
))

BBOXES = (
    ('1layer.psd', 0, BBox(0, 0, 101, 55)),
    ('2layers.psd', 0, BBox(8, 4, 93, 50)),
    ('2layers.psd', 1, BBox(0, 0, 101, 55)),
    ('group.psd', 0, BBox(25, 24, 66, 98)),
    ('empty-layer.psd', 0, BBox(37, 58, 51, 72)),
    ('empty-layer.psd', 1, BBox(0, 0, 100, 150)),
)

RESOLUTIONS = (
    ('1layer.psd', ResolutionInfo(
        h_res=72.0, h_res_unit=DisplayResolutionUnit.PIXELS_PER_INCH,
        v_res=72.0, v_res_unit=DisplayResolutionUnit.PIXELS_PER_INCH,
        width_unit=DimensionUnit.INCH, height_unit=DimensionUnit.INCH)),
    ('group.psd', ResolutionInfo(
        h_res=72.0, h_res_unit=DisplayResolutionUnit.PIXELS_PER_INCH,
        v_res=72.0, v_res_unit=DisplayResolutionUnit.PIXELS_PER_INCH,
        width_unit=DimensionUnit.CM, height_unit=DimensionUnit.CM)),
    ('1layer.psb', ResolutionInfo(
        h_res=72.0, h_res_unit=DisplayResolutionUnit.PIXELS_PER_INCH,
        v_res=72.0, v_res_unit=DisplayResolutionUnit.PIXELS_PER_INCH,
        width_unit=DimensionUnit.CM, height_unit=DimensionUnit.CM)),
    ('group.psb', ResolutionInfo(
        h_res=72.0, h_res_unit=DisplayResolutionUnit.PIXELS_PER_INCH,
        v_res=72.0, v_res_unit=DisplayResolutionUnit.PIXELS_PER_INCH,
        width_unit=DimensionUnit.CM, height_unit=DimensionUnit.CM)),
)


@pytest.mark.parametrize(("filename", "size"), DIMENSIONS)
def test_dimensions(filename, size):
    w, h = size
    psd = load_psd(filename)
    assert psd.header.width == w
    assert psd.header.height == h


@pytest.mark.parametrize(("filename", "resolution"), RESOLUTIONS)
def test_resolution(filename, resolution):
    psd = decode_psd(filename)
    psd_res = dict(
        (block.resource_id, block.data) for block in psd.image_resource_blocks
    )
    assert psd_res[ImageResourceID.RESOLUTION_INFO] == resolution


@pytest.mark.parametrize(("filename", "size"), DIMENSIONS)
def test_dimensions_api(filename, size):
    psd = PSDImage(decode_psd(filename))
    assert psd.header.width == size[0]
    assert psd.header.height == size[1]


@pytest.mark.parametrize(("filename", "layer_index", "bbox"), BBOXES)
def test_bbox(filename, layer_index, bbox):
    psd = PSDImage(decode_psd(filename))
    layer = psd.layers[layer_index]
    assert layer.bbox == bbox
