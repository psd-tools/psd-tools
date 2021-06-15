from __future__ import absolute_import, unicode_literals

import logging

import pytest

from psd_tools.api import pil_io
from psd_tools.constants import ColorMode

logger = logging.getLogger(__name__)


@pytest.mark.parametrize('mode', [
    'L',
    'LA',
    'RGB',
    'RGBA',
    'CMYK',
    'CMYKA',
    'LAB',
    '1',
])
def test_get_color_mode(mode):
    assert isinstance(pil_io.get_color_mode(mode), ColorMode)


@pytest.mark.parametrize(
    'mode, alpha, expected',
    [
        (ColorMode.BITMAP, False, '1'),
        (ColorMode.GRAYSCALE, False, 'L'),
        (ColorMode.GRAYSCALE, True, 'LA'),
        (ColorMode.RGB, False, 'RGB'),
        (ColorMode.RGB, True, 'RGBA'),
        (ColorMode.CMYK, False, 'CMYK'),
        (ColorMode.CMYK, True, 'CMYK'),    # CMYK with alpha is not supported.
        (ColorMode.LAB, False, 'LAB'),
    ])
def test_get_pil_mode(mode, alpha, expected):
    assert pil_io.get_pil_mode(mode.name, alpha) == expected
