# -*- coding: utf-8 -*-
from __future__ import absolute_import
from io import BytesIO

from psd_tools.utils import read_be_array
from tests.utils import decode_psd
from psd_tools.user_api.psd_image import PSDImage

def test_read_be_array_from_file_like_objects():
    fp = BytesIO(b"\x00\x01\x00\x05")
    res = read_be_array("H", 2, fp)
    assert list(res) == [1, 5]


def test_print_tree():
    psd = PSDImage(decode_psd('empty-group.psd'))
    psd.print_tree()
