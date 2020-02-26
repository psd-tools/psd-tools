from __future__ import absolute_import, unicode_literals
import pytest
import logging
from psd_tools.psd.tagged_blocks import (
    TaggedBlocks, TaggedBlock, IntegerElement
)
from psd_tools.psd.layer_and_mask import (
    LayerAndMaskInformation, LayerInfo, LayerRecords, LayerRecord, ChannelInfo,
    LayerFlags, LayerBlendingRanges, MaskFlags, MaskData, MaskParameters,
    ChannelImageData, ChannelDataList, ChannelData, GlobalLayerMaskInfo
)
from psd_tools.constants import ChannelID, Compression, Tag

from ..utils import check_write_read, check_read_write

logger = logging.getLogger(__name__)


def test_layer_and_mask_information():
    check_write_read(LayerAndMaskInformation())


def test_layer_info():
    check_write_read(LayerInfo())

    layer_records = LayerRecords([
        LayerRecord(
            channel_info=[
                ChannelInfo(id=0, length=18),
                ChannelInfo(id=-1, length=18),
            ]
        )
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
    ((False, False, False, False, False), ),
    ((True, True, True, True, True), ),
])
def test_layer_flags_wr(args):
    check_write_read(LayerFlags(*args))


@pytest.mark.parametrize(['fixture'], [
    (b'(', ),
    (b'\t', ),
])
def test_layer_flags_rw(fixture):
    check_read_write(LayerFlags, fixture)


def test_layer_blending_ranges():
    check_write_read(LayerBlendingRanges())
    check_write_read(
        LayerBlendingRanges([(0, 1), (0, 1)], [
            [(0, 1), (0, 1)],
            [(0, 1), (0, 1)],
            [(0, 1), (0, 1)],
        ])
    )


def test_layer_record():
    tagged_blocks = TaggedBlocks([
        (
            Tag.LAYER_VERSION,
            TaggedBlock(key=Tag.LAYER_VERSION, data=IntegerElement(0))
        ),
    ])
    check_write_read(LayerRecord())
    check_write_read(LayerRecord(name='foo', tagged_blocks=tagged_blocks))
    check_write_read(LayerRecord(tagged_blocks=tagged_blocks), version=2)


def test_layer_record_channel_sizes():
    layer_record = LayerRecord(
        left=0,
        top=0,
        right=100,
        bottom=120,
        channel_info=[
            ChannelInfo(id=ChannelID.CHANNEL_0),
            ChannelInfo(id=ChannelID.USER_LAYER_MASK),
            ChannelInfo(id=ChannelID.REAL_USER_LAYER_MASK),
        ],
        mask_data=MaskData(
            left=20,
            top=20,
            right=80,
            bottom=90,
            real_left=10,
            real_top=10,
            real_right=90,
            real_bottom=100,
        )
    )
    channel_sizes = layer_record.channel_sizes
    assert len(channel_sizes) == 3
    assert channel_sizes[0] == (100, 120)
    assert channel_sizes[1] == (60, 70)
    assert channel_sizes[2] == (80, 90)


def test_mask_flags_wr():
    check_write_read(MaskFlags())
    check_write_read(MaskFlags(True, True, True, True, True))


@pytest.mark.parametrize(['fixture'], [
    (b'(', ),
    (b'\t', ),
])
def test_mask_flags_rw(fixture):
    check_read_write(MaskFlags, fixture)


@pytest.mark.parametrize(['args'], [
    (dict(), ),
    (
        dict(
            flags=MaskFlags(parameters_applied=True),
            parameters=MaskParameters(255, 1.0, None, None)
        ),
    ),
    (
        dict(
            real_flags=MaskFlags(True, True, True, True, True),
            real_background_color=255,
            real_top=0,
            real_left=0,
            real_bottom=100,
            real_right=100,
        ),
    ),
    (
        dict(
            flags=MaskFlags(parameters_applied=True),
            parameters=MaskParameters(None, 1.0, None, 1.0),
            real_flags=MaskFlags(True, True, True, True, True),
            real_background_color=255,
            real_top=0,
            real_left=0,
            real_bottom=100,
            real_right=100,
        ),
    ),
])
def test_mask_data(args):
    check_write_read(MaskData(**args))


# This doesn't work, but is there such a case?
@pytest.mark.xfail
@pytest.mark.parametrize(['args'], [
    (
        dict(
            flags=MaskFlags(parameters_applied=True),
            parameters=MaskParameters(None, 1.0, None, 1.0),
        ),
    ),
    (
        dict(
            flags=MaskFlags(parameters_applied=True),
            parameters=MaskParameters(255, 1.0, 255, 1.0),
        ),
    ),
])
def test_mask_data_failure(args):
    check_write_read(MaskData(**args))


@pytest.mark.parametrize(['fixture'], [
    (
        b'\x00\x00\x00\x14\x00\x00\x00\x11\x00\x00\x00\x0c\x00\x00\x00\xb3'
        b'\x00\x00\x00D\x00\x18\x04\xcc',
    ),
])
def test_mask_data_rw(fixture):
    check_read_write(MaskData, fixture)


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
        LayerRecord(
            channel_info=[
                ChannelInfo(id=0, length=18),
                ChannelInfo(id=-1, length=18),
            ]
        )
    ])
    channel_data_list = ChannelDataList([
        ChannelData(0, b'\xff' * 16),
        ChannelData(0, b'\xff' * 16),
    ])
    check_write_read(
        ChannelImageData([channel_data_list]), layer_records=layer_records
    )


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
    check_write_read(ChannelDataList(channel_items), channel_info=channel_info)


def test_channel_data():
    check_write_read(ChannelData(data=b''), length=0)
    check_write_read(ChannelData(data=b'\xFF' * 8), length=8)


RAW_IMAGE_3x3_8bit = b'\x00\x01\x02\x01\x01\x01\x01\x00\x00'
RAW_IMAGE_2x2_16bit = b'\x00\x01\x00\x02\x00\x03\x00\x04'


@pytest.mark.parametrize(
    'compression, data, width, height, depth, version', [
        (Compression.RAW, RAW_IMAGE_3x3_8bit, 3, 3, 8, 1),
        (Compression.RLE, RAW_IMAGE_3x3_8bit, 3, 3, 8, 1),
        (Compression.ZIP, RAW_IMAGE_3x3_8bit, 3, 3, 8, 1),
        (Compression.RAW, RAW_IMAGE_3x3_8bit, 3, 3, 8, 2),
        (Compression.RLE, RAW_IMAGE_3x3_8bit, 3, 3, 8, 2),
        (Compression.ZIP, RAW_IMAGE_3x3_8bit, 3, 3, 8, 2),
        (Compression.RAW, RAW_IMAGE_2x2_16bit, 2, 2, 16, 1),
        (Compression.RLE, RAW_IMAGE_2x2_16bit, 2, 2, 16, 1),
        (Compression.ZIP, RAW_IMAGE_2x2_16bit, 2, 2, 16, 1),
        (Compression.RAW, RAW_IMAGE_2x2_16bit, 2, 2, 16, 2),
        (Compression.RLE, RAW_IMAGE_2x2_16bit, 2, 2, 16, 2),
        (Compression.ZIP, RAW_IMAGE_2x2_16bit, 2, 2, 16, 2),
    ]
)
def test_channel_data_data(compression, data, width, height, depth, version):
    channel = ChannelData(compression)
    channel.set_data(data, width, height, depth, version)
    output = channel.get_data(width, height, depth, version)
    assert output == data, 'output=%r, expected=%r' % (output, data)


def test_global_layer_mask_info():
    check_write_read(GlobalLayerMaskInfo())
