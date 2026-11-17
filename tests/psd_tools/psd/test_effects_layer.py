import io
import logging
from typing import Any

import pytest

from psd_tools.constants import ColorSpaceID
from psd_tools.psd.color import Color
from psd_tools.psd.effects_layer import (
    BevelInfo,
    CommonStateInfo,
    InnerGlowInfo,
    OuterGlowInfo,
    ShadowInfo,
    SolidFillInfo,
)

from ..utils import check_read_write, check_write_read

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "kls",
    [
        CommonStateInfo,
        ShadowInfo,
        InnerGlowInfo,
        OuterGlowInfo,
        BevelInfo,
        SolidFillInfo,
    ],
)
def test_effects_layer_empty_wr(kls: type[Any]) -> None:
    check_write_read(kls())


@pytest.mark.parametrize(
    "fixture",
    [
        (
            b"\x00\x00\x00\x028BIMnorm\x0b\xf40262SC\x00\x00\xff\x01\x00\x00"
            b"\xf0\x89\xa7s\x94\xd1\x00\x00"
        ),
    ],
)
def test_solid_fill_info(fixture: bytes) -> None:
    check_read_write(SolidFillInfo, fixture)


def test_bevel_info_v2_writes_real_colors() -> None:
    bevel = BevelInfo(
        version=2,
        highlight_color=Color(ColorSpaceID.RGB, [1, 2, 3, 0]),
        shadow_color=Color(ColorSpaceID.RGB, [4, 5, 6, 0]),
        real_highlight_color=Color(ColorSpaceID.RGB, [7, 8, 9, 0]),
        real_shadow_color=Color(ColorSpaceID.RGB, [10, 11, 12, 0]),
    )
    check_write_read(bevel)


def test_bevel_info_v2_without_real_colors_raises() -> None:
    with pytest.raises(ValueError):
        BevelInfo(version=2).write(io.BytesIO())


def test_bevel_info_v2_without_real_colors_writes_nothing() -> None:
    f = io.BytesIO()
    with pytest.raises(ValueError):
        BevelInfo(version=2).write(f)
    assert f.getvalue() == b""
