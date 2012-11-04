# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import zlib
import array
from psd_tools.utils import be_array_from_bytes, read_be_array

def decompress_packbits(fp, byte_counts, bytes_per_pixel):
    data_size = sum(byte_counts) * bytes_per_pixel
    return fp.read(data_size)

def decompress_zip(fp, data_length):
    compressed_data = fp.read(data_length)
    return zlib.decompress(compressed_data)

def decompress_zip_with_prediction(fp, w, h, bytes_per_pixel, data_length):
    decompressed = decompress_zip(fp, data_length)

    if bytes_per_pixel == 1:
        arr = _delta_decode("B", 2**8, decompressed, w, h)

    elif bytes_per_pixel == 2:
        arr = _delta_decode("H", 2**16, decompressed, w, h)

    elif bytes_per_pixel == 4:

        # 32bit channels are also encoded using delta encoding,
        # but it make no sense to apply delta compression to bytes.
        # It is possible to apply delta compression to 2-byte or 4-byte
        # words, but it seems it is not the best way either.
        # In PSD, each 4-byte item is split into 4 bytes and these
        # bytes are packed together: "123412341234" becomes "111222333444";
        # delta compression is applied to the packed data.
        #
        # So we have to (a) decompress data from the delta compression
        # and (b) recombine data back to 4-byte values.

        bytes_array = _delta_decode("B", 2**8, decompressed, w*4, h)

        # restore 4-byte items.
        # XXX: this is very slow written in Python.
        arr = array.array(str("B"))
        for y in range(h):
            row_start = y*w*4
            offsets = row_start, row_start+w, row_start+w*2, row_start+w*3
            for x in range(w):
                for bt in range(4):
                    arr.append(bytes_array[offsets[bt] + x])

        arr = array.array(str("f"), arr.tostring())
    else:
        return None

    return arr.tostring()

def _delta_decode(fmt, mod, data, w, h):
    arr = be_array_from_bytes(fmt, data)
    for y in range(h):
        offset = y*w
        for x in range(w-1):
            pos = offset + x
            next_value = (arr[pos+1] + arr[pos]) % mod
            arr[pos+1] = next_value
    arr.byteswap()
    return arr

