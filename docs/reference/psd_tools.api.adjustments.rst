psd\_tools\.api\.adjustments
============================

.. automodule:: psd_tools.api.adjustments

.. _fill-layers:

Fill layers
-----------

Fill layers are similar to :py:class:`~psd_tools.api.layers.ShapeLayer`
except that the layer might not have an associated vector mask. The layer
therefore expands the entire canvas of the PSD document.

Fill layers all inherit from :py:class:`~psd_tools.api.layers.FillLayer`.

Example::

    if isinstance(layer, psd_tools.layers.FillLayer):
        image = layer.compose()

SolidColorFill
^^^^^^^^^^^^^^

.. autoclass:: psd_tools.api.adjustments.SolidColorFill
    :members:
    :inherited-members:

PatternFill
^^^^^^^^^^^

.. autoclass:: psd_tools.api.adjustments.PatternFill
    :members:
    :inherited-members:

GradientFill
^^^^^^^^^^^^

.. autoclass:: psd_tools.api.adjustments.GradientFill
    :members:
    :inherited-members:

.. _adjustment-layers:

Adjustment layers
-----------------

Adjustment layers apply image filtering to the composed result. All adjustment
layers inherit from
:py:class:`~psd_tools.api.layers.AdjustmentLayer`. Adjustment layers do not
have pixels, and currently ignored in `compose`. Attempts to call `topil`
on adjustment layers always return `None`.

Just as any other layer, adjustment layers might have an associated mask or
vector mask. Adjustment can appear in other layers' clipping layers.

Example::

    if isinstance(layer, psd_tools.layers.AdjustmentLayer):
        print(layer.kind)

BrightnessContrast
^^^^^^^^^^^^^^^^^^

.. autoclass:: psd_tools.api.adjustments.BrightnessContrast
    :members:
    :undoc-members:

Curves
^^^^^^

.. autoclass:: psd_tools.api.adjustments.Curves
    :members:
    :undoc-members:

Exposure
^^^^^^^^

.. autoclass:: psd_tools.api.adjustments.Exposure
    :members:
    :undoc-members:

Levels
^^^^^^

.. autoclass:: psd_tools.api.adjustments.Levels
    :members:
    :undoc-members:

Vibrance
^^^^^^^^

.. autoclass:: psd_tools.api.adjustments.Vibrance
    :members:
    :undoc-members:

HueSaturation
^^^^^^^^^^^^^

.. autoclass:: psd_tools.api.adjustments.HueSaturation
    :members:
    :undoc-members:

ColorBalance
^^^^^^^^^^^^

.. autoclass:: psd_tools.api.adjustments.ColorBalance
    :members:
    :undoc-members:

BlackAndWhite
^^^^^^^^^^^^^

.. autoclass:: psd_tools.api.adjustments.BlackAndWhite
    :members:
    :undoc-members:

PhotoFilter
^^^^^^^^^^^

.. autoclass:: psd_tools.api.adjustments.PhotoFilter
    :members:
    :undoc-members:

ChannelMixer
^^^^^^^^^^^^

.. autoclass:: psd_tools.api.adjustments.ChannelMixer
    :members:
    :undoc-members:

ColorLookup
^^^^^^^^^^^

.. autoclass:: psd_tools.api.adjustments.ColorLookup
    :members:
    :undoc-members:

Posterize
^^^^^^^^^

.. autoclass:: psd_tools.api.adjustments.Posterize
    :members:
    :undoc-members:

Threshold
^^^^^^^^^

.. autoclass:: psd_tools.api.adjustments.Threshold
    :members:
    :undoc-members:

SelectiveColor
^^^^^^^^^^^^^^

.. autoclass:: psd_tools.api.adjustments.SelectiveColor
    :members:
    :undoc-members:

GradientMap
^^^^^^^^^^^

.. autoclass:: psd_tools.api.adjustments.GradientMap
    :members:
    :undoc-members:
