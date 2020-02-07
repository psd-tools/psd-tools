from cpython.version cimport PY_MAJOR_VERSION


def decode(const unsigned char[:] data):
    cdef int pos = 0
    length = data.shape[0]
    result = bytearray()
    while pos < length:
        header_byte = data[pos]
        if header_byte > 127:
            header_byte -= 256
        pos += 1

        if 0 <= header_byte <= 127:
            result.extend(data[pos:pos+header_byte+1])
            pos += header_byte+1
        elif header_byte == -128:
            pass
        else:
            result.extend([data[pos]] * (1 - header_byte))
            pos += 1

    return bytes(result)


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
