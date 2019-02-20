"""
Various utility functions for low-level binary processing.
"""
from __future__ import unicode_literals, print_function, division
import logging
import sys
import struct
import array

try:
    unichr = unichr
except NameError:
    unichr = chr

logger = logging.getLogger(__name__)


def pack(fmt, *args):
    fmt = str(">" + fmt)
    return struct.pack(fmt, *args)


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
    assert len(data) == fmt_size, 'read=%d, expected=%d' % (
        len(data), fmt_size
    )
    return struct.unpack(fmt, data)


def write_fmt(fp, fmt, *args):
    """
    Writes data to ``fp`` according to ``fmt``.
    """
    fmt = str(">" + fmt)
    fmt_size = struct.calcsize(fmt)
    written = write_bytes(fp, struct.pack(fmt, *args))
    assert written == fmt_size, 'written=%d, expected=%d' % (
        written, fmt_size
    )
    return written


def write_bytes(fp, data):
    """
    Write bytes to the file object and returns bytes written.

    :return: written byte size
    """
    pos = fp.tell()
    fp.write(data)
    written = fp.tell() - pos
    assert written == len(data), 'written=%d, expected=%d' % (
        written, len(data)
    )
    return written


def read_length_block(fp, fmt='I', padding=1):
    """
    Read a block of data with a length marker at the beginning.

    :param fp: file-like
    :param fmt: format of the length marker
    :return: bytes object
    """
    length = read_fmt(fmt, fp)[0]
    data = fp.read(length)
    assert len(data) == length, (len(data), length)
    read_padding(fp, length, padding)
    return data


def write_length_block(fp, writer, fmt='I', padding=1, **kwargs):
    """
    Writes a block of data with a length marker at the beginning.

    Example::

        with io.BytesIO() as fp:
            write_length_block(fp, lambda f: f.write(b'\x00\x00'))

    :param fp: file-like
    :param writer: function object that takes file-like object as an argument
    :param fmt: format of the length marker
    :param padding: divisor for padding not included in length marker
    :return: written byte size
    """
    length_position = reserve_position(fp, fmt)
    written = writer(fp, **kwargs)
    written += write_position(fp, length_position, written, fmt)
    written += write_padding(fp, written, padding)
    return written


def reserve_position(fp, fmt='I'):
    """
    Reserves the current position for write.

    Use with `write_position`.

    :param fp: file-like object
    :param fmt: format of the reserved position
    :return: the position
    """
    position = fp.tell()
    fp.seek(struct.calcsize(str('>' + fmt)), 1)
    return position


def write_position(fp, position, value, fmt='I'):
    """
    Writes a value to the specified position.

    :param fp: file-like object
    :param position: position of the value marker
    :param value: value to write
    :param fmt: format of the value
    :return: written byte size
    """
    current_position = fp.tell()
    fp.seek(position)
    written = write_bytes(fp, struct.pack(str('>' + fmt), value))
    fp.seek(current_position)
    return written


def read_padding(fp, size, divisor=2):
    """
    Read padding bytes for the given byte size.

    :param fp: file-like object
    :param divisor: divisor of the byte alignment
    :return: read byte size
    """
    remainder = size % divisor
    if remainder:
        return fp.read(divisor - remainder)
    return b''


def write_padding(fp, size, divisor=2):
    """
    Writes padding bytes given the currently written size.

    :param fp: file-like object
    :param divisor: divisor of the byte alignment
    :return: written byte size
    """
    remainder = size % divisor
    if remainder:
        return write_bytes(fp, struct.pack('%dx' % (divisor - remainder)))
    return 0


def is_readable(fp, size=1):
    """
    Check if the file-like object is readable.

    :param fp: file-like object
    :param size: byte size
    :return: bool
    """
    read_size = len(fp.read(size))
    fp.seek(-read_size, 1)
    return read_size == size


def pad(number, divisor):
    if number % divisor:
        number = (number // divisor + 1) * divisor
    return number


def read_pascal_string(fp, encoding='macroman', padding=2):
    """
    Reads pascal string (length + bytes).

    :param fp: file-like object
    :param encoding: string encoding
    :param padding: padding size
    :return: str
    """
    start_pos = fp.tell()
    # read_length_block doesn't work for a byte.
    length = read_fmt('B', fp)[0]
    data = fp.read(length)
    assert len(data) == length, (len(data), length)
    read_padding(fp, fp.tell() - start_pos, padding)
    return data.decode(encoding)


def write_pascal_string(fp, value, encoding='macroman', padding=2):
    data = value.encode(encoding)
    written = write_fmt(fp, 'B', len(data))
    written += write_bytes(fp, data)
    written += write_padding(fp, written, padding)
    return written


def read_unicode_string(fp, padding=1):
    num_chars = read_fmt('I', fp)[0]
    chars = be_array_from_bytes('H', fp.read(num_chars * 2))
    read_padding(fp, struct.calcsize('I') + num_chars * 2, padding)
    return "".join(unichr(num) for num in chars)


def write_unicode_string(fp, value, padding=1):
    arr = array.array(str('H'), [ord(x) for x in value])
    written = write_fmt(fp, 'I', len(arr))
    written += write_bytes(fp, be_array_to_bytes(arr))
    written += write_padding(fp, written, padding)
    return written


def read_be_array(fmt, count, fp):
    """
    Reads an array from a file with big-endian data.
    """
    arr = array.array(str(fmt))
    if hasattr(arr, 'frombytes'):
        arr.frombytes(fp.read(count * arr.itemsize))
    else:
        arr.fromstring(fp.read(count * arr.itemsize))
    return fix_byteorder(arr)


def write_be_array(fp, arr):
    """
    Writes an array to a file with big-endian data.
    """
    return write_bytes(fp, be_array_to_bytes(arr))


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


def be_array_to_bytes(arr):
    """
    Writes an array to bytestring with big-endian data.
    """
    data = fix_byteorder(arr)
    if hasattr(arr, 'tobytes'):
        return data.tobytes()
    else:
        return data.tostring()


def trimmed_repr(data, trim_length=16):
    if isinstance(data, bytes):
        if len(data) > trim_length:
            return repr(
                data[:trim_length] + b' ... =' +
                str(len(data)).encode('ascii')
            )
    return repr(data)


def decode_fixed_point_32bit(data):
    """
    Decodes ``data`` as an unsigned 4-byte fixed-point number.
    """
    lo, hi = unpack("2H", data)
    # XXX: shouldn't denominator be 2**16 ?
    return lo + hi / (2**16 - 1)


def new_registry(attribute=None):
    """
    Returns an empty dict and a @register decorator.
    """
    registry = {}

    def register(key):
        def decorator(func):
            registry[key] = func
            if attribute:
                setattr(func, attribute, key)
            return func
        return decorator

    return registry, register
