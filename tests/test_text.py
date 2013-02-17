# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import pytest

from psd_tools import PSDImage
from .utils import decode_psd

def test_text():
    psd = PSDImage(decode_psd('text.psd'))

    eltsin = psd.layers[0]
    text_data = eltsin._tagged_blocks['TySh'].text_data

    assert text_data.items[0][1].value == 'Line 1\rLine 2\rLine 3 and text'
