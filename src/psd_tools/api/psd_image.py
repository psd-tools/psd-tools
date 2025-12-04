"""
PSD Image module.

This module provides the main :py:class:`PSDImage` class, which is the primary
entry point for users of psd-tools. It represents a complete Photoshop document
and provides high-level methods for reading, manipulating, and saving PSD/PSB files.

The :py:class:`PSDImage` class wraps the low-level :py:class:`~psd_tools.psd.PSD`
structure and reconstructs the layer tree from the flat layer list, making it much
easier to work with layers and groups.

Key functionality:

- **Opening files**: :py:meth:`PSDImage.open` and :py:meth:`PSDImage.new`
- **Layer access**: Iterate, index, and search layers
- **Compositing**: Render layers to PIL Images via :py:meth:`~PSDImage.composite`
- **Saving**: Write modified documents back to PSD format
- **Metadata access**: Document properties, ICC profiles, resolution, etc.

Example usage::

    from psd_tools import PSDImage

    # Open a PSD file
    psd = PSDImage.open('document.psd')

    # Access document properties
    print(f"Size: {psd.width}x{psd.height}")
    print(f"Color mode: {psd.color_mode}")

    # Iterate through layers
    for layer in psd:
        print(f"{layer.name}: {layer.kind}")

    # Access layers by index
    layer = psd[0]  # First layer

    # Modify layers
    layer.visible = False
    layer.opacity = 128

    # Composite to image
    image = psd.composite()
    image.save('output.png')

    # Save changes
    psd.save('modified.psd')

The class inherits from :py:class:`~psd_tools.api.layers.GroupMixin`, providing
group-like behavior for accessing child layers.
"""

import logging
import os
from typing import Any, BinaryIO, Callable, Iterable, Literal, Optional, Union

try:
    from typing import Self  # type: ignore[attr-defined]
except ImportError:
    from typing_extensions import Self

import numpy as np
from PIL import Image

from psd_tools.api import adjustments, layers, numpy_io, pil_io
from psd_tools.api.protocols import PSDProtocol
from psd_tools.constants import (
    BlendMode,
    ChannelID,
    ColorMode,
    CompatibilityMode,
    Compression,
    Resource,
    SectionDivider,
    Tag,
)
from psd_tools.psd.document import PSD
from psd_tools.psd.header import FileHeader
from psd_tools.psd.image_data import ImageData
from psd_tools.psd.image_resources import ImageResources
from psd_tools.psd.layer_and_mask import (
    ChannelImageData,
    GlobalLayerMaskInfo,
    LayerInfo,
    LayerRecords,
)
from psd_tools.psd.patterns import Patterns
from psd_tools.psd.tagged_blocks import TaggedBlocks

logger = logging.getLogger(__name__)


