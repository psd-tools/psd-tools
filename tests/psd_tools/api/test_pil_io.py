from __future__ import absolute_import, unicode_literals
import pytest
import logging
import os

from psd_tools.api import pil_io
from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import ColorMode
from psd_tools.psd.patterns import Pattern
from ..utils import TEST_ROOT, full_name

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    'mode', [
        'L',
        'LA',
        'RGB',
        'RGBA',
        'CMYK',
        'CMYKA',
        'LAB',
        '1',
    ]
)
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
        (ColorMode.CMYK, True, 'CMYK'),  # CMYK with alpha is not supported.
        (ColorMode.LAB, False, 'LAB'),
    ]
)
def test_get_pil_mode(mode, alpha, expected):
    assert pil_io.get_pil_mode(mode, alpha) == expected


def test_convert_pattern_to_pil():
    filepath = os.path.join(TEST_ROOT, 'tagged_blocks', 'Patt_1.dat')
    with open(filepath, 'rb') as f:
        pattern = Pattern.read(f)

    assert pil_io.convert_pattern_to_pil(pattern)


def test_apply_icc_profile():
    filepath = full_name('colorprofiles/north_america_newspaper.psd')
    psd = PSDImage.open(filepath)
    no_icc = psd.topil(apply_icc=False)
    with_icc = psd.topil(apply_icc=True)
    assert no_icc.getextrema() != with_icc.getextrema()
