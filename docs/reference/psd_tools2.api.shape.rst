psd\_tools2\.api\.shape
=======================

.. automodule:: psd_tools2.api.shape

VectorMask
----------

.. autoclass:: psd_tools2.api.shape.VectorMask
    :members:

Stroke
------

.. autoclass:: psd_tools2.api.shape.Stroke
    :members:

Origination
-----------

Origination keeps live shape properties for some of the primitive shapes.
Origination objects are accessible via
:py:attr:`~psd_tools2.api.layers.Layer.origination` property of layers.
Following primitive shapes are
defined: :py:class:`~psd_tools2.api.shape.Invalidated`,
:py:class:`~psd_tools2.api.shape.Line`,
:py:class:`~psd_tools2.api.shape.Rectangle`,
:py:class:`~psd_tools2.api.shape.Ellipse`,
and :py:class:`~psd_tools2.api.shape.RoundedRectangle`.

.. autoclass:: psd_tools2.api.shape.Invalidated
    :members:

.. autoclass:: psd_tools2.api.shape.Line
    :members:
    :inherited-members:

.. autoclass:: psd_tools2.api.shape.Ellipse
    :members:
    :inherited-members:

.. autoclass:: psd_tools2.api.shape.Rectangle
    :members:
    :inherited-members:

.. autoclass:: psd_tools2.api.shape.RoundedRectangle
    :members:
    :inherited-members:
