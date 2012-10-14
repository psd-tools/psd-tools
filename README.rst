psd-tools
=========

``psd-tools`` is a package for reading Adobe Photoshop PSD files
(as described in specification_) to Python data structures.

.. _specification: https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/PhotoshopFileFormats.htm

Why yet another PSD reader?
---------------------------

There are existing PSD readers for Python:

* `psdparse <https://github.com/jerem/psdparse>`_;
* `pypsd <https://code.google.com/p/pypsd>`_;
* there is a PSD reader in PIL library.

PSD reader in PIL is incomplete, and contributing to PIL is somehow
complicated because of the slow release process.

I also considered contributing to pypsd or psdparse, but they are
GPL and I was not totally satisfied with the interface and the code
(they are really fine, it's me having specific style requirements).

So I finally decided to roll out yet another implementation
that should be MIT-licensed, systematically based on the specification_
and implemented as a set of functions; it should also support both
Python 2.x and Python 3.x.

Design overview
---------------

The process of handling a PSD file is splitted into 3 stages:

1) "PSD reading": the file is read and parsed to low-level data
   structures that closely match the specification. No PIL images
   are constructed; image resources blocks and additional layer
   information are extracted but not parsed (they remain just keys
   with a binary data). The goal is to extract all necessary
   information from a PSD file.

2) "Detailed parsing": image resource blocks and additional layer
   information blocks are parsed to a more detailed data structures
   (that are still based on a specification). There are a lot of PSD
   data types and the library currently doesn't handle them all, but
   it should be easy to add the parsing code for the missing PSD data
   structures if needed.

3) "User-facing API": PIL images of the PSD layers are created and
   combined to a user-friendly data structure.

.. note::

    Currently only (1) is partially implemented.

Contributing
------------

Development happens at github and bitbucket:

* https://github.com/kmike/psd-tools
* https://bitbucket.org/kmike/psd-tools

The main issue tracker is at github: https://github.com/kmike/psd-tools/issues

Feel free to submit ideas, bugs, pull requests (git or hg) or regular patches.

The license is MIT.