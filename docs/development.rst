Development
===========

Why yet another PSD reader?
---------------------------

There are existing PSD readers for Python:

* psdparse_;
* pypsd_;
* there is a PSD reader in PIL_ library;
* it is possible to write Python plugins for GIMP_.

PSD reader in PIL is incomplete and contributing to PIL
is complicated because of the slow release process, but the main issue
with PIL for me is that PIL doesn't have an API for layer groups.

GIMP is cool, but it is a huge dependency, its PSD parser
is not perfect and it is not easy to use GIMP Python plugin
from *your* code.

I also considered contributing to pypsd or psdparse, but they are
GPL and I was not totally satisfied with the interface and the code
(they are really fine, that's me having specific style requirements).

So I finally decided to roll out yet another implementation
that should be MIT-licensed, systematically based on the specification_
(it turns out the specs are incomplete and sometimes incorrect though);
parser should be implemented as a set of functions; the package should
have tests and support both Python 2.x and Python 3.x.

.. _specification: https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/PhotoshopFileFormats.htm
.. _Pymaging: https://github.com/ojii/pymaging
.. _PIL: http://www.pythonware.com/products/pil/
.. _GIMP: http://www.gimp.org/
.. _psdparse: https://github.com/jerem/psdparse
.. _pypsd: https://code.google.com/p/pypsd

Design overview
---------------

The process of handling a PSD file is split into 3 stages:

1) "Reading": the file is read and parsed to low-level data
   structures that closely match the specification. No user-accessible
   images are constructed; image resources blocks and additional layer
   information are extracted but not parsed (they remain just keys
   with a binary data). The goal is to extract all information
   from a PSD file.

2) "Decoding": image resource blocks and additional layer
   information blocks are parsed to a more detailed data structures
   (that are still based on a specification). There are a lot of PSD
   data types and the library currently doesn't handle them all, but
   it should be easy to add the parsing code for the missing PSD data
   structures if needed.

After (1) and (2) we have an in-memory data structure that closely
resembles PSD file; it should be fairly complete but very low-level
and not easy to use. So there is a third stage:

3) "User-facing API": PSD image is converted to an user-friendly object
   that supports layer groups, exporting data as ``PIL.Image`` or
   ``pymaging.Image``, etc.

Stage separation also means user-facing API may be opinionated:
if somebody doesn't like it then it should possible to build an
another API based on lower-level decoded PSD file.

``psd-tools2`` tries not to throw away information from the original
PSD file; even if the library can't parse some info, this info
will be likely available somewhere as raw bytes (open a bug if this is
not the case). This should make it possible to modify and write PSD
files (currently not implemented; contributions are welcome).


Testing
-------

In order to run tests, make sure PIL/Pillow is built with LittleCMS
or LittleCMS2 support, install `tox <http://tox.testrun.org>`_ and type

::

    tox

from the source checkout.


Documentation
-------------

Install Sphinx to generate documents::

    pip install sphinx sphinx_rtd_theme

Once installed, use ``Makefile``::

    make -C docs html


Contributing
------------

Development happens at github: `source code <https://github.com/kyamagu/psd-tools>`__,
`bug tracker <https://github.com/kyamagu/psd-tools/issues>`__.
Feel free to submit ideas, bugs or pull requests.

In case of bugs it would be helpful to provide a small PSD file
demonstrating the issue; this file may be added to a test suite.

The license is MIT.


Acknowledgments
---------------

Great thanks to the original `psd-tools` author Mikhail Korobov.
A full list of contributors can be found here:
https://github.com/kyamagu/psd-tools/blob/master/AUTHORS.txt
