# distutils: language=c++
# cython: wraparound=False, binding=False

from libcpp.string cimport string
from libcpp.algorithm cimport copy_n, fill_n

def decode(const unsigned char[:] data, Py_ssize_t size) -> string:
    """decode(data, size) -> bytes

    Apple PackBits RLE decoder.

    Tolerant implementation: runs that would exceed *size* are clipped at the
    row boundary, runs whose input is truncated copy what is available, and any
    remaining bytes are zero-padded (std::string::resize zero-initialises).
    The function always returns exactly *size* bytes without raising.
    """

    cdef int i = 0
    cdef int j = 0
    cdef int length = data.shape[0]
    cdef int actual, available
    cdef unsigned char bit
    cdef string result

    result.resize(size)  # zero-initialised by std::string::resize

    if length == 1:
        # Single byte: either a no-op (128) or a stray header — return zeros
        return result

    while i < length and j < size:
        i, bit = i+1, data[i]
        if bit > 128:
            bit = 256 - bit
            if i >= length:  # lone repeat header at end of stream — stop
                break
            actual = min(1+bit, size-j)  # clip at remaining output space
            fill_n(result.begin()+j, actual, <char>data[i])
            j += actual
            i += 1
        elif bit < 128:
            if i >= length:  # copy header is the last byte; nothing to copy
                break
            available = min(length-i, 1+bit)
            actual = min(available, size-j)  # clip to input and output
            copy_n(&data[i], actual, result.begin()+j)
            j += actual
            i += available  # advance by declared amount or to end
        # bit == 128: no-op

    return result


def encode(const unsigned char[:] data) -> string:
    """encode(data) -> bytes

    Apple PackBits RLE encoder.
    """
    
    cdef unsigned char MAX_LEN = 0xFF >> 1
    cdef int length = data.shape[0]
    cdef int i = 0
    cdef int j = 0
    cdef string result

    if length == 0:
        return data
    if length == 1:
        result.push_back(0)
        result.push_back(data[0])
        return result

    while i < length:
        if j + 1 < length and data[j] == data[j+1]:
            while j < length:
                if j - i >= MAX_LEN:
                    break
                if j + 1 >= length or data[j] != data[j+1]:
                    break
                j += 1
            result.push_back(- (j - i))
            result.push_back(<char>data[i])
            i = j = j + 1
        else:
            while j < length:
                if j - i >= MAX_LEN:
                    break
                if j+1 < length and (data[j] != data[j+1]):
                    pass
                # NOTE: There's no space saved from encoding length 2 repetitions in this situation.
                #: For example:
                #  A  B  C  D  D  E  F  G  G  G  G  G  G  H  I  J  J  K
                #: could be encoded as either of the following:
                # +2  A  B  C -1  D +1  E  F -5  G +1  H  I -1  J +0  K
                # +6  A  B  C  D  D  E  F -5  G +4  H  I  J  J  K
                elif ((j+2 == length) or (MAX_LEN - (j - i) <= 2)) and not (j+1 == length) and (data[j] == data[j+1]):
                    break
                elif j+2 < length and (data[j] == data[j+1] == data[j+2]):
                    break
                j += 1
            result.push_back(j - i - 1)
            result.append(<char*>&data[i], j - i)
            i = j
    return result
