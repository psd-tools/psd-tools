from __future__ import absolute_import, unicode_literals
import pytest
import logging

from psd_tools.psd.effects_layer import (
    CommonStateInfo,
    ShadowInfo,
    InnerGlowInfo,
    OuterGlowInfo,
    BevelInfo,
    SolidFillInfo,
)

from ..utils import check_write_read, check_read_write

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    'kls', [
        CommonStateInfo,
        ShadowInfo,
        InnerGlowInfo,
        OuterGlowInfo,
        BevelInfo,
        SolidFillInfo,
    ]
)
def test_effects_layer_empty_wr(kls):
    check_write_read(kls())


@pytest.mark.parametrize(
    'fixture', [
        (
            b'\x00\x00\x00\x028BIMnorm\x0b\xf40262SC\x00\x00\xff\x01\x00\x00'
            b'\xf0\x89\xa7s\x94\xd1\x00\x00'
        ),
    ]
)
def test_solid_fill_info(fixture):
    check_read_write(SolidFillInfo, fixture)
