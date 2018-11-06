from __future__ import absolute_import, unicode_literals
import pytest
import logging

from psd_tools2.psd.patterns import (
    Patterns, VirtualMemoryArray
)

from ..utils import check_write_read


logger = logging.getLogger(__name__)


@pytest.mark.parametrize('args', [
    (0, None, None, None, None, b''),
    (1, 8, (0, 0, 8, 8), 8, 0, b'\x00' * 64),
])
def test_filter_effect_channel(args):
    check_write_read(VirtualMemoryArray(*args))
