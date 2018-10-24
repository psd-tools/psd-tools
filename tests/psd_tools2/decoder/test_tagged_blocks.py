from __future__ import absolute_import, unicode_literals
import pytest
import logging
from psd_tools2.decoder.tagged_blocks import TaggedBlocks, TaggedBlock

from ..utils import check_write_read


logger = logging.getLogger(__name__)


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
