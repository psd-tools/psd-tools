# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import pytest

from .utils import load_psd

DIMENSIONS = (
    ('1layer.psd',              (101, 55)),
    ('2layers.psd',             (101, 55)),
    ('32bit.psd',               (100, 150)),
    ('300dpi.psd',              (100, 150)),
    ('clipping-mask.psd',       (360, 200)),
    ('gradient fill.psd',       (100, 150)),
    ('group.psd',               (100, 200)),
    ('hidden-groups.psd',       (100, 200)),
    ('hidden-layer.psd',        (100, 150)),
    ('history.psd',             (100, 150)),
    ('mask.psd',                (100, 150)),
    ('note.psd',                (300, 300)),
    ('pen-text.psd',            (300, 300)),
    ('smart-object-slice.psd',  (100, 100)),
    ('transparentbg.psd',       (100, 150)),
    ('vector mask.psd',         (100, 150)),
)

@pytest.mark.parametrize(("filename", "size"), DIMENSIONS)
def test_dimensions(filename, size):
    w, h = size
    psd = load_psd(filename)
    assert psd.header.width == w
    assert psd.header.height == h