from __future__ import absolute_import, unicode_literals
import pytest
import logging
from psd_tools2.decoder.layer_and_mask import (
    LayerAndMaskInformation, LayerInfo, LayerRecords, LayerRecord,
    ChannelInfo, LayerFlags, LayerBlendingRanges, TaggedBlocks, TaggedBlock,
    MaskFlags, MaskData, MaskParameters, ChannelImageData, ChannelDataList,
    ChannelData, GlobalLayerMaskInfo
)

from ..utils import check_write_read


def test_layer_and_mask_information():
    check_write_read(LayerAndMaskInformation())


def test_layer_info():
    check_write_read(LayerInfo())

    layer_records = LayerRecords([
        LayerRecord(channel_info=[
            ChannelInfo(id=0, length=18),
            ChannelInfo(id=-1, length=18),
        ])
    ])
    channel_image_data = ChannelImageData([
        ChannelDataList([
            ChannelData(0, b'\xff' * 16),
            ChannelData(0, b'\xff' * 16),
        ])
    ])

    check_write_read(LayerInfo(1, layer_records, channel_image_data))


def test_channel_info():
    check_write_read(ChannelInfo(id=0, length=1), version=1)
    check_write_read(ChannelInfo(id=0, length=1), version=2)


@pytest.mark.parametrize(['args'], [
    ((False, False, False, False, False),),
    (( True,  True,  True,  True,  True),),
])
def test_layer_flags(args):
    check_write_read(LayerFlags(*args))


def test_layer_blending_ranges():
    check_write_read(LayerBlendingRanges())
    check_write_read(LayerBlendingRanges(
        [(0, 1), (0, 1)],
        [
            [(0, 1), (0, 1)],
            [(0, 1), (0, 1)],
            [(0, 1), (0, 1)],
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


def test_layer_record():
    tagged_blocks = TaggedBlocks([TaggedBlock(key=b'lnkE')])
    # check_write_read(LayerRecord())
    check_write_read(LayerRecord(name='foo', tagged_blocks=tagged_blocks))
    # check_write_read(LayerRecord(tagged_blocks=tagged_blocks), version=2)


def test_mask_flags():
    check_write_read(MaskFlags())
    check_write_read(MaskFlags(True, True, True, True, True))


def test_mask_data():
    parameters = MaskParameters(None, 1.0, None, 1.0)
    real_flags = MaskFlags(True, True, True, True, True)
    real_top, real_left, real_bottom, real_right = 0, 0, 100, 100
    check_write_read(MaskData())

    # This doesn't work, but is there such a case?
    # check_write_read(MaskData(
    #     flags=MaskFlags(parameters_applied=True),
    #     parameters=parameters,
    # ))
    # check_write_read(MaskData(
    #     flags=MaskFlags(parameters_applied=True),
    #     parameters=MaskParameters(255, 1.0, 255, 1.0),
    # ))
    check_write_read(MaskData(
        flags=MaskFlags(parameters_applied=True),
        parameters=MaskParameters(255, 1.0, None, None),
    ))
    check_write_read(MaskData(
        real_flags=real_flags, real_background_color=255, real_top=real_top,
        real_left=real_left, real_bottom=real_bottom, real_right=real_right,
    ))
    check_write_read(MaskData(
        flags=MaskFlags(parameters_applied=True), parameters=parameters,
        real_flags=real_flags, real_background_color=255, real_top=real_top,
        real_left=real_left, real_bottom=real_bottom, real_right=real_right,
    ))


def test_mask_parameters():
    check_write_read(MaskParameters())
    check_write_read(MaskParameters(None, None, None, 1.0))
    check_write_read(MaskParameters(255, None, None, 1.0))
    check_write_read(MaskParameters(None, 1.0, None, 1.0))
    check_write_read(MaskParameters(255, 1.0, 255, None))
    assert MaskParameters().tobytes() == b'\x00'
    assert len(MaskParameters(255, 1.0, 255, 1.0).tobytes()) == 19


def test_channel_image_data():
    check_write_read(ChannelImageData(), layer_records=LayerRecords())

    layer_records = LayerRecords([
        LayerRecord(channel_info=[
            ChannelInfo(id=0, length=18),
            ChannelInfo(id=-1, length=18),
        ])
    ])
    channel_data_list = ChannelDataList([
        ChannelData(0, b'\xff' * 16),
        ChannelData(0, b'\xff' * 16),
    ])
    check_write_read(ChannelImageData([channel_data_list]),
                     layer_records=layer_records)


def test_channel_data_list():
    channel_info = [
        ChannelInfo(id=0, length=20),
        ChannelInfo(id=1, length=20),
        ChannelInfo(id=2, length=20),
        ChannelInfo(id=-1, length=20),
    ]
    channel_items = [
        ChannelData(0, b'\x00' * 18),
        ChannelData(0, b'\x00' * 18),
        ChannelData(0, b'\x00' * 18),
        ChannelData(0, b'\x00' * 18),
    ]
    check_write_read(ChannelDataList(channel_items),
                     channel_info=channel_info)


def test_channel_data():
    check_write_read(ChannelData())


def test_global_layer_mask_info():
    check_write_read(GlobalLayerMaskInfo())

