# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, unicode_literals, print_function

import sys
import struct
import array

try:
    unichr = unichr
except NameError:
    unichr = chr

def unpack(fmt, data):
    fmt = str(">" + fmt)
    return struct.unpack(fmt, data)

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
    length = read_fmt("B", fp)[0]
    if length == 0:
        fp.seek(padding-1, 1)
        return ''

    res = fp.read(length)

    padded_length = pad(length+1, padding) - 1 # -1 accounts for the length byte
    fp.seek(padded_length - length, 1)
    return res.decode(encoding, 'replace')

def read_unicode_string(fp):
    num_chars = read_fmt("I", fp)[0]
    data = fp.read(num_chars*2)
    chars = be_array_from_bytes("H", data)
    return "".join(unichr(num) for num in chars)

def read_be_array(fmt, count, fp):
    """
    Reads an array from a file with big-endian data.
    """
    arr = array.array(str(fmt))
    arr.fromstring(fp.read(count * arr.itemsize))
    return fix_byteorder(arr)

def fix_byteorder(arr):
    """
    Fixes the byte order of the array (assuming it was read
    from a Big Endian data).
    """
    if sys.byteorder == 'little':
        arr.byteswap()
    return arr

def be_array_from_bytes(fmt, data):
    """
    Reads an array from bytestring with big-endian data.
    """
    arr = array.array(str(fmt), data)
    return fix_byteorder(arr)


def trimmed_repr(data, trim_length=30):
    if isinstance(data, bytes):
        if len(data) > trim_length:
            return repr(data[:trim_length] + b' ... =' + str(len(data)).encode('ascii'))
    return repr(data)

def synchronize(fp, limit=8):
    # This is a hack for the cases where I gave up understanding PSD format.
    signature_list = (b'8BIM', b'8B64')

    start = fp.tell()
    data = fp.read(limit)

    for signature in signature_list:
        pos = data.find(signature)
        if pos != -1:
            fp.seek(start+pos)
            return True

    fp.seek(start)
    return False

def decode_fixed_point_32bit(data):
    """
    Decodes ``data`` as an unsigned 4-byte fixed-point number.
    """
    lo, hi = unpack("2H", data)
    # XXX: shouldn't denominator be 2**16 ?
    return lo + hi / (2**16 - 1)
