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

:py:mod:`psd_tools.api` package provides the user-friendly API to work
with PSD files.
:py:class:`~psd_tools.PSDImage` represents a PSD file.

Open an image::

    from psd_tools import PSDImage
    psdimage = PSDImage.open('my_image.psd')

Most of the data structure in the :py:mod:`psd-tools` suppports pretty
printing in IPython environment.

.. code-block:: none

    In [1]: PSDImage.open('example.psd')
    Out[1]:
    PSDImage(mode=RGB size=101x55 depth=8 channels=3)
      [0] PixelLayer('Background' size=101x55)
      [1] PixelLayer('Layer 1' size=85x46)

Internal layers are accessible by iterator or indexing::

    for layer in psdimage:
        print(layer)
        if layer.is_group():
            for child in layer:
                print(child)

    child = psdimage[0][0]

.. note:: The iteration order is from background to foreground, which is
    reversed from version prior to 1.7.x. Use ``reversed(psd)`` to
    iterate from foreground to background.

The opened PSD file can be saved::

    psdimage.save('output.psd')

If the PSD File's layer structure was updated, saving it will update the ImageData section.
However, the rendered image is likely different from the Photoshop's rendering due to the
limited rendering support in psd_tools.

Working with Layers
-------------------

There are various layer kinds in Photoshop.

The most basic layer type is :py:class:`~psd_tools.api.layers.PixelLayer`::

    print(layer.name)
    layer.kind == 'pixel'

Some of the layer attributes are editable, such as a layer name::

    layer.name = 'Updated layer 1'

psd_tools experimentally supports the creation of a new PixelLayer from a PIL object,
the PIL image will be converted to the color mode of the PSD File given in parameter::

    psdimage.create_pixel_layer(pil_image, name="Layer name")

To construct a layered PSD file from scratch::

    psdimage = PSDImage.new(mode='RGB', size=(640, 480), depth=8)
    layer = psdimage.create_pixel_layer(pil_image, name="Layer 1", top=0, left=0, opacity=255)
    group = psdimage.create_group(name="Group 1")
    group.append(layer)
    psdimage.save('new_image.psd')

See the function documentation for further parameter explanations.

:py:class:`~psd_tools.api.layers.Group` has internal layers::

    for layer in group:
        print(layer)

    first_layer = group[0]

Create a new group object.::

    group = psdimage.create_group(name="Group name")
    group.append(layer)

:py:class:`~psd_tools.api.layers.TypeLayer` is a layer with texts::

    print(layer.text)

:py:class:`~psd_tools.api.layers.ShapeLayer` draws a vector shape, and the
shape information is stored in `vector_mask` and `origination` property.
Other layers can also have shape information as a mask::

    print(layer.vector_mask)
    for shape in layer.origination:
        print(shape)

:py:class:`~psd_tools.api.layers.SmartObjectLayer` embeds or links an
external file for non-destructive editing. The file content is accessible
via `smart_object` property::

    import io
    if layer.smart_object.filetype in ('jpg', 'png'):
        image = Image.open(io.BytesIO(layer.smart_object.data))

:py:class:`~psd_tools.api.adjustments.SolidColorFill`,
:py:class:`~psd_tools.api.adjustments.PatternFill`, and
:py:class:`~psd_tools.api.adjustments.GradientFill` are fill layers that
paint the entire region if there is no associated mask. Sub-classes of
:py:class:`~psd_tools.api.layers.AdjustmentLayer` represents layer
adjustment applied to the composed image. See :ref:`adjustment-layers`.


Modifying the layer structure
-----------------------------

The layer structure of a PSD object can be modified through methods emulating a python list.

The internal model of the psd layer structure will be automatically updated.
Moving a layer from a PSD to another will also automatically convert the PixelLayer to the target psd's color mode.

The follwing are valid for both PSDImage and Group objects.

Set an item::

    group[0] = layer

Add a layer or layers to a group::

    group.append(layer)
    group.extend(layers)

Insert a layer to a specific index in the group::

    group.insert(3, layer)

Remove a layer from the a group::

    group.remove(layer)

Pop a layer from the group::

    layer = group.pop()

Emptying a layer group::

    group.clear()

Get the index of a layer in the group::

    index = group.index(layer)

Count the occurrences of a layer in a group::

    count = group.count(layer)

Move a given list of layers in a newly created Group. If no parent group is given in parameter, 
the new group will replace the first layer of the list in the PSD structure::

    group = psdimage.create_group(layer_list=[layer1, layer2, ...], name="New Group")

Some operations are available for all ``Layer`` objects.

Delete a layer from its layer structure::

    group.remove(layer)

Layers can be moved from a group to another::

    target_group.append(layer)

Layers can be moved within the group to change their order::
    
    layer.move_up() # Will send the layer upward in the group
    layer.move_down() # Will send the layer downward in the group


Exporting data to PIL
---------------------

Export the entire document as :py:class:`PIL.Image`::

    image = psd.composite()
    image.save('exported.png')

Export a single layer including masks and clipping layers::

    image = layer.composite()

Export layer and mask separately without composition::

    image = layer.topil()
    mask = layer.mask.topil()

To composite specific layers, such as layers except for texts, use layer_filter
option::

    image = psd.composite(
        layer_filter=lambda layer: layer.is_visible() and layer.kind != 'type')

.. note::

    Advanced compositing features require optional dependencies. Install with::

        pip install psd-tools[composite]

    These dependencies (``aggdraw``, ``scipy``, ``scikit-image``) are needed for:

    - Vector shapes and strokes
    - Gradient and pattern fills
    - Layer effects

    Basic compositing works without them by using cached previews or simple
    pixel-based operations. If a feature requires missing dependencies, an
    ``ImportError`` with installation instructions will be raised.

Note that most of the layer effects and adjustment layers are not supported.
The compositing result may look different from Photoshop.

Exporting data to NumPy
-----------------------

PSDImage or layers can be exported to NumPy array by
:py:meth:`~psd_tools.api.layers.PixelLayer.numpy` method::

    image = psd.numpy()
    layer_image = layer.numpy()
