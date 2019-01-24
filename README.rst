psd-tools2
==========

``psd-tools2`` is a Python package for working with Adobe Photoshop PSD files
as described in specification_. ``psd-tools2`` is a fork of psd-tools_ that
implements various functionalities.

.. _specification: https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/
.. _psd-tools: https://github.com/psd-tools/psd-tools

.. image:: https://img.shields.io/pypi/v/psd-tools2.svg
   :target: https://pypi.python.org/pypi/psd-tools2
   :alt: PyPI Version

.. image:: https://img.shields.io/travis/kyamagu/psd-tools2/master.svg
   :alt: Build Status
   :target: https://travis-ci.org/kyamagu/psd-tools2

.. image:: https://readthedocs.org/projects/psd-tools2/badge/
   :alt: Document Status
   :target: http://psd-tools2.readthedocs.io/en/latest/

.. _psd-tools: https://github.com/psd-tools/psd-tools

Installation
------------

Use ``pip`` to install the package::

    pip install psd-tools2

.. note::

    In order to extract images from 32bit PSD files PIL/Pillow must be built
    with LITTLECMS or LITTLECMS2 support.

For complete layer image composition functionality, also install NumPy/SciPy.
This will be only necessary when the PSD files are saved without maximized
compatibility and the image contains gradient fill::

    pip install numpy scipy

Getting started
---------------

.. code-block:: python

    from psd_tools2 import PSDImage

    psd = PSDImage.open('example.psd')
    psd.compose().save('example.png')

    for layer in psd:
        print(layer)

Check out the documentation_ for details.

.. _documentation:: https://psd-tools2.readthedocs.io/

Features
--------

Supported:

* Read and write of the low-level PSD/PSB file structure;
* Raw layer image export;
* ICC profile handling for sRGB images.

Limited support:

* Composition of basic pixel-based layers by normal blending;
* Editing of some layer attributes such as layer name.

Not supported:

* Editing of layer structure, such as adding or removing a layer.
* Blending modes other than normal;
* Composition of layer effects;
* Drawing of bezier curves;
* Font rendering.

Contributing
------------

See `development <https://github.com/kyamagu/psd-tools2/blob/master/docs/contributing.rst>` page.
