# -*- coding: utf-8 -*-
"""
A module for decoding "Actions" additional PSD data format.
"""
from __future__ import absolute_import, unicode_literals

import io
import collections

from psd_tools.utils import read_unicode_string, read_fmt

Descriptor = collections.namedtuple('Descriptor', 'name classID item_count items')


def decode_descriptor(data):
    fp = io.BytesIO(data)
    name = read_unicode_string(fp)

    classID_length = read_fmt("I", fp)[0]
    classID = fp.read(classID_length or 4)

    item_count = read_fmt("I", fp)[0]
    items = fp.read() # TODO: detailed parsing

    return Descriptor(name, classID, item_count, items)
