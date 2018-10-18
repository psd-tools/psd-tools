from __future__ import absolute_import, unicode_literals
import pytest
from psd_tools2.decoder.layer_and_mask import (
    LayerAndMaskInformation, LayerInfo, LayerRecord, ChannelInfo, LayerFlags,
    LayerBlendingRanges, TaggedBlocks, TaggedBlock,
)

from ..utils import check_write_read


# def test_layer_and_mask_information():
#     pass


# def test_layer_info():
#     pass


def test_channel_info():
    check_write_read(ChannelInfo(id=0, length=1), version=1)
    check_write_read(ChannelInfo(id=0, length=1), version=2)


@pytest.mark.parametrize(['args'], [
    ((False, False, False),),
    (( True,  True,  True),),
    (( True, False,  None),),
])
def test_layer_flags(args):
    check_write_read(LayerFlags(*args))


def test_layer_blending_ranges():
    check_write_read(LayerBlendingRanges())
    check_write_read(LayerBlendingRanges(
        ((0, 1), (0, 1)),
        [
            ((0, 1), (0, 1)),
            ((0, 1), (0, 1)),
            ((0, 1), (0, 1)),
        ]
    ))


def test_tagged_blocks():
    blocks = TaggedBlocks([TaggedBlock(key=b'lnkE')])
    check_write_read(blocks)
    check_write_read(blocks, version=2)
    check_write_read(blocks, version=2, padding=4)


def test_tagged_block():
    check_write_read(TaggedBlock(key=b'SoCo'))
    check_write_read(TaggedBlock(key=b'lnkE'))
    check_write_read(TaggedBlock(key=b'SoCo'), version=2)
    check_write_read(TaggedBlock(key=b'lnkE'), version=2)
    check_write_read(TaggedBlock(key=b'SoCo'), padding=4)
    check_write_read(TaggedBlock(key=b'lnkE'), padding=4)
    check_write_read(TaggedBlock(key=b'SoCo'), version=2, padding=4)
    check_write_read(TaggedBlock(key=b'lnkE'), version=2, padding=4)


# def test_layer_record():
#     check_write_read(LayerRecord())
