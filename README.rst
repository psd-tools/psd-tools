psd-tools
=========

``psd-tools`` is a Python package for working with Adobe Photoshop PSD files
as described in specification_.

|pypi| |build| |docs|

.. _specification: https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/

.. |pypi| image:: https://img.shields.io/pypi/v/psd-tools.svg
    :alt: PyPI Version
    :target: https://pypi.python.org/pypi/psd-tools

.. |build| image:: https://github.com/psd-tools/psd-tools/actions/workflows/ci.yml/badge.svg
    :alt: Build
    :target: https://github.com/psd-tools/psd-tools/actions/workflows/ci.yml

.. |docs| image:: https://readthedocs.org/projects/psd-tools/badge/
    :alt: Document Status
    :target: http://psd-tools.readthedocs.io/en/latest/

Features
--------

Supported:

* Read and write of the low-level PSD/PSB file structure
* Raw layer image export in NumPy and PIL format

Limited support:

* Composition of basic pixel-based layers
* Composition of fill layer effects
* Vector masks
* Editing of some layer attributes such as layer name
* Blending modes except for dissolve
* Drawing of bezier curves

Not supported:

* Editing of layer structure, such as adding or removing a layer
* Composition of adjustment layers
* Composition of many layer effects
* Font rendering

Installation
------------

Use ``pip`` to install the package::

    pip install psd-tools

Getting started
---------------

.. code-block:: python

    from psd_tools import PSDImage

    psd = PSDImage.open('example.psd')
    psd.composite().save('example.png')

    for layer in psd:
        print(layer)
        layer_image = layer.composite()
        layer_image.save('%s.png' % layer.name)

Check out the documentation_ for features and details.

.. _documentation: https://psd-tools.readthedocs.io/

Contributing
------------

See contributing_ page.

.. _contributing: https://github.com/psd-tools/psd-tools/blob/master/docs/contributing.rst

.. note::

    PSD specification_ is far from complete. If you cannot find a desired
    information in the documentation_, you should inspect the low-level
    data structure.
