from __future__ import absolute_import, unicode_literals
import pytest
import logging
import os

from psd_tools2.constants import TaggedBlockID
from psd_tools2.psd.base import IntegerElement
from psd_tools2.psd.tagged_blocks import (
    TaggedBlocks, TaggedBlock, Annotation, Annotations,
    ChannelBlendingRestrictionsSetting, DescriptorBlock, PixelSourceData2,
    ReferencePoint,
)

from ..utils import check_read_write, check_write_read, TEST_ROOT, full_name


logger = logging.getLogger(__name__)


def test_tagged_blocks():
    blocks = TaggedBlocks([
        (TaggedBlockID.LAYER_VERSION,
         TaggedBlock(key=TaggedBlockID.LAYER_VERSION, data=IntegerElement(1)))
    ])
    check_write_read(blocks)
    check_write_read(blocks, version=2)
    check_write_read(blocks, version=2, padding=4)


@pytest.mark.parametrize('key, data, version, padding', [
    (TaggedBlockID.LAYER_VERSION, IntegerElement(1), 1, 1),
    (TaggedBlockID.LAYER_VERSION, IntegerElement(1), 2, 1),
    (TaggedBlockID.LAYER_VERSION, IntegerElement(1), 1, 4),
    (TaggedBlockID.LAYER_VERSION, IntegerElement(1), 2, 4),
])
def test_tagged_block(key, data, version, padding):
    check_write_read(TaggedBlock(key=key, data=data),
                     version=version, padding=padding)


def test_annotations():
    check_write_read(Annotations([
        Annotation(data=b'\x05'),
        Annotation(data=b'\x03')
    ]))


@pytest.mark.parametrize('fixture', [
    list(range(0)),
    list(range(1)),
    list(range(2)),
])
def test_channel_blending_restrictions_setting(fixture):
    check_write_read(ChannelBlendingRestrictionsSetting(fixture))


def test_computer_info():
    filepath = os.path.join(TEST_ROOT, 'tagged_blocks', 'cinf.dat')
    with open(filepath, 'rb') as f:
        fixture = f.read()
    check_read_write(DescriptorBlock, fixture)


def test_pixel_source_data2_wr():
    filepath = os.path.join(TEST_ROOT, 'tagged_blocks',
                            'pixel_source_data2.dat')
    with open(filepath, 'rb') as f:
        fixture = f.read()
    check_read_write(PixelSourceData2, fixture)


def test_reference_point():
    check_write_read(ReferencePoint([3, 5]))
