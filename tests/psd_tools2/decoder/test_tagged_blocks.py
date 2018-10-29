from __future__ import absolute_import, unicode_literals
import pytest
import logging
from psd_tools2.decoder.tagged_blocks import TaggedBlocks, TaggedBlock
from psd_tools2.constants import TaggedBlockID

from ..utils import check_write_read


logger = logging.getLogger(__name__)


def test_tagged_blocks():
    blocks = TaggedBlocks([TaggedBlock(
        key=TaggedBlockID.LINKED_LAYER_EXTERNAL
    )])
    check_write_read(blocks)
    check_write_read(blocks, version=2)
    check_write_read(blocks, version=2, padding=4)


@pytest.mark.parametrize('key, version, padding', [
    (TaggedBlockID.SOLID_COLOR_SHEET_SETTING, 1, 1),
    (TaggedBlockID.LINKED_LAYER_EXTERNAL, 1, 1),
    (TaggedBlockID.SOLID_COLOR_SHEET_SETTING, 2, 1),
    (TaggedBlockID.LINKED_LAYER_EXTERNAL, 2, 1),
    (TaggedBlockID.SOLID_COLOR_SHEET_SETTING, 1, 4),
    (TaggedBlockID.LINKED_LAYER_EXTERNAL, 1, 4),
    (TaggedBlockID.SOLID_COLOR_SHEET_SETTING, 2, 4),
    (TaggedBlockID.LINKED_LAYER_EXTERNAL, 2, 4),
])
def test_tagged_block(key, version, padding):
    check_write_read(TaggedBlock(key=key), version=version, padding=padding)
