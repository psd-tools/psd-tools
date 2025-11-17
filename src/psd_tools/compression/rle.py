"""
Pure Python RLE (Run-Length Encoding) codec implementation.

This module provides pure Python implementations of Apple PackBits RLE encoding
and decoding. PackBits is a simple byte-oriented run-length compression scheme
used in PSD files for channel data compression.

**Note**: This is the fallback implementation. A faster Cython version is available
in ``_rle.pyx`` and will be used automatically if compiled. The Cython version can
be 10-100x faster, especially for large images.

Algorithm overview:

The PackBits algorithm uses a single header byte to indicate:
- Values 0-127: Copy the next (n+1) literal bytes
- Values 129-255: Repeat the next byte (257-n) times
- Value 128: No-op (typically not used)

Encoding example::
    Input:  [A, A, A, B, C, C, C, C]
    Output: [130, A, 1, B, 131, C]
            (repeat A 3x, copy B 1x, repeat C 4x)

The encoder analyzes the input stream to find runs of identical bytes (for RLE
compression) and sequences of varying bytes (stored literally). It balances
between these modes to achieve optimal compression.

Functions:

- :py:func:`decode`: Decompress RLE-encoded data to raw bytes
- :py:func:`encode`: Compress raw bytes using RLE encoding

Example usage::

    from psd_tools.compression.rle import encode, decode

    # Encode raw data
    raw_data = b'\x00' * 100 + b'\xff' * 50
    compressed = encode(raw_data)

    # Decode back to raw
    decompressed = decode(compressed, len(raw_data))
    assert decompressed == raw_data

Performance notes:

- RLE works best for images with large uniform areas (solid colors, gradients)
- Worst case: file size can increase by ~0.4% for random data
- Best case: massive compression for solid colors (100:1 or better)

The pure Python implementation is used as a reference and fallback. For
production use with large files, ensure the Cython version is compiled by
installing with build tools available.
"""


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
                elif (
                    ((j + 2 == length) or (MAX_LEN - (j - i) <= 2))
                    and not (j + 1 == length)
                    and (data[j] == data[j + 1])
                ):
                    break
                elif j + 2 < length and (data[j] == data[j + 1] == data[j + 2]):
                    break
                j += 1
            result.append(j - i - 1)
            result.extend(data[i:j])
            i = j
    return bytes(result)
