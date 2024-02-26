# distutils: language=c++
# cython: wraparound=False, binding=False

from libcpp.string cimport string
from libcpp.algorithm cimport copy_n, fill_n

def decode(const unsigned char[:] data, Py_ssize_t size) -> string:
    """decode(data, size) -> bytes

    Apple PackBits RLE decoder.
    """

    cdef int i = 0
    cdef int j = 0
    cdef int length = data.shape[0]
    cdef unsigned char bit
    cdef string result

    if length == 1:
        if data[0] != 128:
            raise ValueError('Invalid RLE compression')
        return result

    result.resize(size)

    while i < length:
        i, bit = i+1, data[i]
        if bit > 128:
            bit = 256 - bit
            if j+1+bit > size:
                raise ValueError('Invalid RLE compression')
            fill_n(result.begin()+j, 1+bit, <char>data[i])
            j += 1+bit
            i += 1
        elif bit < 128:
            if i+1+bit > length or (j+1+bit > size):
                raise ValueError('Invalid RLE compression')
            copy_n(&data[i], 1+bit, result.begin()+j)
            j += 1+bit
            i += 1+bit

    if size and (j != size):
        raise ValueError('Expected %d bytes but decoded %d bytes' % (size, j))

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
                elif ((j+2 == length) or (MAX_LEN - (j - i) <= 2)) and (data[j] == data[j+1]):
                    break
                elif j+2 < length and (data[j] == data[j+1] == data[j+2]):
                    break
                j += 1
            result.push_back(j - i - 1)
            result.append(<char*>&data[i], j - i)
            i = j
    return result
