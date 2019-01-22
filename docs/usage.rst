Usage
=====

Command line
------------

The package provides command line tools to handle a PSD document::

    psd-tools export <input_file> <output_file> [options]
    psd-tools show <input_file> [options]
    psd-tools debug <input_file> [options]
    psd-tools -h | --help
    psd-tools --version

Example::

    psd-tools show example.psd  # Show the file content
    psd-tools export example.psd example.png  # Export as PNG
    psd-tools export example.psd[0] example-0.png  # Export layer as PNG

Working with PSD document
-------------------------

:py:mod:`psd_tools2.api` package provides the user-friendly API to work
with PSD files.
:py:class:`~psd_tools2.PSDImage` represents a PSD file.

Open an image::

    from psd_tools2 import PSDImage
    psd = PSDImage.open('my_image.psd')

Most of the data structure in the :py:mod:`psd-tools2` suppports pretty
printing in IPython environment::

    In [1]: PSDImage.open('example.psd')
    Out[1]:
    PSDImage(mode=RGB size=101x55 depth=8 channels=3)
      [0] PixelLayer('Background' size=101x55)
      [1] PixelLayer('Layer 1' size=85x46)

Internal layers are accessible by iterator or indexing::

    for layer in psd:
        print(layer)
        if layer.is_group():
            for child in layer:
                print(child)

    child = psd[0][0]

Working with Layers
-------------------

There are various layer kinds in Photoshop.

The most basic layer type is :py:class:`~psd_tools2.api.layers.PixelLayer`::

    print(layer.name)
    layer.kind == 'pixel'

:py:class:`~psd_tools2.api.layers.Group` has internal layers::

    group[0]
    for layer in group:
        print(layer)


Exporting data to PIL
---------------------

Export the entire document as PIL::

    image = psd.topil()
    image.save('exported.png')

Note that above :py:meth:`~psd_tools2.PSDImage.topil` might return ``None``
if the PSD document is saved without `Maximize compatibility` option. In that
case, or to force layer composition, use
:py:meth:`~psd_tools2.PSDImage.compose`::

    image = psd.compose()

Note that empty image returns ``None``.

Export a single layer including masks and clipping layers::

    image = layer.compose()

Export layer, mask, or clipping layers separately without composition::

    image = layer.topil()
    mask = layer.mask.topil()

    from psd_tools2.api.composer import compose
    clip_image = compose(layer.clip_layers)
