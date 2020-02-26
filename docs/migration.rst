Migrating to 1.9
================

psd-tools 1.9 switches to NumPy based compositing.

version 1.8.x::

    psd = PSDImage.open(filename)
    image = psd.compose()
    layer = psd[0]
    layer_image = layer.compose()

version 1.9.x::

    psd = PSDImage.open(filename)
    image = psd.composite()
    layer = psd[0]
    layer_image = layer.composite()

NumPy array API is introduced::

    image = psd.numpy()
    layer_image = layer.numpy()

Migrating to 1.8
================

There are major API changes in version 1.8.x.

.. note:: In version 1.8.0 - 1.8.7, the package name was `psd_tools2`.

PSDImage
--------

File open method is changed from `load` to
:py:meth:`~psd_tools.PSDImage.open`.

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

Primary PIL export method is :py:func:`~psd_tools.compose`.

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
See :py:mod:`psd_tools.psd` subpackage.

version 1.7.x::

    psd.decoded_data

version 1.8.x::

    psd._record

Drop pymaging support
---------------------

Pymaging support is dropped.
