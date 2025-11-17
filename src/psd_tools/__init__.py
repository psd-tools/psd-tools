"""
psd-tools: Python package for reading and writing Adobe Photoshop PSD files.

This package provides a comprehensive toolkit for working with PSD/PSB files,
offering both low-level binary structure access and high-level user-friendly APIs.

Basic usage::

    from psd_tools import PSDImage

    # Open and read a PSD file
    psd = PSDImage.open('example.psd')

    # Iterate through layers
    for layer in psd:
        print(layer.name)

    # Export to PNG
    psd.composite().save('output.png')

Architecture:

- :py:mod:`psd_tools.psd`: Low-level binary structure parsing/writing
- :py:mod:`psd_tools.api`: High-level user-facing API (primary interface)
- :py:mod:`psd_tools.composite`: Layer rendering and blending engine
- :py:mod:`psd_tools.compression`: Image compression codecs (RLE, ZIP)

For most users, the :py:class:`PSDImage` class provides all necessary functionality.
Advanced users can access low-level structures via the ``_record`` attribute.
"""

from psd_tools.api.psd_image import PSDImage
from psd_tools.version import __version__

__all__ = ["PSDImage", "__version__"]
