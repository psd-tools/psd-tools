psd\_tools2\.api\.adjustments
=============================

.. automodule:: psd_tools2.api.adjustments

.. _fill-layers:

Fill layers
-----------

Fill layers are similar to :py:class:`~psd_tools2.api.layers.ShapeLayer`
except that the layer might not have an associated vector mask. The layer
therefore expands the entire canvas of the PSD document.

Fill layers all inherit from :py:class:`~psd_tools2.api.layers.FillLayer`.

Example::

    if isinstance(layer, psd_tools2.layers.FillLayer):
        image = layer.compose()

.. autoclass:: psd_tools2.api.adjustments.SolidColorFill
    :members:
    :inherited-members:

.. autoclass:: psd_tools2.api.adjustments.PatternFill
    :members:
    :inherited-members:

.. autoclass:: psd_tools2.api.adjustments.GradientFill
    :members:
    :inherited-members:

.. _adjustment-layers:

Adjustment layers
-----------------

Adjustment layers apply image filtering to the composed result. All adjustment
layers inherit from
:py:class:`~psd_tools2.api.layers.AdjustmentLayer`. Adjustment layers do not
have pixels, and currently ignored in `compose`. Attempts to call `topil`
on adjustment layers always return `None`.

Just as any other layer, adjustment layers might have an associated mask or
vector mask. Adjustment can appear in other layers' clipping layers.

Example::

    if isinstance(layer, psd_tools2.layers.AdjustmentLayer):
        print(layer.kind)

.. autoclass:: psd_tools2.api.adjustments.BrightnessContrast
    :members:
    :undoc-members:

.. autoclass:: psd_tools2.api.adjustments.Curves
    :members:
    :undoc-members:

.. autoclass:: psd_tools2.api.adjustments.Exposure
    :members:
    :undoc-members:

.. autoclass:: psd_tools2.api.adjustments.Levels
    :members:
    :undoc-members:

.. autoclass:: psd_tools2.api.adjustments.Vibrance
    :members:
    :undoc-members:

.. autoclass:: psd_tools2.api.adjustments.HueSaturation
    :members:
    :undoc-members:

.. autoclass:: psd_tools2.api.adjustments.ColorBalance
    :members:
    :undoc-members:

.. autoclass:: psd_tools2.api.adjustments.BlackAndWhite
    :members:
    :undoc-members:

.. autoclass:: psd_tools2.api.adjustments.PhotoFilter
    :members:
    :undoc-members:

.. autoclass:: psd_tools2.api.adjustments.ChannelMixer
    :members:
    :undoc-members:

.. autoclass:: psd_tools2.api.adjustments.ColorLookup
    :members:
    :undoc-members:

.. autoclass:: psd_tools2.api.adjustments.Posterize
    :members:
    :undoc-members:

.. autoclass:: psd_tools2.api.adjustments.Threshold
    :members:
    :undoc-members:

.. autoclass:: psd_tools2.api.adjustments.SelectiveColor
    :members:
    :undoc-members:

.. autoclass:: psd_tools2.api.adjustments.GradientMap
    :members:
    :undoc-members:
