from __future__ import absolute_import, unicode_literals
import pytest
import logging

from psd_tools2.psd.effects_layer import (
    CommonStateInfo, ShadowInfo, InnerGlowInfo, OuterGlowInfo, BevelInfo,
    SolidFillInfo,
)

from ..utils import check_write_read


logger = logging.getLogger(__name__)


@pytest.mark.parametrize('kls', [
    CommonStateInfo, ShadowInfo, InnerGlowInfo, OuterGlowInfo, BevelInfo,
    SolidFillInfo,
])
def test_effects_layer_empty_wr(kls):
    check_write_read(kls())
