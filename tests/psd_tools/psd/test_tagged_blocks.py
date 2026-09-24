import logging
import os
from typing import Any, List, Type

import pytest

from psd_tools.constants import BlendMode, SectionDivider, Tag
from psd_tools.psd.base import IntegerElement
from psd_tools.psd.tagged_blocks import (
    Annotation,
    Annotations,
    ChannelBlendingRestrictionsSetting,
    DescriptorBlock,
    DescriptorBlock2,
    MetadataSettings,
    PixelSourceData2,
    ReferencePoint,
    SectionDividerSetting,
    TaggedBlock,
    TaggedBlocks,
)

from ..utils import TEST_ROOT, check_read_write, check_write_read

logger = logging.getLogger(__name__)


def test_tagged_blocks() -> None:
    blocks = TaggedBlocks(
        [  # type: ignore[arg-type]
            (
                Tag.LAYER_VERSION,
                TaggedBlock(key=Tag.LAYER_VERSION, data=IntegerElement(1)),  # type: ignore[arg-type]
            )
        ]
    )
    check_write_read(blocks)
    check_write_read(blocks, version=2)
    check_write_read(blocks, version=2, padding=4)
    assert blocks.get_data(Tag.LAYER_VERSION)
    assert blocks.get_data(Tag.LAYER_ID) is None
    assert len([1 for key in blocks if key == Tag.LAYER_VERSION]) == 1


def test_tagged_blocks_v2() -> None:
    filepath = os.path.join(TEST_ROOT, "tagged_blocks", "tagged_blocks_v2.dat")
    with open(filepath, "rb") as f:
        fixture = f.read()
    check_read_write(TaggedBlocks, fixture, version=2, padding=4)


@pytest.mark.parametrize(
    "key, data, version, padding",
    [
        (Tag.LAYER_VERSION, IntegerElement(1), 1, 1),
        (Tag.LAYER_VERSION, IntegerElement(1), 2, 1),
        (Tag.LAYER_VERSION, IntegerElement(1), 1, 4),
        (Tag.LAYER_VERSION, IntegerElement(1), 2, 4),
        (Tag.VECTOR_ORIGINATION_UNKNOWN, IntegerElement(2), 2, 1),
    ],
)
def test_tagged_block(
    key: Tag, data: IntegerElement, version: int, padding: int
) -> None:
    check_write_read(TaggedBlock(key=key, data=data), version=version, padding=padding)  # type: ignore[arg-type]


def test_annotations() -> None:
    check_write_read(Annotations([Annotation(data=b"\x05"), Annotation(data=b"\x03")]))  # type: ignore[list-item]


@pytest.mark.parametrize(
    "fixture",
    [
        list(range(0)),
        list(range(1)),
        list(range(2)),
    ],
)
def test_channel_blending_restrictions_setting(fixture: List[int]) -> None:
    check_write_read(ChannelBlendingRestrictionsSetting(fixture))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kls, filename",
    [
        (DescriptorBlock, "cinf.dat"),
        (DescriptorBlock, "extn_1.dat"),
        (DescriptorBlock, "PxSc_1.dat"),
        (DescriptorBlock, "frgb_1.dat"),
        (PixelSourceData2, "pixel_source_data2.dat"),
        (MetadataSettings, "shmd_1.dat"),
        (MetadataSettings, "shmd_2.dat"),
    ],
)
def test_tagged_block_rw(kls: Type[Any], filename: str) -> None:
    filepath = os.path.join(TEST_ROOT, "tagged_blocks", filename)
    with open(filepath, "rb") as f:
        fixture = f.read()
    check_read_write(kls, fixture)


@pytest.mark.xfail(reason="Not implemented yet")
@pytest.mark.parametrize(
    "kls, filename",
    [(DescriptorBlock2, "CAI.dat")],
)
def test_tagged_block_rw_failure(kls: Type[Any], filename: str) -> None:
    filepath = os.path.join(TEST_ROOT, "tagged_blocks", filename)
    with open(filepath, "rb") as f:
        fixture = f.read()
    check_read_write(kls, fixture)


def test_reference_point() -> None:
    check_write_read(ReferencePoint([3, 5]))  # type: ignore[list-item]


def test_section_divider_setting_converts_a_raw_blend_mode() -> None:
    """A valid 4-byte code is normalised, so ``write()`` can reach ``.value``."""
    setting = SectionDividerSetting(
        SectionDivider.OPEN_FOLDER,  # type: ignore[arg-type]
        signature=b"8BIM",
        blend_mode=b"norm",  # type: ignore[arg-type]
    )
    assert setting.blend_mode is BlendMode.NORMAL
    check_write_read(setting)


def test_section_divider_setting_keeps_an_absent_blend_mode() -> None:
    assert SectionDividerSetting(SectionDivider.OTHER).blend_mode is None  # type: ignore[arg-type]


@pytest.mark.parametrize("blend_mode", [b"zzzz", b"norm\x00", 0, "norm"])
def test_section_divider_setting_rejects_a_bad_blend_mode(blend_mode: Any) -> None:
    """``write()`` used to raise ``AttributeError`` -- or, for ``0``, say nothing.

    ``0`` is falsy, so ``write()``'s ``if self.blend_mode:`` dropped the blend
    mode and the signature with it, leaving a file that reads back short.
    """
    with pytest.raises(ValueError):
        SectionDividerSetting(
            SectionDivider.OPEN_FOLDER,  # type: ignore[arg-type]
            signature=b"8BIM",
            blend_mode=blend_mode,
        )
