# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
from psd_tools import PSDImage, Layer, Group
from psd_tools.constants import BlendMode

from .utils import decode_psd

def test_simple():
    image = PSDImage(decode_psd('1layer.psd'))
    assert len(image.layers) == 1

    layer = image.layers[0]
    assert layer.name == 'Фон'
    assert layer.bbox == (0, 0, 101, 55)
    assert layer.visible
    assert layer.opacity == 255
    assert layer.blend_mode == BlendMode.NORMAL
