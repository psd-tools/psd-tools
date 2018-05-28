psd-tools\.reader
=================

The reader package provides a low-level API to read binary data from PSD file.
According to the `specification`_, Adobe Photoshop files have the following
five sections. The reader package reads these sections without parsing the
individual data structure:

 - File header
 - Color mode data
 - Image resources
 - Layer and mask information
 - Image data

The API is intended to be internally used in the :doc:`decoder` package.

.. _specification: https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/


parse
-----

.. autofunction:: psd_tools.reader.parse

ParseResult
-----------

.. autoclass:: psd_tools.reader.reader.ParseResult
    :members:
    :undoc-members:

PsdHeader
---------

.. autoclass:: psd_tools.reader.header.PsdHeader
    :members:
    :undoc-members:

ImageResource
-------------

.. autoclass:: psd_tools.reader.image_resources.ImageResource
    :members:
    :undoc-members:

Block
-----

.. autoclass:: psd_tools.reader.layers.Block
    :members:
    :undoc-members:

ChannelData
-----------

.. autoclass:: psd_tools.reader.layers.ChannelData
    :members:
    :undoc-members:

ChannelInfo
-----------

.. autoclass:: psd_tools.reader.layers.ChannelInfo
    :members:
    :undoc-members:

GlobalMaskInfo
--------------

.. autoclass:: psd_tools.reader.layers.GlobalMaskInfo
    :members:
    :undoc-members:

LayerAndMaskData
----------------

.. autoclass:: psd_tools.reader.layers.LayerAndMaskData
    :members:
    :undoc-members:

LayerBlendingRanges
-------------------

.. autoclass:: psd_tools.reader.layers.LayerBlendingRanges
    :members:
    :undoc-members:

LayerFlags
----------

.. autoclass:: psd_tools.reader.layers.LayerFlags
    :members:
    :undoc-members:

LayerRecord
-----------

.. autoclass:: psd_tools.reader.layers.LayerRecord
    :members:
    :undoc-members:

Layers
------

.. autoclass:: psd_tools.reader.layers.Layers
    :members:
    :undoc-members:

MaskData
--------

.. autoclass:: psd_tools.reader.layers.MaskData
    :members:
    :undoc-members:

MaskFlags
---------

.. autoclass:: psd_tools.reader.layers.MaskFlags
    :members:
    :undoc-members:

MaskParameters
--------------

.. autoclass:: psd_tools.reader.layers.MaskParameters
    :members:
    :undoc-members:
