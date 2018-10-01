"""
Cython extension with utilities for "zip-with-prediction"
decompression method.
"""
cimport cpython.array

def _delta_decode(arr, int mod, int w, int h):
    if mod == 256:
        _delta_decode_bytes(arr, w, h)
        return arr
    elif mod == 256*256:
        _delta_decode_words(arr, w, h)
        arr.byteswap()
        return arr
    else:
        raise NotImplementedError


cdef _delta_decode_bytes(unsigned char[:] arr, int w, int h):
    cdef int x, y, pos, offset
    for y in range(h):
        offset = y*w
        for x in range(w-1):
            pos = offset + x
            arr[pos+1] += arr[pos]

cdef _delta_decode_words(unsigned short[:] arr, int w, int h):
    cdef int x, y, pos, offset
    for y in range(h):
        offset = y*w
        for x in range(w-1):
            pos = offset + x
            arr[pos+1] += arr[pos]


def _restore_byte_order(bytes_array, int w, int h):
    cdef bytes_copy = bytes_array[:]
    cdef unsigned char [:] src = bytes_array, dst = bytes_copy
    cdef int i = 0
    cdef int b, x, y, row_start

    for y in range(h):
        row_start = y*w*4
        for x in range(w):
            for b in range(4):
                dst[i+b] = src[row_start + w*b + x]
            i += 4

    return bytes_copy.tostring()