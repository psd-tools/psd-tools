# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import pytest

from psd_tools import PSDImage
from .utils import decode_psd, with_psb

TEXTS = with_psb([
    # filename, layer #, text
    ('text.psd', 0, 'Line 1\rLine 2\rLine 3 and text'),
    ('pen-text.psd', 2, 'Борис ельцин'),
])

TARGET_FILES = with_psb([
    ('unicode_pathname.psd',),
])


@pytest.mark.parametrize(('filename', 'layer_num', 'text'), TEXTS)
def test_text(filename, layer_num, text):
    psd = PSDImage(decode_psd(filename))

    layer = psd.layers[layer_num]
    assert layer.text == text
    assert len(layer.matrix) == 6
    assert len(layer.fontset) == 3       # Specific to files.
    assert layer.writing_direction == 0  # Specific to files.
    assert layer.full_text.startswith(text)
    assert all([isinstance(span, dict) for span in layer.style_spans()])


def test_no_text():
    psd = PSDImage(decode_psd('1layer.psd'))
    assert not hasattr(psd.layers[0], 'text_data')


@pytest.mark.parametrize(('filename',), TARGET_FILES)
def test_unicode_pathname(filename):
    decode_data = decode_psd(filename)
    assert decode_data
