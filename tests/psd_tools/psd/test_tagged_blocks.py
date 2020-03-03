from __future__ import absolute_import, unicode_literals
import pytest
import logging
import os
from IPython.display import display

from psd_tools.constants import Tag
from psd_tools.psd.base import IntegerElement
from psd_tools.psd.tagged_blocks import (
    TaggedBlocks,
    TaggedBlock,
    Annotation,
    Annotations,
    ChannelBlendingRestrictionsSetting,
    DescriptorBlock,
    PixelSourceData2,
    ReferencePoint,
    MetadataSettings,
)

from ..utils import check_read_write, check_write_read, TEST_ROOT

logger = logging.getLogger(__name__)


def test_tagged_blocks():
    blocks = TaggedBlocks([(
        Tag.LAYER_VERSION,
        TaggedBlock(key=Tag.LAYER_VERSION, data=IntegerElement(1))
    )])
    check_write_read(blocks)
    check_write_read(blocks, version=2)
    check_write_read(blocks, version=2, padding=4)
    display(blocks)
    assert blocks.get_data(Tag.LAYER_VERSION)
    assert blocks.get_data(Tag.LAYER_ID) is None
    assert len([1 for key in blocks if key == Tag.LAYER_VERSION]) == 1


def test_tagged_blocks_v2():
    filepath = os.path.join(TEST_ROOT, 'tagged_blocks', 'tagged_blocks_v2.dat')
    with open(filepath, 'rb') as f:
        fixture = f.read()
    check_read_write(TaggedBlocks, fixture, version=2, padding=4)


@pytest.mark.parametrize(
    'key, data, version, padding', [
        (Tag.LAYER_VERSION, IntegerElement(1), 1, 1),
        (Tag.LAYER_VERSION, IntegerElement(1), 2, 1),
        (Tag.LAYER_VERSION, IntegerElement(1), 1, 4),
        (Tag.LAYER_VERSION, IntegerElement(1), 2, 4),
    ]
)
def test_tagged_block(key, data, version, padding):
    check_write_read(
        TaggedBlock(key=key, data=data), version=version, padding=padding
    )


def test_annotations():
    check_write_read(
        Annotations([Annotation(data=b'\x05'),
                     Annotation(data=b'\x03')])
    )


@pytest.mark.parametrize(
    'fixture', [
        list(range(0)),
        list(range(1)),
        list(range(2)),
    ]
)
def test_channel_blending_restrictions_setting(fixture):
    check_write_read(ChannelBlendingRestrictionsSetting(fixture))


@pytest.mark.parametrize(
    'kls, filename', [
        (DescriptorBlock, 'cinf.dat'),
        (DescriptorBlock, 'extn_1.dat'),
        (DescriptorBlock, 'PxSc_1.dat'),
        (DescriptorBlock, 'frgb_1.dat'),
        (PixelSourceData2, 'pixel_source_data2.dat'),
        (MetadataSettings, 'shmd_1.dat'),
        (MetadataSettings, 'shmd_2.dat'),
    ]
)
def test_tagged_block_rw(kls, filename):
    filepath = os.path.join(TEST_ROOT, 'tagged_blocks', filename)
    with open(filepath, 'rb') as f:
        fixture = f.read()
    check_read_write(kls, fixture)


def test_reference_point():
    check_write_read(ReferencePoint([3, 5]))