class PSDImage(layers.GroupMixin, PSDProtocol):
    """
    Photoshop PSD/PSB document.

    The low-level data structure is accessible at :py:attr:`PSDImage._record`.

    Example::

        from psd_tools import PSDImage

        psdimage = PSDImage.open('example.psd')
        image = psdimage.composite()

        for layer in psdimage:
            layer_image = layer.composite()
    """

    def __init__(self, data: PSD):
        if not isinstance(data, PSD):
            raise TypeError(f"Expected PSD instance, got {type(data).__name__}")
        self._record = data
        self._layers: list[layers.Layer] = []
        self._compatibility_mode = CompatibilityMode.DEFAULT
        self._updated: bool = False  # Flag to check if the layer tree is edited.

        self._psd = self  # For GroupMixin protocol compatibility.
        self._init()

    @classmethod
    def new(
        cls,
        mode: str,
        size: tuple[int, int],
        color: int = 0,
        depth: Literal[8, 16, 32] = 8,
        **kwargs: Any,
    ) -> Self:
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
    def frompil(
        cls, image: Image.Image, compression: Compression = Compression.RLE
    ) -> Self:
        """
        Create a new layer-less PSD document from PIL Image.

        :param image: PIL Image object.
        :param compression: ImageData compression option. See
            :py:class:`~psd_tools.constants.Compression`.
        :return: A :py:class:`~psd_tools.api.psd_image.PSDImage` object.
        """
        header = cls._make_header(image.mode, image.size)
        # TODO: Add default metadata.
        # TODO: Perhaps make this smart object.
        image_data = ImageData(compression=compression)
        image_data.set_data([channel.tobytes() for channel in image.split()], header)
        return cls(
            PSD(
                header=header,
                image_data=image_data,
                image_resources=ImageResources.new(),
            )
        )

    @classmethod
    def open(cls, fp: Union[BinaryIO, str, bytes, os.PathLike], **kwargs: Any) -> Self:
        """
        Open a PSD document.

        :param fp: filename or file-like object.
        :param encoding: charset encoding of the pascal string within the file,
            default 'macroman'. Some psd files need explicit encoding option.
        :return: A :py:class:`~psd_tools.api.psd_image.PSDImage` object.
        """
        if isinstance(fp, (str, bytes, os.PathLike)):
            with open(fp, "rb") as f:
                self = cls(PSD.read(f, **kwargs))
        else:
            self = cls(PSD.read(fp, **kwargs))
        return self

    def save(
        self,
        fp: Union[BinaryIO, str, bytes, os.PathLike],
        mode: str = "wb",
        **kwargs: Any,
    ) -> None:
        """
        Save the PSD file. Updates the ImageData section if the layer structure has been updated.

        :param fp: filename or file-like object.
        :param encoding: charset encoding of the pascal string within the file,
            default 'macroman'.
        :param mode: file open mode, default 'wb'.
        """
        if self.is_updated():
            # Update the preview image if the layer structure has been changed.
            # TODO: Fill in a white background for the given color mode on failure.
            # TODO: Set a `has_composite` flag in VersionInfo resource.
            try:
                composited_psd = self.composite().convert(self.pil_mode)
                self._record.image_data.set_data(
                    [channel.tobytes() for channel in composited_psd.split()],
                    self._record.header,
                )
            except ImportError as e:
                logger.warning(
                    "Failed to update preview image: %s. "
                    "Install composite dependencies with: pip install 'psd-tools[composite]'",
                    e,
                )

        if isinstance(fp, (str, bytes, os.PathLike)):
            with open(fp, mode) as f:
                self._record.write(f, **kwargs)  # type: ignore[arg-type]
        else:
            self._record.write(fp, **kwargs)  # type: ignore[arg-type]

    def topil(
        self, channel: Union[int, ChannelID, None] = None, apply_icc: bool = True
    ) -> Union[Image.Image, None]:
        """
        Get PIL Image.

        :param channel: Which channel to return; e.g., 0 for 'R' channel in RGB
            image. See :py:class:`~psd_tools.constants.ChannelID`. When `None`,
            the method returns all the channels supported by PIL modes.
        :param apply_icc: Whether to apply ICC profile conversion to sRGB.
        :return: :py:class:`PIL.Image`, or `None` if the composed image is not
            available.
        """
        if self.has_preview():
            return pil_io.convert_image_data_to_pil(self, channel, apply_icc)
        return None

    def numpy(
        self, channel: Optional[Literal["color", "shape", "alpha", "mask"]] = None
    ) -> np.ndarray:
        """
        Get NumPy array of the layer.

        :param channel: Which channel to return, can be 'color',
            'shape', 'alpha', or 'mask'. Default is 'color+alpha'.
        :return: :py:class:`numpy.ndarray`
        """
        array = numpy_io.get_array(self, channel)
        assert array is not None
        return array

    def composite(
        self,
        viewport: Optional[tuple[int, int, int, int]] = None,
        force: bool = False,
        color: Union[float, tuple[float, ...], np.ndarray, None] = 1.0,
        alpha: Union[float, np.ndarray] = 0.0,
        layer_filter: Optional[Callable] = None,
        ignore_preview: bool = False,
        apply_icc: bool = True,
    ) -> Image.Image:
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

        if (
            not (ignore_preview or force or layer_filter)
            and self.has_preview()
            and not self.is_updated()
        ):
            result = self.topil(apply_icc=apply_icc)
            if result is None:
                raise ValueError("Failed to composite PSD image from preview")
            return result
        result = composite_pil(
            self,
            color if color is not None else 1.0,
            alpha,
            viewport,
            layer_filter,
            force,
            apply_icc=apply_icc,
        )
        if result is None:
            raise ValueError("Failed to composite PSD image")
        return result

    def _mark_updated(self) -> None:
        """Mark the layer tree as updated."""
        self._updated = True

    def is_updated(self) -> bool:
        """
        Returns whether the layer tree has been updated.

        :return: `bool`
        """
        return self._updated

    @property
    def parent(self) -> None:
        """Parent of this layer."""
        return None

    def has_preview(self) -> bool:
        """
        Returns if the document has real merged data. When True, `topil()`
        returns pre-composed data.
        """
        version_info = self.image_resources.get_data(Resource.VERSION_INFO)
        if version_info:
            return version_info.has_composite
        return True  # Assuming the image data is valid by default.

    @property
    def name(self) -> str:
        """
        Element name.

        :return: `'Root'`
        """
        return "Root"

    @property
    def kind(self) -> str:
        """
        Kind.

        :return: `'psdimage'`
        """
        return self.__class__.__name__.lower()

    @property
    def visible(self) -> bool:
        """
        Visibility.

        :return: `True`
        """
        return True

    @property
    def left(self) -> int:
        """
        Left coordinate.

        :return: `0`
        """
        return 0

    @property
    def top(self) -> int:
        """
        Top coordinate.

        :return: `0`
        """
        return 0

    @property
    def right(self) -> int:
        """
        Right coordinate.

        :return: `int`
        """
        return self.width

    @property
    def bottom(self) -> int:
        """
        Bottom coordinate.

        :return: `int`
        """
        return self.height

    @property
    def width(self) -> int:
        """
        Document width.

        :return: `int`
        """
        return self._record.header.width

    @property
    def height(self) -> int:
        """
        Document height.

        :return: `int`
        """
        return self._record.header.height

    @property
    def size(self) -> tuple[int, int]:
        """
        (width, height) tuple.

        :return: `tuple`
        """
        return self.width, self.height

    @property
    def offset(self) -> tuple[int, int]:
        """
        (left, top) tuple.

        :return: `tuple`
        """
        return self.left, self.top

    @property
    def bbox(self) -> tuple[int, int, int, int]:
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
    def viewbox(self) -> tuple[int, int, int, int]:
        """
        Return bounding box of the viewport.

        :return: (left, top, right, bottom) `tuple`.
        """
        return self.left, self.top, self.right, self.bottom

    @property
    def color_mode(self) -> ColorMode:
        """
        Document color mode, such as 'RGB' or 'GRAYSCALE'. See
        :py:class:`~psd_tools.constants.ColorMode`.

        :return: :py:class:`~psd_tools.constants.ColorMode`
        """
        return self._record.header.color_mode

    @property
    def channels(self) -> int:
        """
        Number of color channels.

        :return: `int`
        """
        return self._record.header.channels

    @property
    def depth(self) -> int:
        """
        Pixel depth bits.

        :return: `int`
        """
        return self._record.header.depth

    @property
    def version(self) -> int:
        """
        Document version. PSD file is 1, and PSB file is 2.

        :return: `int`
        """
        return self._record.header.version

    @property
    def image_resources(self) -> ImageResources:
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
    def tagged_blocks(self) -> Optional[TaggedBlocks]:
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

    @property
    def compatibility_mode(self) -> CompatibilityMode:
        """
        Set the compositing and layer organization compatibility mode. Writable.

        This property checks whether the PSD file is compatible with
        specific authoring tools, such as Photoshop or CLIP Studio Paint.
        Different authoring tools may have different ways of handling layers,
        such as the use of clipping masks for groups.
        Default is Photoshop compatibility mode.

        :return: :py:class:`~psd_tools.constants.CompatibilityMode`
        """
        return self._compatibility_mode

    @compatibility_mode.setter
    def compatibility_mode(self, value: CompatibilityMode) -> None:
        if self._compatibility_mode != value:
            self._mark_updated()
        self._compatibility_mode = value

    @property
    def pil_mode(self) -> str:
        alpha = self.channels - pil_io.get_pil_channels(
            pil_io.get_pil_mode(self.color_mode)
        )
        # TODO: Check when alpha > 1; Photoshop allows multiple alpha channels.
        return pil_io.get_pil_mode(self.color_mode, alpha > 0)

    def has_thumbnail(self) -> bool:
        """True if the PSDImage has a thumbnail resource."""
        return (
            Resource.THUMBNAIL_RESOURCE in self.image_resources
            or Resource.THUMBNAIL_RESOURCE_PS4 in self.image_resources
        )

    def thumbnail(self) -> Optional[Image.Image]:
        """
        Returns a thumbnail image in PIL.Image. When the file does not
        contain an embedded thumbnail image, returns None.
        """
        if Resource.THUMBNAIL_RESOURCE in self.image_resources:
            return pil_io.convert_thumbnail_to_pil(
                self.image_resources.get_data(Resource.THUMBNAIL_RESOURCE)
            )
        elif Resource.THUMBNAIL_RESOURCE_PS4 in self.image_resources:
            return pil_io.convert_thumbnail_to_pil(
                self.image_resources.get_data(Resource.THUMBNAIL_RESOURCE_PS4)
            )
        return None

    # Editing API
    def create_pixel_layer(
        self,
        image: Image.Image,
        name: str = "Layer",
        top: int = 0,
        left: int = 0,
        compression: Compression = Compression.RLE,
        opacity: int = 255,
        blend_mode: BlendMode = BlendMode.NORMAL,
    ) -> layers.PixelLayer:
        """
        Create a new pixel layer and add it to the PSDImage.

        Example::

            psdimage = PSDImage.new("RGB", (640, 480))
            layer = psdimage.create_pixel_layer(image, name='Layer 1')

        :param name: Name of the new layer.
        :param image: PIL Image object.
        :param top: Top coordinate of the new layer.
        :param left: Left coordinate of the new layer.
        :param compression: Compression method for the layer image data.
        :param opacity: Opacity of the new layer (0-255).
        :param blend_mode: Blend mode of the new layer, default is ``BlendMode.NORMAL``.
        :return: The created :py:class:`~psd_tools.api.layers.PixelLayer` object.
        """
        layer = layers.PixelLayer.frompil(
            image, parent=self, name=name, top=top, left=left, compression=compression
        )
        layer.opacity = opacity
        layer.blend_mode = blend_mode
        self._mark_updated()
        return layer

    def create_group(
        self,
        layer_list: Optional[Iterable[layers.Layer]] = None,
        name: str = "Group",
        opacity: int = 255,
        blend_mode: BlendMode = BlendMode.PASS_THROUGH,
        open_folder: bool = True,
    ) -> layers.Group:
        """
        Create a new group layer and add it to the PSDImage.

        Example::

            group = psdimage.create_group(name='New Group')
            group.append(psdimage.create_pixel_layer(image, name='Layer in Group'))

        :param layer_list: Optional list of layers to add to the group.
        :param name: Name of the new group.
        :param opacity: Opacity of the new layer (0-255).
        :param blend_mode: Blend mode of the new layer, default is ``BlendMode.PASS_THROUGH``.
        :param open_folder: Whether the group is an open folder in the Photoshop UI.
        :return: The created :py:class:`~psd_tools.api.layers.Group` object.
        """
        group = layers.Group.new(parent=self, name=name, open_folder=open_folder)
        if layer_list:
            group.extend(layer_list)
        group.opacity = opacity
        group.blend_mode = blend_mode
        self._mark_updated()
        return group

    # TODO: Add more editing APIs, such as duplicate_layers, resize_canvas, etc.

    # Private methods
    def __repr__(self) -> str:
        return ("%s(mode=%s size=%dx%d depth=%d channels=%d)") % (
            self.__class__.__name__,
            self.color_mode,
            self.width,
            self.height,
            self._record.header.depth,
            self._record.header.channels,
        )

    def _repr_pretty_(self, p: Any, cycle: bool) -> None:
        if cycle:
            p.text(self.__repr__())
            return

        def _pretty(layer: Union[layers.Layer, "PSDImage"], p: Any) -> None:
            p.text(layer.__repr__())
            if isinstance(layer, layers.GroupMixin):
                with p.indent(2):
                    for idx, child in enumerate(layer):
                        p.break_()
                        p.text("[%d] " % idx)
                        if child.clipping:
                            p.text("+")
                        _pretty(child, p)

        _pretty(self, p)

    @classmethod
    def _make_header(
        cls, mode: str, size: tuple[int, int], depth: Literal[8, 16, 32] = 8
    ) -> FileHeader:
        if depth not in (8, 16, 32):
            raise ValueError(f"Invalid depth: {depth}. Must be 8, 16, or 32")
        if size[0] > 300000:
            raise ValueError(f"Width too large: {size[0]} > 300,000")
        if size[1] > 300000:
            raise ValueError(f"Height too large: {size[1]} > 300,000")
        version = 1
        if size[0] > 30000 or size[1] > 30000:
            logger.debug("Width or height larger than 30,000 pixels")
            version = 2
        color_mode = pil_io.get_color_mode(mode)
        alpha = mode.upper().endswith("A")
        channels = ColorMode.channels(color_mode, alpha)
        return FileHeader(
            version=version,
            width=size[0],
            height=size[1],
            depth=depth,
            channels=channels,
            color_mode=color_mode,
        )

    def _get_pattern(self, pattern_id: str) -> Optional[Any]:
        """Get pattern item by id."""
        if self.tagged_blocks is None:
            return None
        for key in (Tag.PATTERNS1, Tag.PATTERNS2, Tag.PATTERNS3):
            if key in self.tagged_blocks:
                data = self.tagged_blocks.get_data(key)
                for pattern in data:
                    if pattern.pattern_id == pattern_id:
                        return pattern
        return None

    def _init(self) -> None:
        """Initialize layer structure."""
        from psd_tools.api import layers

        group_stack: list[Union[layers.Group, PSDImage]] = [self]

        for record, channels in self._record._iter_layers():
            current_group = group_stack[-1]

            blocks = record.tagged_blocks
            end_of_group = False
            layer: Union[layers.Layer, PSDImage, None] = None
            divider = blocks.get_data(Tag.SECTION_DIVIDER_SETTING, None)
            divider = blocks.get_data(Tag.NESTED_SECTION_DIVIDER_SETTING, divider)
            if (
                divider is not None
                and
                # Some PSDs contain dividers with SectionDivider.OTHER.
                # Ignoring them, allows the correct categorization of the layer.
                # Issue : https://github.com/psd-tools/psd-tools/issues/338
                divider.kind is not SectionDivider.OTHER
            ):
                if divider.kind == SectionDivider.BOUNDING_SECTION_DIVIDER:
                    layer = layers.Group(  # type: ignore
                        parent=current_group,
                        # We need to fill in the record and channels later.
                        record=None,  # type: ignore
                        channels=None,  # type: ignore
                    )
                    layer._set_bounding_records(record, channels)
                    group_stack.append(layer)
                elif divider.kind in (
                    SectionDivider.OPEN_FOLDER,
                    SectionDivider.CLOSED_FOLDER,
                ):
                    layer = group_stack.pop()
                    if not isinstance(layer, layers.Group):
                        raise TypeError(
                            f"Expected Group layer, got {type(layer).__name__}"
                        )
                    # Set the record and channels now.
                    layer._record = record
                    layer._channels = channels

                    # If the group is an artboard, convert it.
                    for key in (
                        Tag.ARTBOARD_DATA1,
                        Tag.ARTBOARD_DATA2,
                        Tag.ARTBOARD_DATA3,
                    ):
                        if key in blocks:
                            layer = layers.Artboard._move(layer)
                    end_of_group = True
                else:
                    logger.warning("Divider %s found." % divider.kind)
            elif Tag.TYPE_TOOL_OBJECT_SETTING in blocks or Tag.TYPE_TOOL_INFO in blocks:
                layer = layers.TypeLayer(current_group, record, channels)
            elif (
                Tag.SMART_OBJECT_LAYER_DATA1 in blocks
                or Tag.SMART_OBJECT_LAYER_DATA2 in blocks
                or Tag.PLACED_LAYER1 in blocks
                or Tag.PLACED_LAYER2 in blocks
            ):
                layer = layers.SmartObjectLayer(current_group, record, channels)
            else:
                for key in adjustments.TYPES.keys():
                    if key in blocks:
                        layer = adjustments.TYPES[key](current_group, record, channels)
                        break

            # If nothing applies, this is either a shape or pixel layer.
            shape_condition = record.flags.pixel_data_irrelevant and (
                Tag.VECTOR_ORIGINATION_DATA in blocks
                or Tag.VECTOR_MASK_SETTING1 in blocks
                or Tag.VECTOR_MASK_SETTING2 in blocks
                or Tag.VECTOR_STROKE_DATA in blocks
                or Tag.VECTOR_STROKE_CONTENT_DATA in blocks
            )
            if isinstance(layer, (type(None), layers.FillLayer)) and shape_condition:
                layer = layers.ShapeLayer(current_group, record, channels)

            if layer is None:
                layer = layers.PixelLayer(current_group, record, channels)

            if layer is None:
                raise ValueError("Failed to create layer from record")

            if not end_of_group:
                if isinstance(layer, PSDImage):
                    raise TypeError("Cannot add PSDImage as a layer")
                current_group._layers.append(layer)

    def _update_record(self) -> None:
        """
        Compiles the tree layer structure back into records and channels list
        recursively from the API layer structure.
        """
        # Initialize the layer structure information if not present.
        if self._record.layer_and_mask_information.layer_info is None:
            self._record.layer_and_mask_information.layer_info = LayerInfo()
        if self._record.layer_and_mask_information.global_layer_mask_info is None:
            self._record.layer_and_mask_information.global_layer_mask_info = (
                GlobalLayerMaskInfo()
            )
        if self._record.layer_and_mask_information.tagged_blocks is None:
            self._record.layer_and_mask_information.tagged_blocks = TaggedBlocks()

        # Set layer records and channel image data.
        layer_records, channel_image_data = _build_record_tree(self)
        layer_info = self._record.layer_and_mask_information.layer_info
        layer_info.layer_records = layer_records
        layer_info.channel_image_data = channel_image_data
        layer_info.layer_count = len(layer_records)

        # Flag as updated.
        self._mark_updated()

    def _copy_patterns(self, psdimage: PSDProtocol) -> None:
        """Copy patterns from this psdimage to the target psdimage."""
        if self.tagged_blocks is None:
            # Nothing to copy.
            return

        if psdimage.tagged_blocks is None:
            logger.debug("Creating tagged blocks for psdimage.")
            psdimage._record.layer_and_mask_information.tagged_blocks = TaggedBlocks()
        if psdimage.tagged_blocks is None:
            raise ValueError("Failed to create tagged blocks for psdimage")

        for tag in self.tagged_blocks.keys():
            if not isinstance(tag, Tag):
                raise TypeError(f"Expected Tag instance, got {type(tag).__name__}")
            if tag in (Tag.PATTERNS1, Tag.PATTERNS2, Tag.PATTERNS3):
                logger.debug("Copying patterns for tag %s", tag)
                source_patterns: Patterns = self.tagged_blocks.get_data(tag)
                target_patterns: Patterns = psdimage.tagged_blocks.get_data(tag)
                if target_patterns is None:
                    target_patterns = Patterns()
                    psdimage.tagged_blocks.set_data(tag, target_patterns)

                target_pattern_ids = {p.pattern_id for p in target_patterns}
                for pattern in source_patterns:
                    if pattern.pattern_id not in target_pattern_ids:
                        target_patterns.append(pattern)


def _build_record_tree(
    layer_group: layers.GroupMixin,
) -> tuple[LayerRecords, ChannelImageData]:
    """
    Builds the layer tree structure from records and channels list recursively
    """
    layer_records = LayerRecords()
    channel_image_data = ChannelImageData()

    for layer in layer_group:
        if isinstance(layer, (layers.Group, layers.Artboard)):
            layer_records.append(layer._bounding_record)
            channel_image_data.append(layer._bounding_channels)

            tmp_layer_records, tmp_channel_image_data = _build_record_tree(layer)

            layer_records.extend(tmp_layer_records)
            channel_image_data.extend(tmp_channel_image_data)

        layer_records.append(layer._record)
        channel_image_data.append(layer._channels)

    return (layer_records, channel_image_data)
