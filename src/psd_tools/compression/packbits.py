def decode(data):
    """
    Decodes a PackBit encoded data.
    """
    data = bytearray(data)  # <- python 2/3 compatibility fix
    result = bytearray()
    pos = 0
    while pos < len(data):
        header_byte = data[pos]
        if header_byte > 127:
            header_byte -= 256
        pos += 1

        if 0 <= header_byte <= 127:
            result.extend(data[pos:pos + header_byte + 1])
            pos += header_byte + 1
        elif header_byte == -128:
            pass
        else:
            result.extend([data[pos]] * (1 - header_byte))
            pos += 1

    return bytes(result)


def encode(data):
    """
    Encodes data using PackBits encoding.
    """
    if len(data) == 0:
        return data

    if len(data) == 1:
        return b'\x00' + data

    data = bytearray(data)

    result = bytearray()
    buf = bytearray()
    pos = 0
    repeat_count = 0
    MAX_LENGTH = 127

    # we can safely start with RAW as empty RAW sequences
    # are handled by finish_raw(buf, result)
    state = 'RAW'

    while pos < len(data) - 1:
        current_byte = data[pos]

        if data[pos] == data[pos + 1]:
            if state == 'RAW':
                # end of RAW data
                finish_raw(buf, result)
                state = 'RLE'
                repeat_count = 1
            elif state == 'RLE':
                if repeat_count == MAX_LENGTH:
                    # restart the encoding
                    finish_rle(result, repeat_count, data, pos)
                    repeat_count = 0
                # move to next byte
                repeat_count += 1

        else:
            if state == 'RLE':
                repeat_count += 1
                finish_rle(result, repeat_count, data, pos)
                state = 'RAW'
                repeat_count = 0
            elif state == 'RAW':
                if len(buf) == MAX_LENGTH:
                    # restart the encoding
                    finish_raw(buf, result)

                buf.append(current_byte)

        pos += 1

    if state == 'RAW':
        buf.append(data[pos])
        finish_raw(buf, result)
    else:
        repeat_count += 1
        finish_rle(result, repeat_count, data, pos)

    return bytes(result)


def finish_raw(buf, result):
    if len(buf) == 0:
        return
    result.append(len(buf) - 1)
    result.extend(buf)
    buf[:] = bytearray()


def finish_rle(result, repeat_count, data, pos):
    result.append(256 - (repeat_count - 1))
    result.append(data[pos])
