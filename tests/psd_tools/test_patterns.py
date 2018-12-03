# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import pytest

from psd_tools import PSDImage
from .utils import decode_psd


def test_text():
    psd = PSDImage(decode_psd('patterns.psd'))
    patterns = psd.patterns
    assert len(patterns) == 6

    try:
        from PIL import Image
        for pattern_id in patterns:
            pattern = patterns[pattern_id]
            image = pattern.as_PIL()
            assert image.width == pattern.width
            assert image.height == pattern.height
    except ImportError:
        pass
