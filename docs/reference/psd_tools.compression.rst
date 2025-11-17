psd\_tools\.compression
========================

.. automodule:: psd_tools.compression

This module provides compression and decompression codecs for PSD channel data.

Compression Functions
---------------------

.. autofunction:: psd_tools.compression.compress

.. autofunction:: psd_tools.compression.decompress

RLE Codec
---------

.. autofunction:: psd_tools.compression.encode_rle

.. autofunction:: psd_tools.compression.decode_rle

The RLE (Run-Length Encoding) codec implements Apple PackBits compression.
A Cython-optimized version (``_rle.pyx``) is used when available, providing
10-100x performance improvement over the pure Python fallback.

Prediction Encoding
-------------------

.. autofunction:: psd_tools.compression.encode_prediction

.. autofunction:: psd_tools.compression.decode_prediction

Prediction encoding applies delta compression before ZIP compression, improving
compression ratios for continuous-tone images. Supports 8, 16, and 32-bit depths.
