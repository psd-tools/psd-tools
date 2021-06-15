ImageHash
===========

A image hashing library written in Python. ImageHash supports:

* average hashing (`aHash`_)
* perception hashing (`pHash`_)
* difference hashing (`dHash`_)
* wavelet hashing (`wHash`_)

|Travis|_ |Coveralls|_

Rationale
---------
Why can we not use md5, sha-1, etc.?

Unfortunately, we cannot use cryptographic hashing algorithms in our implementation. Due to the nature of cryptographic hashing algorithms, very tiny changes in the input file will result in a substantially different hash. In the case of image fingerprinting, we actually want our similar inputs to have similar output hashes as well.

Requirements
-------------
Based on PIL/Pillow Image, numpy and scipy.fftpack (for pHash)
Easy installation through `pypi`_.

Basic usage
------------
::

	>>> from PIL import Image
	>>> import imagehash
	>>> hash = imagehash.average_hash(Image.open('test.png'))
	>>> print(hash)
	d879f8f89b1bbf
	>>> otherhash = imagehash.average_hash(Image.open('other.bmp'))
	>>> print(otherhash)
	ffff3720200ffff
	>>> print(hash == otherhash)
	False
	>>> print(hash - otherhash)
	36

The demo script **find_similar_images** illustrates how to find similar images in a directory.

Source hosted at github: https://github.com/JohannesBuchner/imagehash

.. _aHash: http://www.hackerfactor.com/blog/index.php?/archives/432-Looks-Like-It.html
.. _pHash: http://www.hackerfactor.com/blog/index.php?/archives/432-Looks-Like-It.html
.. _dHash: http://www.hackerfactor.com/blog/index.php?/archives/529-Kind-of-Like-That.html
.. _wHash: https://fullstackml.com/2016/07/02/wavelet-image-hash-in-python/
.. _pypi: https://pypi.python.org/pypi/ImageHash

Changelog
----------

* 4.0: Changed binary to hex implementation, because the previous one was broken for various hash sizes. This change breaks compatibility to previously stored hashes; to convert them from the old encoding, use the "old_hex_to_hash" function.

* 3.5: image data handling speed-up

* 3.2: whash now also handles smaller-than-hash images

* 3.0: dhash had a bug: It computed pixel differences vertically, not horizontally.
       I modified it to follow `dHash`_. The old function is available as dhash_vertical.

* 2.0: added whash

* 1.0: initial ahash, dhash, phash implementations.


.. |Travis| image:: https://travis-ci.org/JohannesBuchner/imagehash.svg?branch=master
.. _Travis: https://travis-ci.org/JohannesBuchner/imagehash

.. |Coveralls| image:: https://coveralls.io/repos/github/JohannesBuchner/imagehash/badge.svg
.. _Coveralls: https://coveralls.io/github/JohannesBuchner/imagehash


