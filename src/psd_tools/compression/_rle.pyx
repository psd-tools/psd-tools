from libc.stdlib cimport malloc, free
from libc.string cimport memcpy, memset
from cpython.version cimport PY_MAJOR_VERSION


def decode(const unsigned char[:] data, Py_ssize_t size):
    cdef unsigned char* result = <unsigned char*> malloc(size * sizeof(char))
    cdef int src = 0
    cdef int dst = 0

    if not result:
        raise MemoryError()

    try:
        while src < data.shape[0]:
            header = data[src]
            if header > 127:
                header -= 256
            src += 1

            if 0 <= header <= 127:
                length = header + 1
                if src + length <= data.shape[0] and dst + length <= size:
                    memcpy(&result[dst], &data[src], length)
                    src += length
                    dst += length
                else:
                    raise ValueError('Invalid RLE compression')
            elif header == -128:
                pass
            else:
                length = 1 - header
                if src + 1 <= data.shape[0] and dst + length <= size:
                    memset(&result[dst], data[src], length)
                    src += 1
                    dst += length
                else:
                    raise ValueError('Invalid RLE compression')
        if dst < size:
            raise ValueError('Expected %d bytes but decoded only %d bytes' % (
                size, dst))

        py_result = result[:size]
    finally:
        free(result)

    return py_result


cdef enum State:
    RAW
    RLE


def encode(const unsigned char[:] data):
    length = data.shape[0]
    if length == 0:
        if PY_MAJOR_VERSION < 3:
            return bytes(bytearray(data))
        return bytes(data)
    if length == 1:
        if PY_MAJOR_VERSION < 3:
            return bytes(b'\x00' + bytearray(data))
        return b'\x00' + data

    cdef int pos = 0
    cdef int repeat_count = 0
    cdef int MAX_LENGTH = 127
    result = bytearray()
    buf = bytearray()

    # we can safely start with RAW as empty RAW sequences
    # are handled by finish_raw(buf, result)
    cdef State state = State.RAW

    while pos < length - 1:
        current_byte = data[pos]

        if data[pos] == data[pos+1]:
            if state == State.RAW:
                # end of RAW data
                finish_raw(buf, result)
                state = State.RLE
                repeat_count = 1
            elif state == State.RLE:
                if repeat_count == MAX_LENGTH:
                    # restart the encoding
                    finish_rle(result, repeat_count, data, pos)
                    repeat_count = 0
                # move to next byte
                repeat_count += 1

        else:
            if state == State.RLE:
                repeat_count += 1
                finish_rle(result, repeat_count, data, pos)
                state = State.RAW
                repeat_count = 0
            elif state == State.RAW:
                if len(buf) == MAX_LENGTH:
                    # restart the encoding
                    finish_raw(buf, result)

                buf.append(current_byte)

        pos += 1

    if state == State.RAW:
        buf.append(data[pos])
        finish_raw(buf, result)
    else:
        repeat_count += 1
        finish_rle(result, repeat_count, data, pos)

    return bytes(result)


def finish_raw(buf, result):
    if len(buf) == 0:
        return
    result.append(len(buf)-1)
    result.extend(buf)
    buf[:] = bytearray()


def finish_rle(result, repeat_count, data, pos):
    result.append(256-(repeat_count - 1))
    result.append(data[pos])
