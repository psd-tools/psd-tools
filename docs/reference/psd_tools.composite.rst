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

Vector shape and path rendering. A path is filled by
:py:mod:`psd_tools.composite.scanline`; aggdraw draws the pen of a stroke.

Path Rasterization
------------------

.. automodule:: psd_tools.composite.scanline
    :members:

Exact-coverage rasterization of a filled path: the area the path covers in
each pixel, computed rather than sampled.

Effects Rendering
-----------------

.. automodule:: psd_tools.composite.effects
    :members:

Layer effects rendering including strokes, shadows, and glows. Requires
scipy for the distance transform that places a stroke of any position, and
scikit-image for pattern fills.
