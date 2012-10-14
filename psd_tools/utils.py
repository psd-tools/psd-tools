# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, unicode_literals

import sys
import struct
import array

def read_fmt(fmt, fp):
    """
    Reads data from ``fp`` according to ``fmt``.
    """
    fmt = str(">" + fmt)
    fmt_size = struct.calcsize(fmt)
    data = fp.read(fmt_size)
    assert len(data) == fmt_size, (len(data), fmt_size)
    return struct.unpack(fmt, data)

def pad(number, divisor):
    if number % divisor:
        number = (number // divisor + 1) * divisor
    return number

def read_pascal_string(fp, encoding, padding=1):
    length = pad(read_fmt("B", fp)[0], padding)
    return fp.read(length).decode(encoding, errors='replace')

def read_be_array(fp, fmt, count):
    """
    Reads an array from a file with big-endian data.
    """
    arr = array.array(str(fmt))
    arr.fromfile(fp, count)
    if sys.byteorder == 'little':
        arr.byteswap()
    return arr

def trimmed_repr(data, trim_length):
    if data is not None and len(data) > trim_length:
        return repr(data[:trim_length] + b' ...')
    else:
        return repr(data)

