# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import pytest

from psd_tools import PSDImage
from .utils import decode_psd

@pytest.mark.xfail
def test_text():
    psd = PSDImage(decode_psd('pen-text.psd'))

    eltsin = psd.layers[2]
    text_data = eltsin._tagged_blocks['TySh'].text_data

    # Extra \x00 is added to string?
    #assert text_data.items[0][1].value == 'Борис ельцин\x00'
    assert text_data.items[0][1].value == 'Борис ельцин'
