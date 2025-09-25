"""
PSD Image module.
"""

import logging
import os
from typing import Any, BinaryIO, Callable, Literal, Optional, Union

try:
    from typing import Self
except ImportError:
    from typing_extensions import Self

import numpy as np
from PIL.Image import Image as PILImage

from psd_tools.api import adjustments
from psd_tools.api.layers import (
    Artboard,
    FillLayer,
    Group,
    GroupMixin,
    PixelLayer,
    ShapeLayer,
    SmartObjectLayer,
    TypeLayer,
)
from psd_tools.api.pil_io import get_pil_channels, get_pil_mode
from psd_tools.constants import (
    ChannelID,
    ColorMode,
    CompatibilityMode,
    Compression,
    Resource,
    SectionDivider,
    Tag,
)
from psd_tools.psd import (
    PSD,
    ChannelImageData,
    FileHeader,
    GlobalLayerMaskInfo,
    ImageData,
    ImageResources,
    LayerInfo,
    LayerRecords,
    TaggedBlocks,
)

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

    def __init__(self, data: PSD):
        from psd_tools.api.layers import Layer

        assert isinstance(data, PSD)
        self._record = data
        self._layers: list[Layer] = []
        self._compatibility_mode = CompatibilityMode.DEFAULT
        self._updated_layers = False  # Flag to check if the layer tree is edited.
        self._init()

    @classmethod
    def new(
        cls,
        mode: str,
        size: tuple[int, int],
        color: int = 0,
        depth: Literal[8, 16, 32] = 8,
        **kwargs: Any,
    ):
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
    def frompil(cls, image: PILImage, compression=Compression.RLE) -> Self:
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

        self._update_record()

        if self._updated_layers:
            composited_psd = self.composite(force=True)
            self._record.image_data.set_data(
                [channel.tobytes() for channel in composited_psd.split()],
                self._record.header,
            )

        if isinstance(fp, (str, bytes, os.PathLike)):
            with open(fp, mode) as f:
                self._record.write(f, **kwargs)
        else:
            self._record.write(fp, **kwargs)

    def topil(
        self, channel: Union[int, ChannelID, None] = None, apply_icc: bool = True
    ) -> Union[PILImage, None]:
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

        self._update_record()

        if self.has_preview():
            return convert_image_data_to_pil(self, channel, apply_icc)
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
        from .numpy_io import get_array

        return get_array(self, channel)

    def composite(
        self,
        viewport: Optional[tuple[int, int, int, int]] = None,
        force: bool = False,
        color: Optional[Union[float, tuple[float, ...]]] = 1.0,
        alpha: float = 0.0,
        layer_filter: Optional[Callable] = None,
        ignore_preview: bool = False,
        apply_icc: bool = True,
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

        self._update_record()

        if (
            not (ignore_preview or force or layer_filter)
            and self.has_preview()
            and not self._updated_layers
        ):
            return self.topil(apply_icc=apply_icc)
        return composite_pil(
            self, color, alpha, viewport, layer_filter, force, apply_icc=apply_icc
        )

    def is_visible(self) -> bool:
        """
        Returns visibility of the element.

        :return: `bool`
        """
        return self.visible

    @property
    def parent(self) -> None:
        """Parent of this layer."""
        return None

    def is_group(self) -> bool:
        """
        Return True if the layer is a group.

        :return: `bool`
        """
        return isinstance(self, GroupMixin)

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

        :return: :py:class:`~psd_tools.constants.CompatibilityMode`
        """
        return self._compatibility_mode

    @compatibility_mode.setter
    def compatibility_mode(self, value: CompatibilityMode) -> None:
        self._compatibility_mode = value

    @property
    def pil_mode(self) -> str:
        alpha = self.channels - get_pil_channels(get_pil_mode(self.color_mode))
        return get_pil_mode(self.color_mode, alpha > 0)

    def has_thumbnail(self) -> bool:
        """True if the PSDImage has a thumbnail resource."""
        return (
            Resource.THUMBNAIL_RESOURCE in self.image_resources
            or Resource.THUMBNAIL_RESOURCE_PS4 in self.image_resources
        )

    def thumbnail(self) -> Optional[PILImage]:
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
                self.image_resources.get_data(Resource.THUMBNAIL_RESOURCE_PS4)
            )
        return None

    def __repr__(self) -> str:
        return ("%s(mode=%s size=%dx%d depth=%d channels=%d)") % (
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
            if isinstance(layer, GroupMixin):
                with p.indent(2):
                    for idx, child in enumerate(layer):
                        p.break_()
                        p.text("[%d] " % idx)
                        if child.clipping_layer:
                            p.text("+")
                        _pretty(child, p)

        _pretty(self, p)

    @classmethod
    def _make_header(
        cls, mode: str, size: tuple[int, int], depth: Literal[8, 16, 32] = 8
    ) -> FileHeader:
        from .pil_io import get_color_mode

        assert depth in (8, 16, 32), "Invalid depth: %d" % (depth)
        assert size[0] <= 300000, "Width too large > 300,000"
        assert size[1] <= 300000, "Height too large > 300,000"
        version = 1
        if size[0] > 30000 or size[1] > 30000:
            logger.debug("Width or height larger than 30,000 pixels")
            version = 2
        color_mode = get_color_mode(mode)
        alpha = int(mode.upper().endswith("A"))
        channels = ColorMode.channels(color_mode, alpha)
        return FileHeader(
            version=version,
            width=size[0],
            height=size[1],
            depth=depth,
            channels=channels,
            color_mode=color_mode,
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

    def _init(self) -> None:
        """Initialize layer structure."""
        from psd_tools.api.layers import Layer

        group_stack: list[Union[Group, Artboard, PSDImage]] = [self]

        for record, channels in self._record._iter_layers():
            current_group = group_stack[-1]

            blocks = record.tagged_blocks
            end_of_group = False
            layer: Union[Layer, Group, Artboard, PSDImage, None] = None
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
                    layer = Group(  # type: ignore
                        psd=self,
                        record=None,  # type: ignore
                        channels=None,  # type: ignore
                        parent=current_group,
                    )
                    layer._set_bounding_records(record, channels)
                    group_stack.append(layer)
                elif divider.kind in (
                    SectionDivider.OPEN_FOLDER,
                    SectionDivider.CLOSED_FOLDER,
                ):
                    layer = group_stack.pop()
                    assert not isinstance(layer, PSDImage)

                    layer._record = record
                    layer._channels = channels
                    for key in (
                        Tag.ARTBOARD_DATA1,
                        Tag.ARTBOARD_DATA2,
                        Tag.ARTBOARD_DATA3,
                    ):
                        if key in blocks:
                            layer = Artboard._move(layer)
                    end_of_group = True
                else:
                    logger.warning("Divider %s found." % divider.kind)
            elif Tag.TYPE_TOOL_OBJECT_SETTING in blocks or Tag.TYPE_TOOL_INFO in blocks:
                layer = TypeLayer(self, record, channels, current_group)
            elif (
                Tag.SMART_OBJECT_LAYER_DATA1 in blocks
                or Tag.SMART_OBJECT_LAYER_DATA2 in blocks
                or Tag.PLACED_LAYER1 in blocks
                or Tag.PLACED_LAYER2 in blocks
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
                Tag.VECTOR_ORIGINATION_DATA in blocks
                or Tag.VECTOR_MASK_SETTING1 in blocks
                or Tag.VECTOR_MASK_SETTING2 in blocks
                or Tag.VECTOR_STROKE_DATA in blocks
                or Tag.VECTOR_STROKE_CONTENT_DATA in blocks
            )
            if isinstance(layer, (type(None), FillLayer)) and shape_condition:
                layer = ShapeLayer(self, record, channels, current_group)

            if layer is None:
                layer = PixelLayer(self, record, channels, current_group)

            assert layer is not None

            if not end_of_group:
                assert not isinstance(layer, PSDImage)
                current_group._layers.append(layer)

    def _update_record(self) -> None:
        """
        Compiles the tree layer structure back into records and channels list recursively
        """

        if not self._updated_layers:
            # Skip if nothing is changed.
            return

        layer_records, channel_image_data = _build_record_tree(self)

        # PSDImage.frompil doesn't create a LayerInfo attribute to LayerAndMaskInformation
        if not self._record.layer_and_mask_information.layer_info:
            self._record.layer_and_mask_information.layer_info = LayerInfo()

        if not self._record.layer_and_mask_information.global_layer_mask_info:
            self._record.layer_and_mask_information.global_layer_mask_info = (
                GlobalLayerMaskInfo()
            )

        if not self._record.layer_and_mask_information.tagged_blocks:
            self._record.layer_and_mask_information.tagged_blocks = TaggedBlocks()

        layer_info = self._record.layer_and_mask_information.layer_info
        layer_info.layer_records = layer_records
        layer_info.channel_image_data = channel_image_data
        layer_info.layer_count = len(layer_records)


def _build_record_tree(
    layer_group: GroupMixin,
) -> tuple[LayerRecords, ChannelImageData]:
    """
    Builds the layer tree structure from records and channels list recursively
    """

    layer_records = LayerRecords()
    channel_image_data = ChannelImageData()

    for layer in layer_group:
        if isinstance(layer, (Group, Artboard)):
            layer_records.append(layer._bounding_record)
            channel_image_data.append(layer._bounding_channels)

            tmp_layer_records, tmp_channel_image_data = _build_record_tree(layer)

            layer_records.extend(tmp_layer_records)
            channel_image_data.extend(tmp_channel_image_data)

        layer_records.append(layer._record)
        channel_image_data.append(layer._channels)

    return (layer_records, channel_image_data)
