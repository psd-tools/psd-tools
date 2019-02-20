psd-tools
=========

`psd-tools` is a Python package for working with Adobe Photoshop PSD files
as described in specification_.

.. _specification: https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/
.. _psd-tools: https://github.com/psd-tools/psd-tools

.. image:: https://img.shields.io/pypi/v/psd-tools.svg
   :target: https://pypi.python.org/pypi/psd-tools
   :alt: PyPI Version

.. image:: https://img.shields.io/travis/psd-tools/psd-tools/master.svg
   :alt: Build Status
   :target: https://travis-ci.org/psd-tools/psd-tools

.. image:: https://readthedocs.org/projects/psd-tools/badge/
   :alt: Document Status
   :target: http://psd-tools.readthedocs.io/en/latest/

.. _psd-tools: https://github.com/psd-tools/psd-tools

Installation
------------

Use ``pip`` to install the package::

    pip install psd-tools

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

    from psd_tools import PSDImage

    psd = PSDImage.open('example.psd')
    psd.compose().save('example.png')

    for layer in psd:
        print(layer)

Check out the documentation_ for features and details.

.. _documentation: https://psd-tools.readthedocs.io/

Contributing
------------

See contributing_ page.

.. _contributing: https://github.com/psd-tools/psd-tools/blob/master/docs/contributing.rst
