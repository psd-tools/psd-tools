from __future__ import absolute_import, unicode_literals
import pytest
import logging
from psd_tools2.decoder.tagged_blocks import (
    TaggedBlocks, TaggedBlock, Integer,
)

from psd_tools2.constants import TaggedBlockID

from ..utils import check_write_read


logger = logging.getLogger(__name__)


def test_tagged_blocks():
    blocks = TaggedBlocks([
        (TaggedBlockID.LAYER_ID,
         TaggedBlock(key=TaggedBlockID.LAYER_ID, data=Integer(1)))
    ])
    check_write_read(blocks)
    check_write_read(blocks, version=2)
    check_write_read(blocks, version=2, padding=4)


@pytest.mark.parametrize('key, data, version, padding', [
    (TaggedBlockID.LAYER_ID, Integer(1), 1, 1),
    (TaggedBlockID.LAYER_ID, Integer(1), 2, 1),
    (TaggedBlockID.LAYER_ID, Integer(1), 1, 4),
    (TaggedBlockID.LAYER_ID, Integer(1), 2, 4),
])
def test_tagged_block(key, data, version, padding):
    check_write_read(TaggedBlock(key=key, data=data),
                     version=version, padding=padding)
