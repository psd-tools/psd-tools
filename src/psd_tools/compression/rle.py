def decode(data: bytes, size: int) -> bytes:
    """decode(data, size) -> bytes

    Apple PackBits RLE decoder.
    """

    i, j = 0, 0
    length = len(data)
    data = bytearray(data)
    result = bytearray()

    if length == 1:
        if data[0] != 128:
            raise ValueError("Invalid RLE compression")
        return result

    while i < length:
        i, bit = i + 1, data[i]
        if bit > 128:
            bit = 256 - bit
            if j + 1 + bit > size:
                raise ValueError("Invalid RLE compression")
            result.extend((data[i : i + 1]) * (1 + bit))
            j += 1 + bit
            i += 1
        elif bit < 128:
            if i + 1 + bit > length or (j + 1 + bit > size):
                raise ValueError("Invalid RLE compression")
            result.extend(data[i : i + 1 + bit])
            j += 1 + bit
            i += 1 + bit

    if size and (len(result) != size):
        raise ValueError("Expected %d bytes but decoded %d bytes" % (size, j))

    return bytes(result)


def encode(data: bytes) -> bytes:
    """encode(data) -> bytes

    Apple PackBits RLE encoder.
    """

    MAX_LEN = 0xFF >> 1
    length = len(data)
    i = 0
    j = 0
    result = bytearray()

    if length == 0:
        return data
    if length == 1:
        result.extend((0, data[0]))
        return result

    while i < length:
        if j + 1 < length and data[j] == data[j + 1]:
            while j < length:
                if j - i >= MAX_LEN:
                    break
                if j + 1 >= length or data[j] != data[j + 1]:
                    break
                j += 1
            result.extend((256 - (j - i), data[i]))
            i = j = j + 1
        else:
            while j < length:
                if j - i >= MAX_LEN:
                    break
                if j + 1 < length and (data[j] != data[j + 1]):
                    pass
                # NOTE: There's no space saved from encoding length 2 repetitions.
                #: For example:
                #  A  B  C  D  D  E  F  G  G  G  G  G  G  H  I  J  J  K
                #: could be encoded as either of the following:
                # +2  A  B  C -1  D +1  E  F -5  G +1  H  I -1  J +0  K
                # +6  A  B  C  D  D  E  F -5  G +3  H  I  J  J  K
                elif ((j + 2 == length) or (MAX_LEN - (j - i) <= 2)) and (
                    data[j] == data[j + 1]
                ):
                    break
                elif j + 2 < length and (data[j] == data[j + 1] == data[j + 2]):
                    break
                j += 1
            result.append(j - i - 1)
            result.extend(data[i:j])
            i = j
    return bytes(result)
