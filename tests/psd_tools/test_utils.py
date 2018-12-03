# -*- coding: utf-8 -*-
from __future__ import absolute_import
import pytest
from io import BytesIO

from psd_tools.utils import read_be_array
from psd_tools.user_api.psd_image import PSDImage
from .utils import decode_psd


PRINT_FILES = (
    ('empty-group.psd',),
    ('layer_mask_data.psd',),
    ('placedLayer.psd',),
    ('adjustment-fillers.psd',),
)


def test_read_be_array_from_file_like_objects():
    fp = BytesIO(b"\x00\x01\x00\x05")
    res = read_be_array("H", 2, fp)
    assert list(res) == [1, 5]


@pytest.mark.parametrize(["filename"], PRINT_FILES)
def test_print_tree(filename):
    psd = PSDImage(decode_psd(filename))
    psd.print_tree()
