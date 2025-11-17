psd\_tools\.composite
======================

.. automodule:: psd_tools.composite

This module provides layer rendering and compositing functionality.

**Installation**: Requires optional dependencies::

    pip install psd-tools[composite]

Or with uv::

    uv sync --extra composite

Composite Functions
-------------------

.. autofunction:: psd_tools.composite.composite

.. autofunction:: psd_tools.composite.composite_pil

Blend Modes
-----------

.. automodule:: psd_tools.composite.blend
    :members:

The blend module implements Photoshop's blend modes following the Adobe PDF
specification. All blend functions operate on normalized float32 NumPy arrays.

Vector Rendering
----------------

.. automodule:: psd_tools.composite.vector
    :members:

Vector shape and path rendering using aggdraw for bezier curve rasterization.

Effects Rendering
-----------------

.. automodule:: psd_tools.composite.effects
    :members:

Layer effects rendering including strokes, shadows, and glows. Requires
scikit-image for morphological operations.
