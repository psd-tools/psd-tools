from __future__ import absolute_import, unicode_literals
import pytest
import logging
import os

import numpy as np
from psd_tools.api import numpy_io
from psd_tools.api.psd_image import PSDImage
from psd_tools.psd.patterns import Pattern
from ..utils import TEST_ROOT, full_name

logger = logging.getLogger(__name__)


def test_convert_pattern_to_pil():
    filepath = os.path.join(TEST_ROOT, 'tagged_blocks', 'Patt_1.dat')
    with open(filepath, 'rb') as f:
        pattern = Pattern.read(f)

    assert isinstance(numpy_io.get_pattern(pattern, version=1), np.ndarray)


@pytest.mark.parametrize(
    'colormode, depth', [
        ('bitmap', 1),
        ('cmyk', 8),
        ('duotone', 8),
        ('grayscale', 8),
        ('index_color', 8),
        ('rgb', 8),
        ('rgba', 8),
        ('lab', 8),
        ('multichannel', 16),
    ]
)
def test_numpy_colormodes(colormode, depth):
    filename = 'colormodes/4x4_%gbit_%s.psd' % (depth, colormode)
    psd = PSDImage.open(full_name(filename))
    assert isinstance(psd.numpy(), np.ndarray)
    for layer in psd:
        assert isinstance(layer.numpy(), (np.ndarray, type(None)))
