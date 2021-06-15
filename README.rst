psd-tools3
==========

.. image:: https://badges.production.guardrails.io/sfneal/psd-tools3.svg
   :alt: GuardRails badge
   :target: https://www.guardrails.io

``psd-tools3`` is a package for reading Adobe Photoshop PSD files
as described in specification_ to Python data structures.

This is a fork of psd-tools_ that adds a couple of enhancements to the
original version.

.. _specification: https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/PhotoshopFileFormats.htm

.. image:: https://img.shields.io/pypi/v/psd-tools3.svg
   :target: https://pypi.python.org/pypi/psd-tools3
   :alt: PyPI Version

.. image:: https://img.shields.io/travis/kyamagu/psd-tools3/master.svg
   :alt: Build Status
   :target: https://travis-ci.org/kyamagu/psd-tools3

.. image:: https://readthedocs.org/projects/psd-tools3/badge/
   :alt: Document Status
   :target: http://psd-tools3.readthedocs.io/en/latest/

.. _psd-tools: https://github.com/psd-tools/psd-tools


Installation
------------

.. code-block:: bash

    pip install psd-tools3

Pillow_ should be installed if you want work with PSD image and layer data:
export images to PNG, process them. PIL_ library should also work.

.. code-block:: bash

   pip install Pillow

.. note::

    In order to extract images from 32bit PSD files PIL/Pillow must be built
    with LITTLECMS or LITTLECMS2 support.

psd-tools3 also has a rudimentary support for Pymaging_.
`Pymaging installation instructions`_ are available in pymaging docs.

.. _PIL: http://www.pythonware.com/products/pil/
.. _Pillow: https://github.com/python-imaging/Pillow
.. _packbits: http://pypi.python.org/pypi/packbits/
.. _Pymaging: https://github.com/ojii/pymaging
.. _Pymaging installation instructions: http://pymaging.readthedocs.org/en/latest/usr/installation.html
.. _exifread: https://github.com/ianare/exif-py


Command line
------------

The current tool supports PNG/JPEG export:

.. code-block:: bash

    psd-tools convert <psd_filename> <out_filename> [options]
    psd-tools export_layer <psd_filename> <layer_index> <out_filename> [options]
    psd-tools debug <filename> [options]
    psd-tools -h | --help
    psd-tools --version


API Usage
---------

Load an image::

    >>> from psd_tools import PSDImage
    >>> psd = PSDImage.load('my_image.psd')

Print the layer structure::

    >>> psd.print_tree()

Read image header::

    >>> psd.header
    PsdHeader(number_of_channels=3, height=200, width=100, depth=8, color_mode=RGB)

Access its layers::

    >>> psd.layers
    [<group: 'Group 2', layer_count=1, mask=None, visible=1>,
     <group: 'Group 1', layer_count=1, mask=None, visible=1>,
     <pixel: 'Background', size=100x200, x=0, y=0, mask=None, visible=1>]

    >>> list(psd.descendants())
    [<group: 'Group 2', layer_count=1, mask=None, visible=1>,
     <shape: 'Shape 2', size=43x62, x=40, y=72, mask=None, visible=1)>,
     <group: 'Group 1', layer_count=1, mask=None, visible=1>,
     ...
     ]


Work with a layer group::

    >>> group2 = psd.layers[0]
    >>> group2.name
    Group 2

    >>> group2.visible
    True

    >>> group2.opacity
    255

    >>> group2.blend_mode == 'normal'
    True

    >>> group2.layers
    [<shape: 'Shape 2', size=43x62, x=40, y=72, mask=None, visible=1)>]

Work with a layer::

    >>> layer = group2.layers[0]
    >>> layer.name
    Shape 2

    >>> layer.kind
    type

    >>> layer.bbox
    BBox(x1=40, y1=72, x2=83, y2=134)

    >>> layer.bbox.width, layer.bbox.height
    (43, 62)

    >>> layer.visible, layer.opacity, layer.blend_mode
    (True, 255, 'normal')

    >>> layer.text
    'Text inside a text box'

    >>> layer.as_PIL()
    <PIL.Image.Image image mode=RGBA size=43x62 at ...>

    >>> mask = layer.mask
    >>> mask.bbox
    BBox(x1=40, y1=72, x2=83, y2=134)

    >>> mask.as_PIL()
    <PIL.Image.Image image mode=L size=43x62 at ...>

    >>> layer.clip_layers
    [<shape: 'Clipped', size=43x62, x=40, y=72, mask=None, visible=1)>, ...]

    >>> layer.effects
    [<GradientOverlay>]

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

Export a thumbnail in PIL Image::

    >>> thumbnail_image = psd.thumbnail()

Export layer group (experimental)::

    >>> group_image = group2.as_PIL()
    >>> group_image.save('group.png')


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

``psd-tools3`` tries not to throw away information from the original
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
* very basic & experimental layer merging;
* support both PSD and PSB file formats;
* EngineData structure is decoded;
* EXIF data is taken into account.

Not implemented:

* reading of Duotone, LAB, etc. images;
* some image resource types and tagged blocks are not decoded
  (they are attached to the result as raw bytes);
* some of the raw Descriptor values are not decoded;
* this library can't reliably blend layers together: it is possible to export
  a single layer and to export a final image, but rendering of
  e.g. layer group may produce incorrect results;
* the writing of PSD images is not implemented;
* Pymaging_ support is limited: it only supports 8bit RGB/RGBA
  images, ICC profiles are not applied, layer merging doesn't work, etc.

If you need some of unimplemented features then please file an issue
or implement it yourself (pull requests are welcome in this case).


Contributing
------------

Development happens at github: `source code <https://github.com/kyamagu/psd-tools3>`__,
`bug tracker <https://github.com/kyamagu/psd-tools3/issues>`__.
Feel free to submit ideas, bugs or pull requests.

In case of bugs it would be helpful to provide a small PSD file
demonstrating the issue; this file may be added to a test suite.

In order to run tests, make sure PIL/Pillow is built with LittleCMS
or LittleCMS2 support, install `tox <http://tox.testrun.org>`_ and type:

.. code-block:: bash

    tox

Install Sphinx to generate documents:

.. code-block:: bash

    pip install sphinx sphinx_rtd_theme

Once installed, use ``Makefile``:

.. code-block:: bash

    make -C docs html

from the source checkout.

The license is MIT.

Acknowledgments
---------------

Great thanks to the original `psd-tools` author Mikhail Korobov.
A full list of contributors can be found here:
https://github.com/kyamagu/psd-tools3/blob/master/AUTHORS.txt
