from __future__ import absolute_import, unicode_literals
import pytest
import logging
from psd_tools2.psd.tagged_blocks import (
    TaggedBlocks, TaggedBlock, Integer, ChannelBlendingRestrictionsSetting,
)
from psd_tools2.psd.effects_layer import (
    CommonStateInfo, ShadowInfo, InnerGlowInfo, OuterGlowInfo, BevelInfo,
    SolidFillInfo,
)
from psd_tools2.psd.filter_effects import (
    FilterEffect, FilterEffectChannel
)

from psd_tools2.constants import TaggedBlockID

from ..utils import check_write_read


logger = logging.getLogger(__name__)


def test_tagged_blocks():
    blocks = TaggedBlocks([
        (TaggedBlockID.LAYER_VERSION,
         TaggedBlock(key=TaggedBlockID.LAYER_VERSION, data=Integer(1)))
    ])
    check_write_read(blocks)
    check_write_read(blocks, version=2)
    check_write_read(blocks, version=2, padding=4)


@pytest.mark.parametrize('key, data, version, padding', [
    (TaggedBlockID.LAYER_VERSION, Integer(1), 1, 1),
    (TaggedBlockID.LAYER_VERSION, Integer(1), 2, 1),
    (TaggedBlockID.LAYER_VERSION, Integer(1), 1, 4),
    (TaggedBlockID.LAYER_VERSION, Integer(1), 2, 4),
])
def test_tagged_block(key, data, version, padding):
    check_write_read(TaggedBlock(key=key, data=data),
                     version=version, padding=padding)


@pytest.mark.parametrize('fixture', [
    list(range(0)),
    list(range(1)),
    list(range(2)),
])
def test_channel_blending_restrictions_setting(fixture):
    check_write_read(ChannelBlendingRestrictionsSetting(fixture))


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


@pytest.mark.parametrize('cls', [
    CommonStateInfo, ShadowInfo, InnerGlowInfo, OuterGlowInfo, BevelInfo,
    SolidFillInfo,
])
def test_effects_layer_item(cls):
    check_write_read(cls())
