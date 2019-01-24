psd-tools2
==========

``psd-tools2`` is a Python package for working with Adobe Photoshop PSD files
as described in specification_. ``psd-tools2`` is a fork of psd-tools_ that
implements various functionalities.

.. _specification: https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/
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
    psd.topil().save('example.png')

    for layer in psd:
        print(layer)

Check out the :doc:`usage` documentation for more examples.


.. toctree::
    :caption: Notes
    :maxdepth: 1

    usage
    migration
    contributing

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
* Drawing of bezier curves.


.. toctree::
    :caption: Package reference
    :maxdepth: 1

    reference/psd_tools2
    reference/psd_tools2.api.adjustments
    reference/psd_tools2.api.effects
    reference/psd_tools2.api.layers
    reference/psd_tools2.api.mask
    reference/psd_tools2.api.shape
    reference/psd_tools2.api.smart_object
    reference/psd_tools2.constants
    reference/psd_tools2.psd
    reference/psd_tools2.psd.color_mode_data
    reference/psd_tools2.psd.descriptor
    reference/psd_tools2.psd.engine_data
    reference/psd_tools2.psd.header
    reference/psd_tools2.psd.image_data
    reference/psd_tools2.psd.image_resources
    reference/psd_tools2.psd.layer_and_mask
    reference/psd_tools2.psd.tagged_blocks
    reference/psd_tools2.psd.vector

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
