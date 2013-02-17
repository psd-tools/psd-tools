# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import pytest

from psd_tools import PSDImage
from .utils import decode_psd

TEXTS = [
    # filename, layer #, text
    ('text.psd', 0, 'Line 1\rLine 2\rLine 3 and text'),
    ('pen-text.psd', 2, 'Борис ельцин')
]

@pytest.mark.parametrize(('filename', 'layer_num', 'text'), TEXTS)
def test_text(filename, layer_num, text):
    psd = PSDImage(decode_psd(filename))

    layer = psd.layers[layer_num]
    text_data = layer._tagged_blocks['TySh'].text_data

    assert text_data.items[0][1].value == text
