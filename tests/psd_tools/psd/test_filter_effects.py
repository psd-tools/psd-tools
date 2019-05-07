from __future__ import absolute_import, unicode_literals
import pytest
import logging
import os

from psd_tools.psd.filter_effects import (
    FilterEffects, FilterEffect, FilterEffectChannel, FilterEffectExtra
)

from ..utils import check_write_read, check_read_write, TEST_ROOT

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    'args', [
        (
            'uuid', 1, (0, 0, 512, 512), 8, 3, [
                FilterEffectChannel(1, 0, b'\x00'),
                FilterEffectChannel(1, 0, b'\x00'),
                FilterEffectChannel(1, 0, b'\x00'),
                FilterEffectChannel(1, 0, b'\x00'),
                FilterEffectChannel(1, 0, b'\x00'),
            ], None
        ),
        (
            'uuid', 1, (0, 0, 512, 512), 8, 3, [
                FilterEffectChannel(1, 0, b'\x00'),
                FilterEffectChannel(1, 0, b'\x00'),
                FilterEffectChannel(1, 0, b'\x00'),
                FilterEffectChannel(1, 0, b'\x00'),
                FilterEffectChannel(1, 0, b'\x00'),
            ], FilterEffectExtra(1, [0, 0, 512, 512], 0, b'\x00')
        ),
        (
            'uuid', 1, (0, 0, 512, 512), 8, 3, [
                FilterEffectChannel(1, 0, b'\x00'),
                FilterEffectChannel(1, 0, b'\x00'),
                FilterEffectChannel(1, 0, b'\x00'),
                FilterEffectChannel(1, 0, b'\x00'),
                FilterEffectChannel(1, 0, b'\x00'),
            ], FilterEffectExtra(0)
        ),
    ]
)
def test_filter_effect(args):
    check_write_read(FilterEffect(*args))


@pytest.mark.parametrize(
    'is_written, compression, data', [
        (0, None, b''),
        (1, None, b''),
        (1, 0, b''),
        (1, 0, b'\x00'),
    ]
)
def test_filter_effect_channel(is_written, compression, data):
    check_write_read(FilterEffectChannel(is_written, compression, data))


@pytest.mark.parametrize(
    'filename', [
        'filter_effects_1.dat',
        'filter_effects_2.dat',
    ]
)
def test_filter_effects_rw(filename):
    filepath = os.path.join(TEST_ROOT, 'tagged_blocks', filename)
    with open(filepath, 'rb') as f:
        fixture = f.read()
    check_read_write(FilterEffects, fixture)
