import logging
import os

import pytest

from psd_tools.psd.filter_effects import (
    FilterEffect,
    FilterEffectChannel,
    FilterEffectExtra,
    FilterEffects,
)

from ..utils import TEST_ROOT, check_read_write, check_write_read

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "args",
    [
        (
            "uuid",
            1,
            (0, 0, 512, 512),
            8,
            3,
            [
                FilterEffectChannel(is_written=1, compression=0, data=b"\x00"),
                FilterEffectChannel(is_written=1, compression=0, data=b"\x00"),
                FilterEffectChannel(is_written=1, compression=0, data=b"\x00"),
                FilterEffectChannel(is_written=1, compression=0, data=b"\x00"),
                FilterEffectChannel(is_written=1, compression=0, data=b"\x00"),
            ],
            None,
        ),
        (
            "uuid",
            1,
            (0, 0, 512, 512),
            8,
            3,
            [
                FilterEffectChannel(is_written=1, compression=0, data=b"\x00"),
                FilterEffectChannel(is_written=1, compression=0, data=b"\x00"),
                FilterEffectChannel(is_written=1, compression=0, data=b"\x00"),
                FilterEffectChannel(is_written=1, compression=0, data=b"\x00"),
                FilterEffectChannel(is_written=1, compression=0, data=b"\x00"),
            ],
            FilterEffectExtra(is_written=1, rectangle=[0, 0, 512, 512], compression=0, data=b"\x00"),
        ),
        (
            "uuid",
            1,
            (0, 0, 512, 512),
            8,
            3,
            [
                FilterEffectChannel(is_written=1, compression=0, data=b"\x00"),
                FilterEffectChannel(is_written=1, compression=0, data=b"\x00"),
                FilterEffectChannel(is_written=1, compression=0, data=b"\x00"),
                FilterEffectChannel(is_written=1, compression=0, data=b"\x00"),
                FilterEffectChannel(is_written=1, compression=0, data=b"\x00"),
            ],
            FilterEffectExtra(is_written=0),
        ),
    ],
)
def test_filter_effect(args):
    check_write_read(FilterEffect(*args))


@pytest.mark.parametrize(
    "is_written, compression, data",
    [
        (0, None, b""),
        (1, None, b""),
        (1, 0, b""),
        (1, 0, b"\x00"),
    ],
)
def test_filter_effect_channel(is_written, compression, data):
    check_write_read(FilterEffectChannel(is_written=is_written, compression=compression, data=data))


@pytest.mark.parametrize(
    "filename",
    [
        "filter_effects_1.dat",
        "filter_effects_2.dat",
    ],
)
def test_filter_effects_rw(filename):
    filepath = os.path.join(TEST_ROOT, "tagged_blocks", filename)
    with open(filepath, "rb") as f:
        fixture = f.read()
    check_read_write(FilterEffects, fixture)
