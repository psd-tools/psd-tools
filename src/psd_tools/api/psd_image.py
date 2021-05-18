"""
PSD Image module.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools.constants import (
    Clipping, Compression, ColorMode, SectionDivider, Resource, Tag
)
from psd_tools.psd import PSD, FileHeader, ImageData, ImageResources
from psd_tools.api.layers import (
    Artboard, Group, PixelLayer, ShapeLayer, SmartObjectLayer, TypeLayer,
    GroupMixin, FillLayer
)
from psd_tools.api import adjustments
from psd_tools.api import deprecated

logger = logging.getLogger(__name__)


class PSDImage(GroupMixin):
    """
    Photoshop PSD/PSB file object.

    The low-level data structure is accessible at :py:attr:`PSDImage._record`.

    Example::

        from psd_tools import PSDImage

        psd = PSDImage.open('example.psd')
        image = psd.compose()

        for layer in psd:
            layer_image = layer.compose()
    """
    def __init__(self, data):
        assert isinstance(data, PSD)
        self._record = data
        self._layers = []
        self._tagged_blocks = None
        self._init()

    @classmethod
    def new(cls, mode, size, color=0, depth=8, **kwargs):
        """
        Create a new PSD document.

        :param mode: The color mode to use for the new image.
        :param size: A tuple containing (width, height) in pixels.
        :param color: What color to use for the image. Default is black.
        :return: A :py:class:`~psd_tools.api.psd_image.PSDImage` object.
        """
        header = cls._make_header(mode, size, depth)
        image_data = ImageData.new(header, color=color, **kwargs)
        # TODO: Add default metadata.
        return cls(
            PSD(
                header=header,
                image_data=image_data,
                image_resources=ImageResources.new(),
            )
        )

    @classmethod
    def frompil(cls, image, compression=Compression.RLE):
        """
        Create a new PSD document from PIL Image.

        :param image: PIL Image object.
        :param compression: ImageData compression option. See
            :py:class:`~psd_tools.constants.Compression`.
        :return: A :py:class:`~psd_tools.api.psd_image.PSDImage` object.
        """
        header = cls._make_header(image.mode, image.size)
        # TODO: Add default metadata.
        # TODO: Perhaps make this smart object.
        image_data = ImageData(compression=compression)
        image_data.set_data([channel.tobytes() for channel in image.split()],
                            header)
        return cls(
            PSD(
                header=header,
                image_data=image_data,
                image_resources=ImageResources.new(),
            )
        )

    @classmethod
    def open(cls, fp, **kwargs):
        """
        Open a PSD document.

        :param fp: filename or file-like object.
        :param encoding: charset encoding of the pascal string within the file,
            default 'macroman'. Some psd files need explicit encoding option.
        :return: A :py:class:`~psd_tools.api.psd_image.PSDImage` object.
        """
        if hasattr(fp, 'read'):
            self = cls(PSD.read(fp, **kwargs))
        else:
            with open(fp, 'rb') as f:
                self = cls(PSD.read(f, **kwargs))
        return self

    def save(self, fp, mode='wb', **kwargs):
        """
        Save the PSD file.

        :param fp: filename or file-like object.
        :param encoding: charset encoding of the pascal string within the file,
            default 'macroman'.
        :param mode: file open mode, default 'wb'.
        """
        if hasattr(fp, 'write'):
            self._record.write(fp, **kwargs)
        else:
            with open(fp, mode) as f:
                self._record.write(f, **kwargs)

    def topil(self, channel=None, apply_icc=False):
        """
        Get PIL Image.

        :param channel: Which channel to return; e.g., 0 for 'R' channel in RGB
            image. See :py:class:`~psd_tools.constants.ChannelID`. When `None`,
            the method returns all the channels supported by PIL modes.
        :param apply_icc: Whether to apply ICC profile conversion to sRGB.
        :return: :py:class:`PIL.Image`, or `None` if the composed image is not
            available.
        """
        from .pil_io import convert_image_data_to_pil
        if self.has_preview():
            return convert_image_data_to_pil(self, channel, apply_icc)
        return None

    @deprecated
    def compose(self, force=False, bbox=None, layer_filter=None):
        """
        Deprecated, use :py:func:`~psd_tools.PSDImage.composite`.

        Compose the PSD image.

        :param bbox: Viewport tuple (left, top, right, bottom).
        :return: :py:class:`PIL.Image`, or `None` if there is no pixel.
        """
        from psd_tools.composer import compose
        image = None
        if (not force or len(self) == 0) and not bbox and not layer_filter:
            image = self.topil()
        if image is None:
            image = compose(
                self,
                bbox=bbox or self.viewbox,
                force=force,
                layer_filter=layer_filter,
            )
        elif bbox is not None:
            image = image.crop(bbox)
        return image

    def numpy(self, channel=None):
        """
        Get NumPy array of the layer.

        :param channel: Which channel to return, can be 'color',
            'shape', 'alpha', or 'mask'. Default is 'color+alpha'.
        :return: :py:class:`numpy.ndarray`
        """
        from .numpy_io import get_array
        return get_array(self, channel)

    def composite(
        self,
        viewport=None,
        force=False,
        color=1.0,
        alpha=0.0,
        layer_filter=None,
        ignore_preview=False,
    ):
        """
        Composite the PSD image.

        :param viewport: Viewport bounding box specified by (x1, y1, x2, y2)
            tuple. Default is the viewbox of the PSD.
        :param ignore_preview: Boolean flag to whether skip compositing when a
            pre-composited preview is available.
        :param force: Boolean flag to force vector drawing.
        :param color: Backdrop color specified by scalar or tuple of scalar.
            The color value should be in [0.0, 1.0]. For example, (1., 0., 0.)
            specifies red in RGB color mode.
        :param alpha: Backdrop alpha in [0.0, 1.0].
        :param layer_filter: Callable that takes a layer as argument and
            returns whether if the layer is composited. Default is
            :py:func:`~psd_tools.api.layers.PixelLayer.is_visible`.
        :return: :py:class:`PIL.Image`.
        """
        from psd_tools.composite import composite_pil
        if not (ignore_preview or force or layer_filter) and self.has_preview():
            return self.topil()
        return composite_pil(self, color, alpha, viewport, layer_filter, force)

    def is_visible(self):
        """
        Returns visibility of the element.

        :return: `bool`
        """
        return self.visible

    @property
    def parent(self):
        """Parent of this layer."""
        return None

    def is_group(self):
        """
        Return True if the layer is a group.

        :return: `bool`
        """
        return isinstance(self, GroupMixin)

    def has_preview(self):
        """
        Returns if the document has real merged data. When True, `topil()`
        returns pre-composed data.
        """
        version_info = self.image_resources.get_data(Resource.VERSION_INFO)
        if version_info:
            return version_info.has_composite
        return True  # Assuming the image data is valid by default.

    @property
    def name(self):
        """
        Element name.

        :return: `'Root'`
        """
        return 'Root'

    @property
    def kind(self):
        """
        Kind.

        :return: `'psdimage'`
        """
        return self.__class__.__name__.lower()

    @property
    def visible(self):
        """
        Visibility.

        :return: `True`
        """
        return True

    @property
    def left(self):
        """
        Left coordinate.

        :return: `0`
        """
        return 0

    @property
    def top(self):
        """
        Top coordinate.

        :return: `0`
        """
        return 0

    @property
    def right(self):
        """
        Right coordinate.

        :return: `int`
        """
        return self.width

    @property
    def bottom(self):
        """
        Bottom coordinate.

        :return: `int`
        """
        return self.height

    @property
    def width(self):
        """
        Document width.

        :return: `int`
        """
        return self._record.header.width

    @property
    def height(self):
        """
        Document height.

        :return: `int`
        """
        return self._record.header.height

    @property
    def size(self):
        """
        (width, height) tuple.

        :return: `tuple`
        """
        return self.width, self.height

    @property
    def offset(self):
        """
        (left, top) tuple.

        :return: `tuple`
        """
        return self.left, self.top

    @property
    def bbox(self):
        """
        Minimal bounding box that contains all the visible layers.

        Use :py:attr:`~psd_tools.api.psd_image.PSDImage.viewbox` to get
        viewport bounding box. When the psd is empty, bbox is equal to the
        canvas bounding box.

        :return: (left, top, right, bottom) `tuple`.
        """
        bbox = super(PSDImage, self).bbox
        if bbox == (0, 0, 0, 0):
            bbox = self.viewbox
        return bbox

    @property
    def viewbox(self):
        """
        Return bounding box of the viewport.

        :return: (left, top, right, bottom) `tuple`.
        """
        return self.left, self.top, self.right, self.bottom

    @property
    def color_mode(self):
        """
        Document color mode, such as 'RGB' or 'GRAYSCALE'. See
        :py:class:`~psd_tools.constants.ColorMode`.

        :return: :py:class:`~psd_tools.constants.ColorMode`
        """
        return self._record.header.color_mode

    @property
    def channels(self):
        """
        Number of color channels.

        :return: `int`
        """
        return self._record.header.channels

    @property
    def depth(self):
        """
        Pixel depth bits.

        :return: `int`
        """
        return self._record.header.depth

    @property
    def version(self):
        """
        Document version. PSD file is 1, and PSB file is 2.

        :return: `int`
        """
        return self._record.header.version

    @property
    def image_resources(self):
        """
        Document image resources.
        :py:class:`~psd_tools.psd.image_resources.ImageResources` is a
        dict-like structure that keeps various document settings.

        See :py:class:`psd_tools.constants.Resource` for available keys.

        :return: :py:class:`~psd_tools.psd.image_resources.ImageResources`

        Example::

            from psd_tools.constants import Resource
            version_info = psd.image_resources.get_data(Resource.VERSION_INFO)
            slices = psd.image_resources.get_data(Resource.SLICES)

        Image resources contain an ICC profile. The following shows how to
        export a PNG file with embedded ICC profile::

            from psd_tools.constants import Resource
            icc_profile = psd.image_resources.get_data(Resource.ICC_PROFILE)
            image = psd.compose(apply_icc=False)
            image.save('output.png', icc_profile=icc_profile)
        """
        return self._record.image_resources

    @property
    def tagged_blocks(self):
        """
        Document tagged blocks that is a dict-like container of settings.

        See :py:class:`psd_tools.constants.Tag` for available
        keys.

        :return: :py:class:`~psd_tools.psd.tagged_blocks.TaggedBlocks` or
            `None`.

        Example::

            from psd_tools.constants import Tag
            patterns = psd.tagged_blocks.get_data(Tag.PATTERNS1)
        """
        return self._record.layer_and_mask_information.tagged_blocks

    def has_thumbnail(self):
        """True if the PSDImage has a thumbnail resource."""
        return (
            Resource.THUMBNAIL_RESOURCE in self.image_resources or
            Resource.THUMBNAIL_RESOURCE_PS4 in self.image_resources
        )

    def thumbnail(self):
        """
        Returns a thumbnail image in PIL.Image. When the file does not
        contain an embedded thumbnail image, returns None.
        """
        from .pil_io import convert_thumbnail_to_pil
        if Resource.THUMBNAIL_RESOURCE in self.image_resources:
            return convert_thumbnail_to_pil(
                self.image_resources.get_data(Resource.THUMBNAIL_RESOURCE)
            )
        elif Resource.THUMBNAIL_RESOURCE_PS4 in self.image_resources:
            return convert_thumbnail_to_pil(
                self.image_resources.get_data(Resource.THUMBNAIL_RESOURCE_PS4),
                'BGR'
            )
        return None

    def __repr__(self):
        return ('%s(mode=%s size=%dx%d depth=%d channels=%d)') % (
            self.__class__.__name__,
            self.color_mode,
            self.width,
            self.height,
            self._record.header.depth,
            self._record.header.channels,
        )

    def _repr_pretty_(self, p, cycle):
        if cycle:
            return self.__repr__()

        def _pretty(layer, p):
            p.text(layer.__repr__())
            if hasattr(layer, 'clip_layers'):
                for idx, layer in enumerate(layer.clip_layers or []):
                    p.break_()
                    p.text(' +  ')
                    p.pretty(layer)
            if hasattr(layer, '__iter__'):
                with p.indent(2):
                    for idx, layer in enumerate(layer):
                        p.break_()
                        p.text('[%d] ' % idx)
                        _pretty(layer, p)

        _pretty(self, p)

    @classmethod
    def _make_header(cls, mode, size, depth=8):
        from .pil_io import get_color_mode
        assert depth in (8, 16, 32), 'Invalid depth: %d' % (depth)
        assert size[0] <= 300000, 'Width too large > 300,000'
        assert size[1] <= 300000, 'Height too large > 300,000'
        version = 1
        if size[0] > 30000 or size[1] > 30000:
            logger.debug('Width or height larger than 30,000 pixels')
            version = 2
        color_mode = get_color_mode(mode)
        alpha = int(mode.upper().endswith('A'))
        channels = ColorMode.channels(color_mode, alpha)
        return FileHeader(
            version=version,
            width=size[0],
            height=size[1],
            depth=depth,
            channels=channels,
            color_mode=color_mode
        )

    def _get_pattern(self, pattern_id):
        """Get pattern item by id."""
        for key in (Tag.PATTERNS1, Tag.PATTERNS2, Tag.PATTERNS3):
            if key in self.tagged_blocks:
                data = self.tagged_blocks.get_data(key)
                for pattern in data:
                    if pattern.pattern_id == pattern_id:
                        return pattern
        return None

    def _init(self):
        """Initialize layer structure."""
        group_stack = [self]
        clip_stack = []
        last_layer = None

        for record, channels in self._record._iter_layers():
            current_group = group_stack[-1]

            blocks = record.tagged_blocks
            end_of_group = False
            layer = None
            divider = blocks.get_data(Tag.SECTION_DIVIDER_SETTING, None)
            divider = blocks.get_data(
                Tag.NESTED_SECTION_DIVIDER_SETTING, divider
            )
            if divider is not None:
                if divider.kind == SectionDivider.BOUNDING_SECTION_DIVIDER:
                    layer = Group(self, None, None, current_group)
                    group_stack.append(layer)
                elif divider.kind in (
                    SectionDivider.OPEN_FOLDER, SectionDivider.CLOSED_FOLDER
                ):
                    layer = group_stack.pop()
                    assert layer is not self

                    layer._record = record
                    layer._channels = channels
                    for key in (
                        Tag.ARTBOARD_DATA1, Tag.ARTBOARD_DATA2,
                        Tag.ARTBOARD_DATA3
                    ):
                        if key in blocks:
                            layer = Artboard._move(layer)
                    end_of_group = True
                else:
                    logger.warning('Divider %s found.' % divider.kind)
            elif (
                Tag.TYPE_TOOL_OBJECT_SETTING in blocks or
                Tag.TYPE_TOOL_INFO in blocks
            ):
                layer = TypeLayer(self, record, channels, current_group)
            elif (
                Tag.SMART_OBJECT_LAYER_DATA1 in blocks or
                Tag.SMART_OBJECT_LAYER_DATA2 in blocks or
                Tag.PLACED_LAYER1 in blocks or Tag.PLACED_LAYER2 in blocks
            ):
                layer = SmartObjectLayer(self, record, channels, current_group)
            else:
                for key in adjustments.TYPES.keys():
                    if key in blocks:
                        layer = adjustments.TYPES[key](
                            self, record, channels, current_group
                        )
                        break

            # If nothing applies, this is either a shape or pixel layer.
            shape_condition = record.flags.pixel_data_irrelevant and (
                Tag.VECTOR_ORIGINATION_DATA in blocks or
                Tag.VECTOR_MASK_SETTING1 in blocks or
                Tag.VECTOR_MASK_SETTING2 in blocks or
                Tag.VECTOR_STROKE_DATA in blocks or
                Tag.VECTOR_STROKE_CONTENT_DATA in blocks)
            if isinstance(layer, (type(None), FillLayer)) and shape_condition:
                layer = ShapeLayer(self, record, channels, current_group)

            if layer is None:
                layer = PixelLayer(self, record, channels, current_group)

            assert layer is not None

            if record.clipping == Clipping.NON_BASE:
                clip_stack.append(layer)
            else:
                if clip_stack:
                    last_layer._clip_layers = clip_stack
                clip_stack = []
                if not end_of_group:
                    current_group._layers.append(layer)
                last_layer = layer

        if clip_stack and last_layer:
            last_layer._clip_layers = clip_stack
