# distutils: language=c++
# cython: wraparound=False, binding=False

from libcpp.string cimport string


def decode(const unsigned char[:] data, Py_ssize_t size) -> string:
    """decode(data, size) -> bytes

    Apple PackBits RLE decoder.
    """

    cdef int i = 0
    cdef int length = len(data)
    cdef unsigned char bit
    cdef string result
    cdef Py_ssize_t result_length = 0

    result.reserve(size)

    if length == 1:
        if data[0] != 128:
            raise ValueError('Invalid RLE compression')
        return result

    while i < length:
        i, bit = i+1, data[i]
        if bit > 128:
            bit = 256 - bit
            if result_length+bit+1 > size:
                raise ValueError('Invalid RLE compression')
            result.append(1+bit, <char>data[i])
            result_length += 1+bit
            i+=1
        elif bit < 128:
            if 1+bit > length or (result_length+bit+1 > size):
                raise ValueError('Invalid RLE compression')
            result.append(<char*>&data[i], 1+bit)
            result_length += 1+bit
            i+=bit + 1

    if size and (result_length != size):
        raise ValueError('Expected %d bytes but decoded %d bytes' % (size, result_length))

    return result


def encode(const unsigned char[:] data) -> string:
    """encode(data) -> bytes

    Apple PackBits RLE encoder.
    """

    cdef unsigned char MAX_LEN = 0xFF >> 1
    cdef int length = len(data)
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
                # NOTE: There's no space saved from encoding length 2 repetitions.
                #: So we only swap back once we see more than 2, or when
                #: we need to reset our counter soon anyway. For example:
                #  A  B  C  D  D  E  F  G  G  G  G  G  G  H  I  J  J  K
                #: could be encoded as either of the following:
                # +2  A  B  C -1  D +1  E  F -5  G +1  H  I -1  J +0  K
                # +6  A  B  C  D  D  E  F -5  G +3  H  I  J  J  K
                elif ((j+2 == length) or (MAX_LEN - (j - i) <= 4)) and (data[j] == data[j+1]):
                    break
                elif j+2 < length and (data[j] == data[j+1] == data[j+2]):
                    break
                j += 1
            result.push_back(j - i - 1)
            result.append(<char*>&data[i], j - i)
            i = j
    return result
