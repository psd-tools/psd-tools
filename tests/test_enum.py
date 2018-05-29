# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

from psd_tools.constants import Enum


class SampleEnum(Enum):
    FOO = 1
    BAR = 2
    _PRIVATE = 3


def test_is_known():
    assert SampleEnum.FOO == 1
    assert SampleEnum.is_known(1)
    assert SampleEnum.is_known(2)
    assert not SampleEnum.is_known(0)
    assert not SampleEnum.is_known(3)


def test_name_of():
    assert SampleEnum.name_of(1) == 'FOO'
    assert SampleEnum.name_of(2) == 'BAR'
    assert SampleEnum.name_of(3) == '<unknown:3>'
