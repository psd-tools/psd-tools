from __future__ import absolute_import, unicode_literals
import pytest
import logging

from psd_tools2.psd.filter_effects import (
    FilterEffect, FilterEffectChannel
)

from ..utils import check_write_read


logger = logging.getLogger(__name__)


@pytest.mark.parametrize('args', [
    ('uuid', 1, (0, 0, 512, 512), 8, 3, [
        FilterEffectChannel(1, 0, b'\x00'),
        FilterEffectChannel(1, 0, b'\x00'),
        FilterEffectChannel(1, 0, b'\x00'),
        FilterEffectChannel(1, 0, b'\x00'),
        FilterEffectChannel(1, 0, b'\x00'),
    ], None),
    ('uuid', 1, (0, 0, 512, 512), 8, 3, [
        FilterEffectChannel(1, 0, b'\x00'),
        FilterEffectChannel(1, 0, b'\x00'),
        FilterEffectChannel(1, 0, b'\x00'),
        FilterEffectChannel(1, 0, b'\x00'),
        FilterEffectChannel(1, 0, b'\x00'),
    ], ((0, 0, 512, 512), 0, b'\x00')),
])
def test_filter_effect(args):
    check_write_read(FilterEffect(*args))


@pytest.mark.parametrize('is_written, compression, data', [
    (0, None, b''),
    (1, None, b''),
    (1, 0, b''),
    (1, 0, b'\x00'),
])
def test_filter_effect_channel(is_written, compression, data):
    check_write_read(FilterEffectChannel(is_written, compression, data))
