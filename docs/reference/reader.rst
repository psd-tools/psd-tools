psd-tools\.reader
=================

.. automodule:: psd_tools.reader

The reader package provides a low-level API to read binary data from PSD
files. According to the `specification`_, Adobe Photoshop files have the
following five sections. The reader package reads these sections without
parsing the individual data structure:

 - File header
 - Color mode data
 - Image resources
 - Layer and mask information
 - Image data

:py:class:`~psd_tools.reader.reader.ParseResult` holds all the data fields above::

    ParseResult(
     header=PsdHeader(version=1, number_of_channels=3, height=1200, width=1600, depth=8, color_mode=RGB),
     color_data='',
     image_resource_blocks=[ImageResource(1005 RESOLUTION_INFO, u'', '\x00d\x00\x00\x00\x01\x00\x01\x00d\x00\x00\x00\x01\x00\x01'),
      ImageResource(1039 ICC_PROFILE, u'', '\x00\x00#xlcms\x02\x10\x00\x00mntrRGB XYZ \x07\xdf\x00\x0b\x00\n ... =9080')],
     layer_and_mask_data=LayerAndMaskData(
      layers=Layers( layer_count=0, layer_records=[], channel_image_data=[]),
      global_mask_info=None,
      tagged_blocks=[]),
     image_data=[ChannelData(compression=1 PACK_BITS, len(data)=32568),
      ChannelData(compression=1 PACK_BITS, len(data)=32568),
      ChannelData(compression=1 PACK_BITS, len(data)=32568)])

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
