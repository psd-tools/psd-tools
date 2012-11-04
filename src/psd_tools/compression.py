# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import array
from psd_tools.utils import be_array_from_bytes

def decode_prediction(data, w, h, bytes_per_pixel):
    if bytes_per_pixel == 1:
        arr = be_array_from_bytes("B", data)
        arr = _delta_decode(arr, 2**8, w, h)

    elif bytes_per_pixel == 2:
        arr = be_array_from_bytes("H", data)
        arr = _delta_decode(arr, 2**16, w, h)

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

        arr = array.array(str("B"), data)
        arr = _delta_decode(arr, 2**8, w*4, h)
        arr = _restore_byte_order(arr, w, h)
        arr = array.array(str("f"), arr)
    else:
        return None

    return arr.tostring()

def _delta_decode(arr, mod, w, h):
    for y in range(h):
        offset = y*w
        for x in range(w-1):
            pos = offset + x
            next_value = (arr[pos+1] + arr[pos]) % mod
            arr[pos+1] = next_value
    arr.byteswap()
    return arr

def _restore_byte_order(bytes_array, w, h):
    arr = bytes_array[:]
    i = 0
    rng4 = range(4)
    for y in range(h):
        row_start = y*w*4
        offsets = row_start, row_start+w, row_start+w*2, row_start+w*3
        for x in range(w):
            for bt in rng4:
                arr[i] = bytes_array[offsets[bt] + x]
                i += 1
    return arr.tostring()

# Replace _delta_decode and _restore_byte_order with faster versions (from
# a compiled extension) if this is possible:
try:
    from ._compression import _delta_decode, _restore_byte_order
except ImportError:
    pass