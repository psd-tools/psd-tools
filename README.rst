psd-tools
=========

``psd-tools`` is a package for reading Adobe Photoshop PSD files
(as described in specification_) to Python data structures.

.. _specification: https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/PhotoshopFileFormats.htm

.. image:: https://img.shields.io/pypi/v/psd-tools.svg
   :target: https://pypi.python.org/pypi/psd-tools
   :alt: PyPI Version

.. image:: https://img.shields.io/travis/psd-tools/psd-tools/master.svg
   :alt: Build Status
   :target: https://travis-ci.org/psd-tools/psd-tools

Installation
------------

::

    pip install psd-tools

Pillow_ should be installed if you want work with PSD image and layer data:
export images to PNG, process them. PIL_ library should also work.

::

   pip install Pillow

.. note::

    In order to extract images from 32bit PSD files PIL/Pillow must be built
    with LITTLECMS or LITTLECMS2 support.

psd-tools also has a rudimentary support for Pymaging_.
`Pymaging installation instructions`_ are available in pymaging docs.
If you want to use Pymaging instead of Pillow you'll also need packbits_
library::

      pip install packbits

.. _PIL: http://www.pythonware.com/products/pil/
.. _Pillow: https://github.com/python-imaging/Pillow
.. _packbits: http://pypi.python.org/pypi/packbits/
.. _Pymaging: https://github.com/ojii/pymaging
.. _Pymaging installation instructions: http://pymaging.readthedocs.org/en/latest/usr/installation.html

Usage
-----

Load an image::

    >>> from psd_tools import PSDImage
    >>> psd = PSDImage.load('my_image.psd')

Read image header::

    >>> psd.header
    PsdHeader(number_of_channels=3, height=200, width=100, depth=8, color_mode=RGB)

Access its layers::

    >>> psd.layers
    [<psd_tools.Group: 'Group 2', layer_count=1>,
     <psd_tools.Group: 'Group 1', layer_count=1>,
     <psd_tools.Layer: 'Background', size=100x200, x=0, y=0>]

Work with a layer group::

    >>> group2 = psd.layers[0]
    >>> group2.name
    Group 2

    >>> group2.visible
    True

    >>> group2.closed
    False

    >>> group2.opacity
    255

    >>> from psd_tools.constants import BlendMode
    >>> group2.blend_mode == BlendMode.NORMAL
    True

    >>> group2.layers
    [<psd_tools.Layer: 'Shape 2', size=43x62, x=40, y=72)>]

Work with a layer::

    >>> layer = group2.layers[0]
    >>> layer.name
    Shape 2

    >>> layer.bbox
    BBox(x1=40, y1=72, x2=83, y2=134)

    >>> layer.bbox.width, layer.bbox.height
    (43, 62)

    >>> layer.visible, layer.opacity, layer.blend_mode
    (True, 255, u'norm')

    >>> layer.text_data.text
    'Text inside a text box'

    >>> layer.as_PIL()
    <PIL.Image.Image image mode=RGBA size=43x62 at ...>


Export a single layer::

    >>> layer_image = layer.as_PIL()
    >>> layer_image.save('layer.png')

Export the merged image::

    >>> merged_image = psd.as_PIL()
    >>> merged_image.save('my_image.png')

The same using Pymaging_::

    >>> merged_image = psd.as_pymaging()
    >>> merged_image.save_to_path('my_image.png')
    >>> layer_image = layer.as_pymaging()
    >>> layer_image.save_to_path('layer.png')

Export layer group (experimental)::

    >>> group_image = group2.as_PIL()
    >>> group_image.save('group.png')


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

``psd-tools`` tries not to throw away information from the original
PSD file; even if the library can't parse some info, this info
will be likely available somewhere as raw bytes (open a bug if this is
not the case). This should make it possible to modify and write PSD
files (currently not implemented; contributions are welcome).

Features
--------

Supported:

* reading of RGB, RGBA, CMYK, CMYKA and Grayscale images;
* 8bit, 16bit and 32bit channels;
* all PSD compression methods are supported (not only the most
  common RAW and RLE);
* image ICC profile is taken into account;
* many image resource types and tagged block types are decoded;
* layer effects information is decoded;
* Descriptor structures are decoded;
* there is an optional Cython extension to make the parsing fast;
* very basic & experimental layer merging.

Not implemented:

* reading of Duotone, LAB, etc. images;
* many image resource types and tagged blocks are not decoded
  (they are attached to the result as raw bytes);
* some of the raw Descriptor values (like EngineData) are not decoded;
* this library can't reliably blend layers together: it is possible to export
  a single layer and to export a final image, but rendering of
  e.g. layer group may produce incorrect results;
* the writing of PSD images is not implemented;
* Pymaging_ support is limited: it only supports 8bit RGB/RGBA
  images, ICC profiles are not applied, layer merging doesn't work, etc.

If you need some of unimplemented features then please fire an issue
or implement it yourself (pull requests are welcome in this case).


Contributing
------------

Development happens at github: `source code <https://github.com/psd-tools/psd-tools>`__,
`bug tracker <https://github.com/psd-tools/psd-tools/issues>`__.
Feel free to submit ideas, bugs or pull requests.

In case of bugs it would be helpful to provide a small PSD file
demonstrating the issue; this file may be added to a test suite.

.. note::

    Unfortunately I don't have a license for Adobe Photoshop and use GIMP for
    testing; PNG screenshots may be necessary in cases where GIMP fails.

In order to run tests, make sure PIL/Pillow is built with LittleCMS
or LittleCMS2 support, install `tox <http://tox.testrun.org>`_ and type

::

    tox

from the source checkout.

The license is MIT.

Acknowledgments
---------------

A full list of contributors can be found here:
https://github.com/psd-tools/psd-tools/blob/master/AUTHORS.txt

Thanks to all guys who write PSD parsers: I learned a lot about PSD
file structure from the source code of psdparse_, GIMP_, libpsd_
and `psdparse C library`_; special thanks to `Paint.NET PSD Plugin`_ authors
for deciphering the "32bit layer + zip-with-prediction compression" case.

Sponsors:

* Leonid Gluzman;
* https://marvelapp.com/.

.. _libpsd: http://sourceforge.net/projects/libpsd/
.. _psdparse C library: http://telegraphics.com.au/svn/psdparse/trunk/
.. _Paint.NET PSD Plugin: http://psdplugin.codeplex.com/
