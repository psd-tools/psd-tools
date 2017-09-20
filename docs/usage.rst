Usage
=====

Load an image::

    >>> from psd_tools import PSDImage
    >>> psd = PSDImage.load('my_image.psd')

Print the layer structure::

    >>> psd.print_tree()

Read image header::

    >>> psd.header
    PsdHeader(number_of_channels=3, height=200, width=100, depth=8, color_mode=RGB)

Access its layers::

    >>> psd.layers
    [<Group: 'Group 2', layer_count=1, mask=None, visible=1>,
     <Group: 'Group 1', layer_count=1, mask=None, visible=1>,
     <PixelLayer: 'Background', size=100x200, x=0, y=0, mask=None, visible=1>]

Work with a layer group::

    >>> group2 = psd.layers[0]
    >>> group2.name
    Group 2

    >>> group2.visible
    True

    >>> group2.closed
    False

    >>> group2.opacity
    255

    >>> from psd_tools.constants import BlendMode
    >>> group2.blend_mode == BlendMode.NORMAL
    True

    >>> group2.layers
    [<ShapeLayer: 'Shape 2', size=43x62, x=40, y=72, mask=None, visible=1)>]

Work with a layer::

    >>> layer = group2.layers[0]
    >>> layer.name
    Shape 2

    >>> layer.kind
    type

    >>> layer.bbox
    BBox(x1=40, y1=72, x2=83, y2=134)

    >>> layer.bbox.width, layer.bbox.height
    (43, 62)

    >>> layer.visible, layer.opacity, layer.blend_mode
    (True, 255, u'norm')

    >>> layer.text
    'Text inside a text box'

    >>> layer.as_PIL()
    <PIL.Image.Image image mode=RGBA size=43x62 at ...>

    >>> mask = layer.mask
    >>> mask.bbox
    BBox(x1=40, y1=72, x2=83, y2=134)

    >>> mask.as_PIL()
    <PIL.Image.Image image mode=L size=43x62 at ...>

    >>> layer.clip_layers
    [<Layer: 'Clipped', size=43x62, x=40, y=72, mask=None, visible=1)>, ...]

    >>> layer.effects
    [<GradientOverlay>]

Export a single layer::

    >>> layer_image = layer.as_PIL()
    >>> layer_image.save('layer.png')

Export the merged image::

    >>> merged_image = psd.as_PIL()
    >>> merged_image.save('my_image.png')

The same using Pymaging::

    >>> merged_image = psd.as_pymaging()
    >>> merged_image.save_to_path('my_image.png')
    >>> layer_image = layer.as_pymaging()
    >>> layer_image.save_to_path('layer.png')

Export layer group (experimental)::

    >>> group_image = group2.as_PIL()
    >>> group_image.save('group.png')

Get pattern dict::

    >>> psd.patterns
    {'b2fdfd29-de85-11d5-838b-ff55e75fb875': <psd_tools.Pattern: size=265x219 ...>}
