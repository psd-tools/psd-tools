psd-tools
=========

``psd-tools`` is a package for reading Adobe Photoshop PSD files
(as described in specification_) to Python data structures.

.. _specification: https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/PhotoshopFileFormats.htm

Installation
------------

::

    pip install psd-tools

There are also optional dependencies: docopt_ for command-line interface
and PIL_ (or Pillow_) for accessing PSD layer data as PIL images::

    pip install Pillow
    pip install docopt


.. _docopt: https://github.com/docopt/docopt
.. _PIL: http://www.pythonware.com/products/pil/
.. _Pillow: https://github.com/python-imaging/Pillow


Usage
-----

Load an image::

    >>> from psd_tools import PSDImage
    >>> psd = PSDImage.load('my_image.psd')

Access its layers::

    >>> psd.layers
    [<psd_tools.Group: 'Group 2', layer_count=1>,
     <psd_tools.Group: 'Group 1', layer_count=1>,
     <psd_tools.Layer: 'Background', size=100x200>]

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
    [<psd_tools.Layer: 'Shape 2', size=43x62>]

Work with a layer::

    >>> layer = group2.layers[0]
    >>> layer.name
    Shape 2

    >>> layer.bbox
    (40, 72, 83, 134)

    >>> layer.width, layer.height
    (43, 62)

    >>> layer.visible, layer.opacity, layer.blend_mode
    (True, 255, u'norm')

    >>> layer.as_PIL()
    <PIL.Image.Image image mode=RGBA size=43x62 at ...>

Export a single layer::

    >>> layer_image = layer.as_PIL()
    >>> layer_image.save('layer.png')

Export the merged image::

    >>> merged_image = psd.composite_image()
    >>> merged_image.save('my_image.png')


Why yet another PSD reader?
---------------------------

There are existing PSD readers for Python:

* `psdparse <https://github.com/jerem/psdparse>`_;
* `pypsd <https://code.google.com/p/pypsd>`_;
* there is a PSD reader in PIL_ library;
* it is possible to write Python plugins for GIMP_.

PIL doesn't have an API for layer groups, PSD reader in PIL is incomplete
and contributing to PIL is somehow complicated because of the
slow release process.

GIMP is cool, but it is a huge dependency, its PSD parser
is not perfect and it is not easy to use GIMP Python plugin
from *your* code.

I also considered contributing to pypsd or psdparse, but they are
GPL and I was not totally satisfied with the interface and the code
(they are really fine, that's me having specific style requirements).

So I finally decided to roll out yet another implementation
that should be MIT-licensed, systematically based on the specification_;
parser should be implemented as a set of functions; the package should
also have tests and support both Python 2.x and Python 3.x.

.. _GIMP: http://www.gimp.org/

Design overview
---------------

The process of handling a PSD file is splitted into 3 stages:

1) "Reading": the file is read and parsed to low-level data
   structures that closely match the specification. No PIL images
   are constructed; image resources blocks and additional layer
   information are extracted but not parsed (they remain just keys
   with a binary data). The goal is to extract all necessary
   information from a PSD file.

2) "Decoding": image resource blocks and additional layer
   information blocks are parsed to a more detailed data structures
   (that are still based on a specification). There are a lot of PSD
   data types and the library currently doesn't handle them all, but
   it should be easy to add the parsing code for the missing PSD data
   structures if needed.

After (1) and (2) we have an in-memory data structure that closely
resembles PSD file; it should be fairly complete but very low-level
and not easy to use. So there is a third stage:

3) "User-facing API": PIL images of the PSD layers are created and
   combined to a user-friendly data structure.

Stage separation also means user-facing API may be opinionated:
if somebody doesn't like it then it should possible to build an
another API (e.g. without PIL) based on lower-level decoded PSD file.


Contributing
------------

Development happens at github and bitbucket:

* https://github.com/kmike/psd-tools
* https://bitbucket.org/kmike/psd-tools

The main issue tracker is at github: https://github.com/kmike/psd-tools/issues

Feel free to submit ideas, bugs, pull requests (git or hg) or regular patches.

In case of bugs it would be helpful to provide a small PSD file
demonstrating the issue; this file may be added to a test suite.

In order to run tests, install `tox <http://tox.testrun.org>`_ and type

::

    tox

from the source checkout.

The license is MIT.
