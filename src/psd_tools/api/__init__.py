"""
High-level API for working with PSD/PSB files.

This subpackage provides the user-facing API for psd-tools, offering
Pythonic interfaces for manipulating Photoshop documents. It wraps the
low-level :py:mod:`psd_tools.psd` binary structures with convenient
methods and properties.

The main entry point is :py:class:`~psd_tools.api.psd_image.PSDImage`,
which provides document-level operations. Individual layers are represented
by various layer classes in :py:mod:`psd_tools.api.layers`.

Key modules:

- :py:mod:`psd_tools.api.psd_image`: Main PSDImage class for document operations
- :py:mod:`psd_tools.api.layers`: Layer type hierarchy (Layer, GroupMixin, etc.)
- :py:mod:`psd_tools.api.adjustments`: Adjustment layer types
- :py:mod:`psd_tools.api.mask`: Layer mask operations
- :py:mod:`psd_tools.api.shape`: Vector shape and stroke operations
- :py:mod:`psd_tools.api.effects`: Layer effects (shadows, glows, etc.)
- :py:mod:`psd_tools.api.pil_io`: PIL/Pillow image I/O utilities
- :py:mod:`psd_tools.api.numpy_io`: NumPy array I/O utilities

Example usage::

    from psd_tools import PSDImage

    # Open a PSD file
    psd = PSDImage.open('document.psd')

    # Access layers
    for layer in psd:
        print(f"{layer.name}: {layer.kind}")

    # Modify a layer
    layer = psd[0]
    layer.name = "New Name"
    layer.opacity = 128

    # Save changes
    psd.save('modified.psd')

The API layer automatically reconstructs the layer tree from the flat
list of layer records in the PSD file, establishing proper parent-child
relationships for groups.
"""
