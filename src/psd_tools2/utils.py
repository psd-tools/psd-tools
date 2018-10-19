from __future__ import unicode_literals, print_function, division
import sys
import struct
import array

try:
    unichr = unichr
except NameError:
    unichr = chr


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
    assert len(data) == fmt_size, (len(data), fmt_size)
    return struct.unpack(fmt, data)


def write_fmt(fp, fmt, *args):
    """
    Writes data to ``fp`` according to ``fmt``.
    """
    fmt = str(">" + fmt)
    fmt_size = struct.calcsize(fmt)
    written = fp.write(struct.pack(fmt, *args))
    assert written == fmt_size, (written, fmt_size)
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
    :return: written byte size
    """
    length_position = reserve_position(fp, fmt)
    written = writer(fp, **kwargs)
    size = written
    written += write_position(fp, length_position, written, fmt)
    written += write_padding(fp, size, padding)
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
    written = fp.write(struct.pack(str('>' + fmt), value))
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
    return 0


def write_padding(fp, size, divisor=2):
    """
    Writes padding bytes given the currently written size.

    :param fp: file-like object
    :param divisor: divisor of the byte alignment
    :return: written byte size
    """
    remainder = size % divisor
    if remainder:
        return fp.write(struct.pack('%dx' % (divisor - remainder)))
    return 0


def is_readable(fp):
    """
    Check if the file-like object is readable.

    :param fp: file-like object
    :return: bool
    """
    if len(fp.read(1)):
        fp.seek(-1, 1)
        return True
    else:
        return False


def pad(number, divisor):
    if number % divisor:
        number = (number // divisor + 1) * divisor
    return number


def pad_data(value, divisor):
    return value + b'\x00' * (len(value) % divisor)


def read_pascal_string(fp, encoding='utf-8', padding=1):
    length = read_fmt("B", fp)[0]
    if length == 0:
        fp.seek(padding-1, 1)
        return ''

    res = fp.read(length)
    # -1 accounts for the length byte
    padded_length = pad(length+1, padding) - 1
    fp.seek(padded_length - length, 1)
    return res.decode(encoding, 'replace')


def write_pascal_string(fp, value, encoding='utf-8', padding=1):
    data = value.encode(encoding)
    written = write_fmt(fp, 'B', len(data))
    written += fp.write(data)
    written += write_padding(fp, written, padding)
    return written


def read_unicode_string(fp):
    num_chars = read_fmt("I", fp)[0]
    data = fp.read(num_chars*2)
    chars = be_array_from_bytes("H", data)
    return "".join(unichr(num) for num in chars)


def write_unicode_string(fp, value):
    arr = array.array(str('H'), value.encode('utf-8'))
    data = be_array_to_bytes(arr)
    return write_fmt(fp, 'I%dH', len(data), *data)


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
    return fp.write(be_array_to_bytes(arr))


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


def trimmed_repr(data, trim_length=30):
    if isinstance(data, bytes):
        if len(data) > trim_length:
            return repr(
                data[:trim_length] + b' ... =' +
                str(len(data)).encode('ascii')
            )
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
