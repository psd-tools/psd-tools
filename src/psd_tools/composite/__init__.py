"""
Composite module for layer rendering and blending.

This subpackage provides the rendering engine for compositing PSD layers
into raster images. It implements Photoshop's blend modes, layer effects,
and vector shape rasterization.

**Note**: This module requires optional dependencies. Install with::

    pip install 'psd-tools[composite]'

Or using uv::

    uv sync --extra composite

The composite extra includes:

- ``aggdraw``: For vector path and bezier curve rasterization
- ``scipy``: For advanced image processing operations
- ``scikit-image``: For morphological operations in effects

Key modules:

- :py:mod:`psd_tools.composite.composite`: Main compositing functions
- :py:mod:`psd_tools.composite.blend`: Blend mode implementations
- :py:mod:`psd_tools.composite.effects`: Layer effects (stroke, shadow, etc.)
- :py:mod:`psd_tools.composite.vector`: Vector shape and path rendering
- :py:mod:`psd_tools.composite.paint`: Fill rendering (gradients, patterns)

Example usage::

    from psd_tools import PSDImage

    psd = PSDImage.open('document.psd')

    # Composite entire document to PIL Image
    image = psd.composite()
    image.save('output.png')

    # Composite specific layer
    layer_image = psd[0].composite()

The compositing engine uses NumPy arrays for efficient pixel manipulation
and supports all of Photoshop's standard blend modes including multiply,
screen, overlay, soft light, and more.

Performance considerations:

- Compositing can be memory-intensive for large documents
- Vector shapes require aggdraw for accurate rendering
- Some effects have limited support compared to Photoshop
"""

from psd_tools.composite.composite import composite, composite_pil

__all__ = [
    "composite",
    "composite_pil",
]
