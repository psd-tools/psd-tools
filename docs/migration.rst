Migrating from version 1.7 to 1.8
=================================

There are major API changes in version 1.8.x.

Package name
------------

Starting version 1.8.0, the package name is changed from `psd_tools` to
`psd_tools2`.

version 1.7.x::

    import psd_tools
    from psd_tools import PSDImage

version 1.8.x::

    import psd_tools2
    from psd_tools2 import PSDImage

PSDImage
--------

File open method is changed from `load` to
:py:meth:`~psd_tools2.PSDImage.open`.

version 1.7.x::

    psd = PSDImage.load(filename)
    with open(filename, 'rb') as f:
        psd = PSDImage.from_stream(f)

version 1.8.x::

    psd = PSDImage.open(filename)
    with open(filename, 'rb') as f:
        psd = PSDImage.open(f)

Layers
------

Children of PSDImage or Group is directly accessible by iterator or indexing.

version 1.7.x::

    for layer in group.layers:
        print(layer)

    first_child = group.layers[0]

version 1.8.x::

    for layer in group:
        print(layer)

    first_child = group[0]


In version 1.8.x, the order of layers is reversed to reflect that the index
should not change when a new layer is added on top.

PIL export
----------

Primary PIL export method is now :py:func:`~psd_tools2.compose`.

version 1.7.x::

    image = psd.as_PIL()

    layer_image = compose(layer)
    raw_layer_image = layer.as_PIL()

version 1.8.x::

    image = psd.compose()

    layer_image = layer.compose()
    raw_layer_image = layer.topil()


Low-level data structure
------------------------

Data structures are completely rewritten to support writing functionality.
See :py:mod:`psd_tools2.psd` subpackage.

version 1.7.x::

    psd.decoded_data

version 1.8.x::

    psd._record
