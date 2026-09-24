"""
Layer module.

This module implements the high-level layer API for psd-tools, providing
Pythonic interfaces for working with Photoshop layers. It defines the layer
type hierarchy and common operations.

Key classes:

- :py:class:`Layer`: Base class for all layer types
- :py:class:`GroupMixin`: Mixin for layers that contain children (groups, documents)
- :py:class:`Group`: Folder/group layer containing other layers
- :py:class:`PixelLayer`: Regular raster layer with pixel data
- :py:class:`TypeLayer`: Text layer with typography information
- :py:class:`ShapeLayer`: Vector shape layer
- :py:class:`SmartObjectLayer`: Embedded or linked smart object
- :py:class:`AdjustmentLayer`: Non-destructive adjustment (curves, levels, etc.)

Layer hierarchy:

Layers are organized in a tree structure where groups can contain child layers.
The :py:class:`GroupMixin` provides iteration, indexing, and search capabilities::

    # Iterate through all layers
    for layer in psd:
        print(layer.name)

    # Access by index
    first_layer = psd[0]

    # Check if layer is a specific type
    if layer.kind == 'pixel':
        pixels = layer.numpy()

Common layer properties:

- ``name``: Layer name
- ``visible``: Visibility flag
- ``opacity``: Opacity (0-255)
- ``blend_mode``: Blend mode enum
- ``bbox``: Bounding box (left, top, right, bottom)
- ``width``, ``height``: Dimensions
- ``kind``: Layer type string ('pixel', 'group', 'type', etc.)
- ``parent``: Parent layer or document

Layer operations:

- :py:meth:`~Layer.composite`: Render layer to PIL Image
- :py:meth:`~Layer.numpy`: Get pixel data as NumPy array
- :py:meth:`~Layer.topil`: Convert to PIL Image
- :py:meth:`~Layer.has_mask`: Check if layer has a mask
- :py:meth:`~Layer.has_clip_layers`: Check if layer has clipping mask

Example usage::

    from psd_tools import PSDImage

    psd = PSDImage.open('document.psd')

    # Access first layer
    layer = psd[0]

    # Modify layer properties
    layer.visible = False
    layer.opacity = 128
    layer.name = "New Name"

    # Get pixel data
    pixels = layer.numpy()  # NumPy array
    image = layer.topil()   # PIL Image

    # Work with groups
    for group in psd.descendants():
        if group.kind == 'group':
            print(f"Group: {group.name} with {len(group)} layers")

    # Composite specific layer
    rendered = layer.composite()
    rendered.save('layer.png')

Layer types are automatically determined from the underlying PSD structures
and exposed through the ``kind`` property for easy type checking.
"""

import logging
import warnings
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Collection,
    Iterable,
    Iterator,
    Literal,
    Protocol,
    Sequence,
    TypeVar,
    cast,
    runtime_checkable,
)

from typing_extensions import Self

if TYPE_CHECKING:
    from psd_tools.api.typesetting import TypeSetting

import numpy as np
from PIL import Image, ImageChops

import psd_tools.psd.engine_data as engine_data
from psd_tools.api import numpy_io, pil_io
from psd_tools.color_convert import LAB_NEUTRAL_CHROMA, rgb_to_grayscale
from psd_tools.compression import PSDDecompressionWarning
from psd_tools.api.effects import Effects
from psd_tools.api.mask import Mask
from psd_tools.api.protocols import GroupMixinProtocol, LayerProtocol, PSDProtocol
from psd_tools.api.shape import Origination, Stroke, VectorMask
from psd_tools.api.smart_object import SmartObject
from psd_tools.constants import (
    BlendMode,
    ChannelID,
    Clipping,
    ColorMode,
    CompatibilityMode,
    Compression,
    ProtectedFlags,
    SectionDivider,
    SheetColorType,
    Tag,
    TextType,
)
from psd_tools.psd.descriptor import DescriptorBlock
from psd_tools.psd.header import FileHeader
from psd_tools.psd.layer_and_mask import (
    ChannelData,
    ChannelDataList,
    ChannelInfo,
    LayerRecord,
    MaskData,
    MaskFlags,
)
from psd_tools.psd.tagged_blocks import (
    ProtectedSetting,
    SectionDividerSetting,
    TaggedBlocks,
)
from psd_tools.terminology import Key

logger = logging.getLogger(__name__)


TGroupMixin = TypeVar("TGroupMixin", bound="GroupMixin")


def _compression_for(compression: Compression, depth: int) -> Compression:
    """The codec to store a channel with, given the document's *depth*.

    ZIP with prediction delta-encodes whole samples, and a 1-bit channel has
    none: ``encode_prediction()`` raises on it, and ``decompress()`` turns the
    matching read into a black channel and a warning. So a bitmap document
    takes plain ZIP instead of a codec it cannot express. Every other pairing
    of the four codecs with depths 1, 8, 16 and 32 round-trips as asked.

    The choice is recorded in the channel's own ``compression`` field, so a
    reader is told what it was given and nothing has to infer it.
    """
    if depth == 1 and compression == Compression.ZIP_WITH_PREDICTION:
        logger.debug("ZIP with prediction is not defined at depth 1; using ZIP.")
        return Compression.ZIP
    return compression


class Layer(LayerProtocol):
    def __init__(
        self,
        parent: "GroupMixin",
        record: LayerRecord,
        channels: ChannelDataList,
    ):
        self._psd = parent._psd
        self._parent: "GroupMixinProtocol | None" = parent
        self._record = record
        self._channels = channels

    @property
    def name(self) -> str:
        """
        Layer name. Writable.

        :return: `str`
        """
        return self._record.tagged_blocks.get_data(
            Tag.UNICODE_LAYER_NAME, self._record.name
        )

    @name.setter
    def name(self, value: str) -> None:
        if len(value) >= 256:
            raise ValueError(
                "Layer name too long (%d characters, max 255): %s" % (len(value), value)
            )
        try:
            value.encode("macroman")
            self._record.name = value
        except UnicodeEncodeError:
            self._record.name = str("?")
        self._record.tagged_blocks.set_data(Tag.UNICODE_LAYER_NAME, value)

    @property
    def kind(self) -> str:
        """
        Kind of this layer.

        One of group, pixel, shape, type, smartobject, or psdimage -- the
        class name without its `layer` suffix.

        :return: `str`
        """
        return self.__class__.__name__.lower().replace("layer", "")

    @property
    def layer_id(self) -> int:
        """
        Layer ID.

        :return: int layer id. if the layer is not assigned an id, -1.
        """
        return self.tagged_blocks.get_data(Tag.LAYER_ID, -1)

    def _invalidate_bbox(self) -> None:
        """
        Invalidate this layer's _bbox and any parents recursively to the root.
        """
        if isinstance(self, (GroupMixin, ShapeLayer)):
            self._bbox: tuple[int, int, int, int] | None = None
        # Every parent is a container that caches a box of its own, and the
        # document is one of them: naming ``Group`` and ``Artboard`` here
        # stopped the walk one level short of
        # :py:class:`~psd_tools.api.psd_image.PSDImage`, which is a
        # ``GroupMixin`` but not a ``Layer``, and left the document's box stale
        # after a top-level child changed (#814).
        parent = self.parent
        if parent is not None:
            parent._invalidate_bbox()

    @property
    def visible(self) -> bool:
        """
        Layer visibility. Doesn't take group visibility in account. Writable.

        :return: `bool`
        """
        return self._record.flags.visible

    @visible.setter
    def visible(self, value: bool) -> None:
        value = bool(value)
        if self.visible == value:
            return
        if self._psd is not None:
            self._psd.mark_updated()
        self._record.flags.visible = value
        # Up: every ancestor's union gains or loses this layer.
        self._invalidate_bbox()
        # Down: ``Group.extract_bbox()`` filters children through
        # ``is_visible()``, which walks *up* the parent chain, so this flag is
        # an input to the box of every container *beneath* this layer as well.
        # Those are the boxes nothing used to drop (#819). ``Group`` rather
        # than ``GroupMixin``: the latter is a ``runtime_checkable`` protocol
        # whose ``isinstance`` runs ``hasattr(x, "bbox")`` on Python <= 3.11,
        # recomputing this subtree's boxes a line before the walk drops them.
        # The answer is the same either way; the concrete check skips the work.
        if isinstance(self, Group):
            self._invalidate_subtree_bbox()

    def is_visible(self) -> bool:
        """
        Layer visibility. Takes group visibility in account.

        :return: `bool`
        """
        if not self.visible:
            return False
        elif self.parent is not None:
            return self.parent.is_visible()
        return True

    @property
    def opacity(self) -> int:
        """
        Opacity of this layer in [0, 255] range. Writable.

        :return: int
        """
        return self._record.opacity

    @opacity.setter
    def opacity(self, value: int) -> None:
        if not (0 <= value <= 255):
            raise ValueError(f"Opacity must be in range [0, 255], got {value}")
        if self.opacity != value and self._psd is not None:
            self._psd.mark_updated()
        self._record.opacity = int(value)

    @property
    def parent(self) -> GroupMixinProtocol | None:
        """Parent of this layer."""
        return self._parent  # type: ignore

    def next_sibling(self, visible: bool = False) -> Self | None:
        """Next sibling of this layer."""
        if self.parent is None:
            return None
        index = self.parent.index(self)  # type: ignore
        for i in range(index + 1, len(self.parent)):
            if not visible or self.parent[i].visible:
                return self.parent[i]  # type: ignore[return-value]
        return None

    def previous_sibling(self, visible: bool = False) -> Self | None:
        """Previous sibling of this layer."""
        if self.parent is None:
            return None
        index = self.parent.index(self)  # type: ignore
        for i in range(index - 1, -1, -1):
            if not visible or self.parent[i].visible:
                return self.parent[i]  # type: ignore[return-value]
        return None

    def is_group(self) -> bool:
        """
        Return True if the layer is a group.

        :return: `bool`
        """
        return False

    @property
    def blend_mode(self) -> BlendMode:
        """
        Blend mode of this layer. Writable.

        Example::

            from psd_tools.constants import BlendMode
            if layer.blend_mode == BlendMode.NORMAL:
                layer.blend_mode = BlendMode.SCREEN

        :return: :py:class:`~psd_tools.constants.BlendMode`.
        """
        return self._record.blend_mode

    @blend_mode.setter
    def blend_mode(self, value: bytes | str | BlendMode) -> None:
        if isinstance(value, str):
            value = value.encode("ascii")
        blend_mode = BlendMode(value)
        if self.blend_mode != blend_mode:
            self._psd.mark_updated()
        self._record.blend_mode = blend_mode

    @property
    def left(self) -> int:
        """
        Left coordinate. Writable.

        :return: int
        """
        return self._record.left

    @left.setter
    def left(self, value: int) -> None:
        if self.left != value:
            self._psd.mark_updated()
        self._invalidate_bbox()
        w = self.width
        self._record.left = int(value)
        self._record.right = int(value) + w

    @property
    def top(self) -> int:
        """
        Top coordinate. Writable.

        :return: int
        """
        return self._record.top

    @top.setter
    def top(self, value: int) -> None:
        if self.top != value and self._psd is not None:
            self._psd.mark_updated()
        self._invalidate_bbox()
        h = self.height
        self._record.top = int(value)
        self._record.bottom = int(value) + h

    @property
    def right(self) -> int:
        """
        Right coordinate.

        :return: int
        """
        return self._record.right

    @property
    def bottom(self) -> int:
        """
        Bottom coordinate.

        :return: int
        """
        return self._record.bottom

    @property
    def width(self) -> int:
        """
        Width of the layer.

        :return: int
        """
        return self.right - self.left

    @property
    def height(self) -> int:
        """
        Height of the layer.

        :return: int
        """
        return self.bottom - self.top

    @property
    def offset(self) -> tuple[int, int]:
        """
        (left, top) tuple. Writable.

        :return: `tuple`
        """
        return self.left, self.top

    @offset.setter
    def offset(self, value: tuple[int, int]) -> None:
        if len(value) != 2:
            raise ValueError(
                f"Offset must be a tuple of 2 integers, got {len(value)} elements"
            )
        self.left, self.top = tuple(int(x) for x in value)

    @property
    def size(self) -> tuple[int, int]:
        """
        (width, height) tuple.

        :return: `tuple`
        """
        return self.width, self.height

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """(left, top, right, bottom) tuple."""
        return self.left, self.top, self.right, self.bottom

    def has_pixels(self) -> bool:
        """
        Whether the layer has associated pixels.

        When True, the `topil` method returns :py:class:`PIL.Image.Image`.

        :return: `bool`
        """
        return any(
            ci.id >= 0 and cd.data and len(cd.data) > 0
            for ci, cd in zip(self._record.channel_info, self._channels)
        )

    def has_mask(self) -> bool:
        """
        Returns True if the layer has a mask.

        :return: `bool`
        """
        return self._record.mask_data is not None

    @property
    def mask(self) -> Mask | None:
        """
        Returns mask associated with this layer.

        :return: :py:class:`~psd_tools.api.mask.Mask` or `None`
        """
        if not hasattr(self, "_mask"):
            self._mask = Mask(self) if self.has_mask() else None
        return self._mask

    def _make_mask_channel_data(
        self,
        image: Image.Image,
        compression: Compression,
    ) -> tuple[ChannelData, int, int]:
        """Return ``(channel_data, width, height)`` for a mask image.

        If the image has an alpha channel the alpha channel is used as the
        mask data; otherwise the image is converted to grayscale (``L`` mode).

        A mask is stored at the **document's** depth, as every other channel
        is: 24 of the corpus's masks are 16-bit and two are 32-bit, and
        :py:func:`~psd_tools.api.numpy_io.get_layer_data` reads a mask channel
        at ``layer._psd.depth`` like any other. Writing one at a fixed 8 bits
        gave a 16-bit document half the rows it asked for (#867).
        """
        if "A" in image.getbands():
            mask_pixels = image.getchannel("A")
        else:
            mask_pixels = image.convert("L")

        width, height = mask_pixels.size
        header = self._psd._record.header
        depth = cast(Literal[1, 8, 16, 32], header.depth)

        channel_data = ChannelData(_compression_for(compression, depth))
        channel_data.set_data(
            pil_io.encode_channel(mask_pixels, depth),
            width,
            height,
            depth,
            header.version,
        )
        return channel_data, width, height

    def _channel_geometry(self, channel_id: int) -> tuple[int, int] | None:
        """The ``(width, height)`` a stored channel was compressed against.

        A mask channel carries its own rectangle, and the user mask's is not
        the real mask's. :py:attr:`Mask.width` cannot answer for both: it
        reports the real rectangle whenever one exists.

        ``None`` where the rectangle is missing -- a mask channel with no mask
        block, or a real-mask channel whose ``real_*`` bounds are unset, both
        of which the format permits and neither of which can be decompressed.
        """
        if channel_id not in (
            ChannelID.USER_LAYER_MASK,
            ChannelID.REAL_USER_LAYER_MASK,
        ):
            return self.width, self.height
        mask = self._record.mask_data
        if mask is None:
            return None
        if channel_id == ChannelID.USER_LAYER_MASK:
            return mask.right - mask.left, mask.bottom - mask.top
        left, top = mask.real_left, mask.real_top
        right, bottom = mask.real_right, mask.real_bottom
        if left is None or top is None or right is None or bottom is None:
            return None
        return right - left, bottom - top

    def _reencode_channels(self, source: FileHeader, dest: FileHeader) -> None:
        """Repack every stored channel from *source*'s packing into *dest*'s.

        Depth and file version are the two things about a document that decide
        how a channel's bytes are laid out without changing what they mean:
        depth sets the bytes per sample, and version sets the width of the
        row-length words an RLE channel is prefixed with. A layer moved into a
        document that differs in either carries bytes the destination's reader
        cannot make sense of -- it reads half the rows it asked for, or reads
        the row table as data -- so the channels are unpacked at the source's
        numbers and packed again at the destination's.

        The record is left alone. That is the point: the values are unchanged,
        only their packing moves, so nothing about the layer other than its
        channel data has to be rebuilt.

        A channel that cannot be read is left exactly as it stands rather than
        rewritten from what the codec returned. The codec has two ways of
        failing and only one of them raises: the other *succeeds*, with black,
        which is why the read promotes
        :py:class:`~psd_tools.compression.PSDDecompressionWarning` to an error.
        Repacking a black-filled channel would turn an unreadable channel into
        a readable wrong one, and a move is the wrong place to do either.

        ``catch_warnings()`` is process-global and not thread-safe; for the
        length of the read another thread's decode warning is an error too.
        The scope is one statement, as it is in
        :py:func:`~psd_tools.api.numpy_io._stored_planes`.
        """
        for info, data in zip(self._record.channel_info, self._channels):
            if len(data.data) == 0:
                continue
            geometry = self._channel_geometry(info.id)
            if geometry is None:
                continue
            width, height = geometry
            if width <= 0 or height <= 0:
                continue
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", PSDDecompressionWarning)
                    raw = data.get_data(width, height, source.depth, source.version)
                plane = numpy_io._parse_array(
                    raw, cast(Literal[1, 8, 16, 32], source.depth), width
                )
                encoded = numpy_io._encode_array(
                    plane, cast(Literal[1, 8, 16, 32], dest.depth), width
                )
            except (ValueError, PSDDecompressionWarning) as e:
                logger.warning(
                    "Channel %s could not be re-encoded for depth %d; "
                    "leaving it as stored: %s",
                    info.id,
                    dest.depth,
                    e,
                )
                continue
            data.compression = _compression_for(data.compression, dest.depth)
            data.set_data(encoded, width, height, dest.depth, dest.version)
            info.length = data._length

    def create_mask(
        self,
        image: Image.Image,
        top: int | None = None,
        left: int | None = None,
        compression: Compression = Compression.RLE,
    ) -> Mask:
        """
        Create a pixel mask on this layer from a PIL Image.

        If the image has an alpha channel (e.g. RGBA, LA), the alpha channel
        is used as the mask data. Otherwise the image is converted to
        grayscale (``L`` mode). White (255) means fully unmasked, black (0)
        means fully masked.

        :param image: Source :py:class:`~PIL.Image.Image` for the mask.
        :param top: Top offset of the mask. Defaults to the layer's top.
        :param left: Left offset of the mask. Defaults to the layer's left.
        :param compression: Compression algorithm for the mask data.
        :return: The new :py:class:`~psd_tools.api.mask.Mask`.
        :raises ValueError: If the layer already has a mask.
        """
        if self.has_mask():
            raise ValueError("Layer already has a mask. Remove it first.")

        if top is None:
            top = self._record.top
        if left is None:
            left = self._record.left

        channel_data, width, height = self._make_mask_channel_data(image, compression)

        mask_data = MaskData(
            top=top,
            left=left,
            bottom=top + height,
            right=left + width,
            background_color=0,
            flags=MaskFlags(),
        )

        channel_info = ChannelInfo(
            id=ChannelID.USER_LAYER_MASK,
            length=channel_data._length,
        )

        self._record.mask_data = mask_data
        self._record.channel_info.append(channel_info)
        self._channels.append(channel_data)

        if hasattr(self, "_mask"):
            del self._mask
        self._psd.mark_updated()
        return self.mask  # type: ignore[return-value]

    def remove_mask(self) -> None:
        """
        Remove the pixel mask from this layer.

        :raises ValueError: If the layer does not have a mask.
        """
        if not self.has_mask():
            raise ValueError("Layer does not have a mask.")

        for i, ci in enumerate(self._record.channel_info):
            if ci.id == ChannelID.USER_LAYER_MASK:
                self._record.channel_info.pop(i)
                self._channels.pop(i)
                break

        self._record.mask_data = None

        if hasattr(self, "_mask"):
            del self._mask
        self._psd.mark_updated()

    def update_mask(
        self,
        image: Image.Image,
        top: int | None = None,
        left: int | None = None,
        compression: Compression = Compression.RLE,
    ) -> Mask:
        """
        Update the pixel mask of this layer with a new image.

        If the image has an alpha channel (e.g. RGBA, LA), the alpha channel
        is used as the mask data. Otherwise the image is converted to
        grayscale (``L`` mode). White (255) means fully unmasked, black (0)
        means fully masked.

        :param image: New source :py:class:`~PIL.Image.Image` for the mask.
        :param top: New top offset of the mask. Defaults to current mask top.
        :param left: New left offset of the mask. Defaults to current mask left.
        :param compression: Compression algorithm for the mask data.
        :return: The updated :py:class:`~psd_tools.api.mask.Mask`.
        :raises ValueError: If the layer does not have a mask.
        """
        if not self.has_mask():
            raise ValueError("Layer does not have a mask. Use create_mask() first.")

        channel_data, width, height = self._make_mask_channel_data(image, compression)

        mask_data = cast(MaskData, self._record.mask_data)
        new_top = top if top is not None else mask_data.top
        new_left = left if left is not None else mask_data.left
        mask_data.top = new_top
        mask_data.left = new_left
        mask_data.bottom = new_top + height
        mask_data.right = new_left + width

        for i, ci in enumerate(self._record.channel_info):
            if ci.id == ChannelID.USER_LAYER_MASK:
                self._channels[i] = channel_data
                self._record.channel_info[i].length = channel_data._length
                break

        if hasattr(self, "_mask"):
            del self._mask
        self._psd.mark_updated()
        return self.mask  # type: ignore[return-value]

    def has_vector_mask(self) -> bool:
        """
        Returns True if the layer has a vector mask.

        :return: `bool`
        """
        return any(
            key in self.tagged_blocks
            for key in (Tag.VECTOR_MASK_SETTING1, Tag.VECTOR_MASK_SETTING2)
        )

    @property
    def vector_mask(self) -> VectorMask | None:
        """
        Returns vector mask associated with this layer.

        :return: :py:class:`~psd_tools.api.shape.VectorMask` or `None`
        """
        if not hasattr(self, "_vector_mask"):
            self._vector_mask = None
            blocks = self.tagged_blocks
            for key in (Tag.VECTOR_MASK_SETTING1, Tag.VECTOR_MASK_SETTING2):
                if key in blocks:
                    self._vector_mask = VectorMask(blocks.get_data(key))
                    break
        return self._vector_mask

    def has_origination(self) -> bool:
        """
        Returns True if the layer has live shape properties.

        :return: `bool`
        """
        if self.origination:
            return True
        return False

    @property
    def origination(self) -> list[Origination]:
        """
        Property for a list of live shapes or a line.

        Some of the vector masks have associated live shape properties, that
        are Photoshop feature to handle primitive shapes such as a rectangle,
        an ellipse, or a line. Vector masks without live shape properties are
        plain path objects.

        See :py:mod:`psd_tools.api.shape`.

        :return: List of :py:class:`~psd_tools.api.shape.Invalidated`,
            :py:class:`~psd_tools.api.shape.Rectangle`,
            :py:class:`~psd_tools.api.shape.RoundedRectangle`,
            :py:class:`~psd_tools.api.shape.Ellipse`, or
            :py:class:`~psd_tools.api.shape.Line`.
        """
        if not hasattr(self, "_origination"):
            data = self.tagged_blocks.get_data(Tag.VECTOR_ORIGINATION_DATA, {})
            self._origination: list[Origination] = [
                Origination.create(x)
                for x in data.get(b"keyDescriptorList", [])
                if not data.get(b"keyShapeInvalidated")
            ]
        return self._origination

    def has_stroke(self) -> bool:
        """Returns True if the shape has a stroke."""
        return Tag.VECTOR_STROKE_DATA in self.tagged_blocks

    @property
    def stroke(self) -> Stroke | None:
        """Property for strokes."""
        if not hasattr(self, "_stroke"):
            self._stroke = None
            stroke = self.tagged_blocks.get_data(Tag.VECTOR_STROKE_DATA)
            if stroke:
                self._stroke = Stroke(stroke)
        return self._stroke

    def lock(self, lock_flags: int = ProtectedFlags.COMPLETE) -> None:
        """
        Locks a layer accordind to the combination of flags.

        :param lockflags: An integer representing the locking state

        Example using the constants of ProtectedFlags and bitwise or operation
        to lock both pixels and positions::

            layer.lock(ProtectedFlags.COMPOSITE | ProtectedFlags.POSITION)
        """
        locks = self.locks

        if locks is None:
            locks = ProtectedSetting(0)
            self.tagged_blocks.set_data(Tag.PROTECTED_SETTING, locks)

        locks.lock(lock_flags)

    def unlock(self) -> None:
        self.lock(0)

    @property
    def locks(self) -> ProtectedSetting | None:
        protected_settings_block = self.tagged_blocks.get(Tag.PROTECTED_SETTING)

        if protected_settings_block is not None:
            return protected_settings_block.data

        return None

    def topil(
        self, channel: int | None = None, apply_icc: bool = True
    ) -> Image.Image | None:
        """
        Get PIL Image of the layer.

        :param channel: Which channel to return; e.g., 0 for 'R' channel in RGB
            image. See :py:class:`~psd_tools.constants.ChannelID`. When `None`,
            the method returns all the channels supported by PIL modes.
        :param apply_icc: Whether to apply ICC profile conversion to sRGB.
        :return: :py:class:`PIL.Image.Image`, or `None` if the layer has no pixels.

        Example::

            from psd_tools.constants import ChannelID

            image = layer.topil()
            red = layer.topil(ChannelID.CHANNEL_0)
            alpha = layer.topil(ChannelID.TRANSPARENCY_MASK)

        .. note:: Not all of the PSD image modes are supported in
            :py:class:`PIL.Image.Image`. For example, 'CMYK' mode cannot include
            alpha channel in PIL. In this case, topil drops alpha channel.
        """
        return pil_io.convert_layer_to_pil(self, channel, apply_icc)

    def numpy(
        self, channel: str | None = None, real_mask: bool = True
    ) -> np.ndarray | None:
        """
        Get NumPy array of the layer.

        :param channel: Which channel to return, can be 'color',
            'shape', 'alpha', or 'mask'. Default is 'color+alpha'.
        :return: :py:class:`numpy.ndarray` or None if there is no pixel.
        """
        return numpy_io.get_array(self, channel, real_mask=real_mask)

    def composite(
        self,
        viewport: tuple[int, int, int, int] | None = None,
        force: bool = False,
        color: float | Sequence[float] | np.ndarray = 1.0,
        alpha: float | np.ndarray = 0.0,
        layer_filter: Callable | None = None,
        apply_icc: bool = True,
    ) -> Image.Image | None:
        """
        Composite layer and masks (mask, vector mask, and clipping layers).

        :param viewport: Viewport bounding box specified by (x1, y1, x2, y2)
            tuple. Default is the layer's bbox.
        :param force: Boolean flag to force vector drawing.
        :param color: Backdrop color, as a scalar, a per-channel sequence, or a
            full ``(height, width, channels)`` array.
            The color value should be in [0.0, 1.0]. For example, (1., 0., 0.)
            specifies red in RGB color mode.
        :param alpha: Backdrop alpha in [0.0, 1.0].
        :param layer_filter: Callable that takes a layer as argument and
            returns whether if the layer is composited. Default is
            :py:func:`~psd_tools.api.layers.PixelLayer.is_visible`.
        :return: :py:class:`PIL.Image.Image` or `None`.
        """
        from psd_tools.composite import composite_pil  # noqa: PLC0415

        if self._psd is not None and self._psd.is_updated():
            force = True

        return composite_pil(
            self, color, alpha, viewport, layer_filter, force, apply_icc=apply_icc
        )

    def has_clip_layers(self, visible: bool = False) -> bool:
        """
        Returns True if the layer has associated clipping.

        :param visible: If True, check for visible clipping layers.
        :return: `bool`
        """
        if visible:
            return any(layer.is_visible() for layer in self.clip_layers)
        return len(self.clip_layers) > 0

    @property
    def clip_layers(self) -> list[Self]:
        """
        Clip layers associated with this layer.

        :return: list of layers
        """
        if self.clipping:
            return []

        # Look for clipping layers in the parent scope.
        parent: GroupMixin = self.parent or self._psd  # type: ignore
        index = parent.index(self)

        # TODO: Cache the result and invalidate when needed.
        _clip_layers = []
        for layer in parent[index + 1 :]:  # type: ignore
            if layer.clipping:
                if (
                    isinstance(layer, GroupMixin)
                    and layer._psd.compatibility_mode == CompatibilityMode.PHOTOSHOP
                ):
                    # In Photoshop, clipping groups are not supported.
                    break
                _clip_layers.append(layer)
            else:
                break

        return _clip_layers

    @property
    def clipping(self) -> bool:
        """
        Clipping flag for this layer. Writable.

        :return: `bool`
        """
        return self._record.clipping == Clipping.NON_BASE

    @clipping.setter
    def clipping(self, value: bool) -> None:
        clipping = Clipping.NON_BASE if value else Clipping.BASE
        if self._record.clipping != clipping and self._psd is not None:
            self._psd.mark_updated()
        self._record.clipping = clipping
        self._invalidate_bbox()

    @property
    def clipping_layer(self) -> bool:
        """Deprecated. Use clipping property instead."""
        logger.warning(
            "clipping_layer property is deprecated. Use clipping property instead."
        )
        return self.clipping

    @clipping_layer.setter
    def clipping_layer(self, value: bool) -> None:
        """Deprecated. Use clipping property instead."""
        logger.warning(
            "clipping_layer property is deprecated. Use clipping property instead."
        )
        self.clipping = value

    def has_effects(self, enabled: bool = True, name: str | None = None) -> bool:
        """
        Returns True if the layer has effects.

        Existence is what the Photoshop UI lists: an effect with an entry in
        the layer's fx list. Whether it is switched on is separate -- the UI
        greys out a disabled entry, and the master switch greys out the whole
        list at once. So the two arms ask two questions: ``has_effects()`` is
        "does this layer draw any effect?", which needs the master switch on
        and an entry enabled under it, and ``has_effects(enabled=False)`` is
        "does the fx list show anything?", the same answer as
        ``len(layer.effects) > 0``.

        Neither is "does the layer carry an effects tagged block". Photoshop
        creates that block with the first effect attached and leaves it behind
        once the last is removed, so it outlives what it lists; ask
        :py:attr:`~psd_tools.api.layers.Layer.tagged_blocks` for it, as
        :py:class:`~psd_tools.api.effects.Effects` documents (#318, #830).

        :param enabled: If True, check for enabled effects.
        :param name: If given, check for specific effect type.
        :return: `bool`
        """
        effects = self.effects
        if name is not None:
            # ``find()`` applies the master switch itself.
            return any(effects.find(name, enabled))
        if enabled:
            return effects.enabled and any(effect.enabled for effect in effects)
        return len(effects) > 0

    @property
    def effects(self) -> Effects:
        """
        Layer effects.

        A live view: the proxy re-reads the layer's effects block on every
        access, so an edit made underneath shows through without it having to
        be discarded first. It holds no state worth memoising -- building one
        costs a fraction of listing the effects once.

        :return: :py:class:`~psd_tools.api.effects.Effects`
        """
        return Effects(self)

    @property
    def tagged_blocks(self) -> TaggedBlocks:
        """
        Layer tagged blocks that is a dict-like container of settings.

        See :py:class:`psd_tools.constants.Tag` for available
        keys.

        :return: :py:class:`~psd_tools.psd.tagged_blocks.TaggedBlocks`.

        Example::

            from psd_tools.constants import Tag
            metadata = layer.tagged_blocks.get_data(Tag.METADATA_SETTING)
        """
        return self._record.tagged_blocks

    @property
    def fill_opacity(self) -> int:
        """
        Fill opacity of this layer in [0, 255] range. Writable.

        :return: int
        """
        return self.tagged_blocks.get_data(Tag.BLEND_FILL_OPACITY, 255)

    @fill_opacity.setter
    def fill_opacity(self, value: int) -> None:
        if value < 0 or value > 255:
            raise ValueError("Fill opacity must be between 0 and 255.")
        if self.fill_opacity != value and self._psd is not None:
            self._psd.mark_updated()
        self.tagged_blocks.set_data(Tag.BLEND_FILL_OPACITY, int(value))

    @property
    def reference_point(self) -> tuple[float, float]:
        """
        Reference point of this layer as (x, y) tuple in the canvas coordinates. Writable.

        Reference point is used for transformations such as rotation and scaling.

        :return: (x, y) tuple
        """
        return tuple(self.tagged_blocks.get_data(Tag.REFERENCE_POINT, (0.0, 0.0)))

    @reference_point.setter
    def reference_point(self, value: Sequence[float]) -> None:
        if len(value) != 2:
            raise ValueError("Reference point must be a sequence of two floats.")
        if self.reference_point != value and self._psd is not None:
            self._psd.mark_updated()
        self.tagged_blocks.set_data(
            Tag.REFERENCE_POINT, [float(value[0]), float(value[1])]
        )

    @property
    def sheet_color(self) -> SheetColorType:
        """
        Color label of this layer in the Photoshop layers panel. Writable.

        :return: :py:class:`~psd_tools.constants.SheetColorType`
        """
        return self.tagged_blocks.get_data(
            Tag.SHEET_COLOR_SETTING, SheetColorType.NO_COLOR
        )

    @sheet_color.setter
    def sheet_color(self, value: SheetColorType) -> None:
        value = SheetColorType(value)
        if self.sheet_color != value and self._psd is not None:
            self._psd.mark_updated()
        self.tagged_blocks.set_data(Tag.SHEET_COLOR_SETTING, value)

    def _annotate(self, describe: Callable[[], str]) -> str:
        """One optional part of :py:meth:`__repr__`, dropped if it will not read.

        ``except Exception``, and not the narrow tuple
        :py:mod:`psd_tools.composite.composite` guards its descriptor reads
        with: that one is narrow because its caller goes on to *draw*, so an
        exception outside the set is a bug worth surfacing rather than wrong
        pixels worth hiding. A repr draws nothing, and nothing that calls one
        -- ``print()``, pdb, a logging handler, pytest -- asked what this
        reads. Sharing that tuple would also mean reaching into the rendering
        subpackage from a repr (#828).
        """
        try:
            return describe()
        except Exception as error:
            logger.debug(
                "%s() raised for a %s: %s",
                describe.__name__,
                type(self).__name__,
                error,
            )
            return ""

    def _repr_size(self) -> str:
        has_size = self.width > 0 and self.height > 0
        return " size=%dx%d" % (self.width, self.height) if has_size else ""

    def _repr_effects(self) -> str:
        return " effects" if self.has_effects() else ""

    def __repr__(self) -> str:
        # ``size`` and ``effects`` go through ``_annotate()`` because they are
        # the two parts that read beyond the record's own fields: ``bbox`` is
        # overridden to walk a group's children, to read an artboard's tagged
        # block -- which raises outright when it is absent -- to read a
        # shape's origination, and on a ``FillLayer`` to raise without a
        # document; ``has_effects()`` parses the effects descriptor. ``name``,
        # ``visible``, ``clipping`` and ``has_mask()`` read already-parsed
        # record fields, so guarding them would guard nothing --
        # ``Group.clipping`` being the one that reads further, for the
        # document's compatibility mode, which is set before a group exists.
        return "%s(%r%s%s%s%s%s)" % (
            self.__class__.__name__,
            self.name,
            self._annotate(self._repr_size),
            " invisible" if not self.visible else "",
            " clip" if self.clipping else "",
            " mask" if self.has_mask() else "",
            self._annotate(self._repr_effects),
        )

    # Structure operations
    def delete_layer(self) -> Self:
        """
        Deprecated: Use layer.parent.remove(layer) instead.
        """
        if self.parent is not None and isinstance(self.parent, GroupMixin):
            self.parent.remove(self)
        return self

    def move_to_group(self, group: "GroupMixin") -> Self:
        """
        Deprecated: Use group.append(layer) instead.

        :param group: The group the current layer will be moved into.
        """
        group.append(self)
        return self

    def move_up(self, offset: int = 1) -> Self:
        """
        Moves the layer up a certain offset within the group the layer is in.

        :param offset: The number of positions to move the layer up (can be negative).
        :raises ValueError: If layer has no parent or parent is not a group
        :raises IndexError: If the new index is out of bounds
        :return: self
        """
        if self.parent is None:
            raise ValueError(f"Cannot move layer {self} without a parent")
        if not isinstance(self.parent, GroupMixin):
            raise TypeError(
                f"Parent must be a GroupMixin, got {type(self.parent).__name__}"
            )

        newindex = self.parent.index(self) + offset
        if newindex < 0:
            raise IndexError("Cannot move layer beyond the bottom of the group")
        elif newindex >= len(self.parent):
            raise IndexError("Cannot move layer beyond the top of the group")
        parent = self.parent
        parent.remove(self)
        parent.insert(newindex, self)
        return self

    def move_down(self, offset: int = 1) -> Self:
        """
        Moves the layer down a certain offset within the group the layer is in.

        :param offset: The number of positions to move the layer down (can be negative).
        :raises ValueError: If layer has no parent or parent is not a group
        :raises IndexError: If the new index is out of bounds
        :return: self
        """
        return self.move_up(-1 * offset)


def _invalidate_moved_bbox(layer: Layer) -> None:
    """Drop the cached boxes ``layer`` carries now that something above it changed.

    That is either a new parent or an ancestor whose ``visible`` flag moved;
    see ``GroupMixin._invalidate_subtree_bbox()`` for which boxes those
    are and why. ``Group`` and ``ShapeLayer`` are named concretely rather than
    going through ``GroupMixin``, whose ``runtime_checkable`` protocol check
    would recompute the boxes this is about to drop on Python <= 3.11. That
    costs work rather than correctness -- the walk clears whatever the check
    armed.
    """
    if isinstance(layer, Group):
        layer._invalidate_subtree_bbox()
    elif isinstance(layer, ShapeLayer):
        layer._bbox = None


@runtime_checkable
class GroupMixin(GroupMixinProtocol, Protocol):
    """
    Container behaviour shared by groups and documents.

    :py:class:`Group` and :py:class:`~psd_tools.api.psd_image.PSDImage` both
    hold an ordered list of child layers, and this mixin supplies what
    operates on it: iteration and indexing, the mutation methods below, the
    :py:meth:`descendants` walk, and a :py:attr:`bbox` computed from the
    visible, non-clipping children.

    A layer belongs to exactly one container, so adding one that already has
    a parent moves it out of that parent rather than copying it; see
    :py:meth:`extend`.
    """

    _psd: PSDProtocol
    _bbox: tuple[int, int, int, int] | None = None
    _layers: list[Layer]

    # Note: left, top, right, bottom properties are inherited from Layer
    # and computed via bbox. Groups compute bbox from children, not from _record.

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """(left, top, right, bottom) tuple computed from visible, non-clipping children."""
        if self._bbox is None:
            self._bbox = Group.extract_bbox(self)
        return self._bbox

    def _invalidate_bbox(self) -> None:
        """Drop this container's cached bbox, and every cached box above it.

        ``GroupMixin`` precedes :py:class:`Layer` in ``Group``'s MRO, so this
        is what a group invalidates through. It differs from
        :py:meth:`Layer._invalidate_bbox` only in being available on
        :py:class:`~psd_tools.api.psd_image.PSDImage`, which caches a box here
        too but is not a ``Layer``; the walk stops there, since the document
        has no parent.
        """
        self._bbox = None
        parent = self.parent
        if parent is not None:
            parent._invalidate_bbox()

    def _invalidate_subtree_bbox(self) -> None:
        """Drop this container's cached bbox, and every cached box *beneath* it.

        The downward twin of :py:meth:`_invalidate_bbox`, for a layer whose
        ancestors change rather than its contents. Two cached boxes read
        something above the layer that holds them, so the whole subtree is
        invalidated, not just its root:

        - a group's, because :py:meth:`Group.extract_bbox` filters children
          through ``is_visible()``, which walks up the parent chain;
        - a vector-mask-only shape's, because it scales the mask's normalized
          bounds by ``self._psd.width`` and ``height``, and a cross-document
          move repoints ``_psd`` at a canvas of a different size.

        Two callers reach different halves of that: reparenting or detaching
        can do both, while hiding or showing a group (#819) only ever does the
        first, since it leaves ``_psd`` alone.

        An ordinary layer's box is its record's own offsets, which nothing
        above it can change, so those are left alone.
        """
        self._bbox = None
        for child in self._layers:
            _invalidate_moved_bbox(child)

    def __len__(self) -> int:
        return self._layers.__len__()

    def __iter__(self) -> Iterator[Layer]:
        return self._layers.__iter__()

    def __reversed__(self) -> Iterator[Layer]:
        return self._layers.__reversed__()

    def __contains__(self, item: object) -> bool:
        return item in self._layers

    def __getitem__(self, key: int) -> Layer:
        return self._layers.__getitem__(key)

    def __setitem__(self, key: int, value: Layer) -> None:
        """
        Replace the layer at the specified index with the given layer.

        This operation rewrites the internal references of the layer. If the
        given layer is already in this group, it is moved next to where the
        replaced layer was and the group shrinks by one, following the
        no-duplicates rule of ``extend()``. Its final index is
        one lower than the given one when it came from before the replaced
        layer, because taking it out shifts the rest of the group down.

        :param key: The index of the layer to replace.
        :param value: The layer to put at that index.
        :raises IndexError: If the index is out of range.
        :raises TypeError: If the key is not an index, or the provided object
            is not a Layer instance.
        :raises ValueError: If attempting to add a group to itself.
        """
        if isinstance(key, slice):
            raise TypeError("Slice assignment is not supported")
        target = self._layers[key]
        if target is value:
            return
        index = key if key >= 0 else key + len(self._layers)
        self.insert(index, value)
        self.remove(target)

    def __delitem__(self, key: int) -> None:
        """
        Remove the layer at the specified index from the group.

        This operation rewrites the internal references of the layer.

        :param key: The index of the layer to remove.
        :raises IndexError: If the index is out of range.
        :raises TypeError: If the key is not an index.
        """
        if isinstance(key, slice):
            raise TypeError("Slice deletion is not supported")
        self.remove(self._layers[key])

    def append(self, layer: Layer) -> None:
        """
        Add a layer to the end (top) of the group.

        This operation rewrites the internal references of the layer.
        Adding the same layer will not create a duplicate; it moves to the end
        instead. See ``extend()``, which this delegates to.

        :param layer: The layer to add.
        :raises TypeError: If the provided object is not a Layer instance.
        :raises ValueError: If attempting to add a group to itself.
        """
        self.extend([layer])

    def extend(self, layers: Iterable[Layer]) -> None:
        """
        Add layers to the end (top) of the group.

        This operation rewrites the internal references of the layers.
        Adding the same layer will not create a duplicate: a layer named more
        than once in one call, or already in this group, ends up once, at the
        position of its last mention. That is where a loop of ``append()``
        calls leaves it.

        The iterable is walked once, so a one-shot one is accepted -- a
        generator, or a live container being emptied into this group::

            dest.extend(src)  # Moves every layer of src into dest.

        :param layers: The layers to add.
        :raises TypeError: If the provided object is not a Layer instance.
        :raises ValueError: If attempting to add a group to itself.
        """
        # Materialized before anything walks it. Everything below iterates
        # ``layers`` again, so a one-shot iterable reached the detach loop
        # already empty and nothing was added, and a live container was
        # mutated *while* being iterated: ``dest.extend(src)`` dropped every
        # other layer of ``src``, and ``g.extend(g)`` never terminated (#820).
        pending = list(layers)
        # Keep each layer's *last* mention, which is where a loop of
        # ``append()`` calls leaves it, since a layer already in this group is
        # detached below and re-added at the end. Deliberately not
        # ``dict.fromkeys(pending)``, which looks equivalent but keeps the
        # first. Safe ahead of ``_check_insertion()``, and spares it a repeat
        # of its per-group ``descendants()`` walk, because every dropped
        # element is the same object as one that is kept.
        if len(pending) > 1:
            last = {id(layer): index for index, layer in enumerate(pending)}
            pending = [
                layer for index, layer in enumerate(pending) if last[id(layer)] == index
            ]
        self._check_insertion(pending)
        # Remove parent's reference to the layers.
        donors: list[GroupMixin] = []
        seen: set[int] = set()
        donor_psds: dict[int, PSDProtocol] = {}
        for layer in pending:
            # NOTE: New or removed layers may not be in the parent container.
            if isinstance(layer.parent, GroupMixin) and layer in layer.parent:
                donor = layer.parent
                donor._layers.remove(layer)  # Skip checks for performance
                # Collected rather than invalidated here: on Python <= 3.11 the
                # ``isinstance`` above is a ``runtime_checkable`` protocol check
                # that executes ``bbox``, so clearing a donor inside the loop
                # only makes the next iteration recompute it -- quadratic on
                # ``create_group(list(psd))`` (#814).
                if id(donor) not in seen:
                    seen.add(id(donor))
                    donors.append(donor)
                    # Read here, not off ``donors`` afterwards:
                    # ``_update_children()`` below repoints a moved layer's
                    # ``_psd``, and a donor group that is itself one of
                    # ``pending`` would by then name the receiving document.
                    if donor._psd is not self._psd:
                        donor_psds.setdefault(id(donor._psd), donor._psd)
        self._layers.extend(pending)
        self._update_children()
        self._psd._update_record()
        # The donor document keeps its own flat record list, and ``save()``
        # writes that list without rebuilding it, so a cross-document move that
        # only rebuilt the receiving document wrote the layer into both files
        # (#841). Rebuilding also marks the donor updated, which is what tells
        # its ``save()`` to regenerate a preview that no longer has the layer.
        for donor_psd in donor_psds.values():
            donor_psd._update_record()
        # Last only because by then the tree is consistent and a caller that
        # reads a box next recomputes it once. ``_update_record()`` reads no
        # bounding box, so any point after ``_update_children()`` would do.
        for donor in donors:
            donor._invalidate_bbox()
        for layer in pending:
            _invalidate_moved_bbox(layer)
        self._invalidate_bbox()

    def insert(self, index: int, layer: Layer) -> None:
        """
        Insert the given layer at the specified index.

        This operation rewrites the internal references of the layer. A layer
        already in this group is moved rather than copied, following the
        no-duplicates rule of ``extend()``, so the index it lands at is one
        lower than the given one when it came from before that position.

        :param index: The index to insert the layer at.
        :param layer: The layer to insert.
        :raises TypeError: If the provided object is not a Layer instance.
        :raises ValueError: If attempting to add a group to itself.
        """
        self._check_insertion([layer])
        # Remove parent's reference to the layer.
        donor: GroupMixin | None = None
        donor_psd: PSDProtocol | None = None
        if isinstance(layer.parent, GroupMixin) and layer in layer.parent:
            donor = layer.parent
            donor._layers.remove(layer)  # Skip checks for performance
            if donor._psd is not self._psd:
                donor_psd = donor._psd
        self._layers.insert(index, layer)
        self._update_children()
        self._psd._update_record()
        # See ``extend()``: the donor document's record list is stale until it
        # is rebuilt too, and ``save()`` never rebuilds it (#841).
        if donor_psd is not None:
            donor_psd._update_record()
        if donor is not None:
            donor._invalidate_bbox()
        _invalidate_moved_bbox(layer)
        self._invalidate_bbox()

    def remove(self, layer: Layer) -> Self:
        """
        Removes the specified layer from the group.

        This operation rewrites the internal references of the layer.

        :param layer: The layer to remove.
        :raises ValueError: If the layer is not found in the group.
        :return: self
        """
        if layer not in self:
            raise ValueError(f"Layer {layer} not found in group {self}")
        self._layers.remove(layer)
        layer._parent = None
        self._psd._update_record()
        _invalidate_moved_bbox(layer)
        self._invalidate_bbox()
        return self

    def pop(self, index: int = -1) -> Layer:
        """
        Removes the specified layer from the list and returns it.

        This operation rewrites the internal references of the layer.

        :param index: The index of the layer to remove. Default is -1 (the last layer).
        :raises IndexError: If the index is out of range.
        :return: The removed layer.
        """
        layer = self[index]
        self.remove(layer)
        return layer

    def clear(self) -> None:
        """
        Clears the group.

        This operation rewrites the internal references of the layers.

        :return: None
        """
        detached = list(self._layers)
        for layer in detached:
            layer._parent = None
        self._layers.clear()
        self._psd._update_record()
        for layer in detached:
            _invalidate_moved_bbox(layer)
        self._invalidate_bbox()

    def index(self, layer: Layer) -> int:
        """
        Returns the index of the specified layer in the group.

        :param layer: The layer to find.
        """
        return self._layers.index(layer)

    def count(self, layer: Layer) -> int:
        """
        Counts the number of occurrences of a layer in the group.

        :param layer: The layer to count.
        """
        return self._layers.count(layer)

    def _check_insertion(self, layers: Collection[Layer]) -> None:
        """Check that the given layers can be added to this group.

        ``Collection``, not ``Iterable``: this walks its argument, so a caller
        that walks it again afterwards -- ``extend()`` does -- must not hand it
        a one-shot iterable for this to drain (#820). A re-iterable container,
        a ``Group`` included, is fine, which is why this is not ``Sequence``.

        :raises ValueError: If attempting to add a group to itself or create a reference loop
        :raises TypeError: If the provided object is not a Layer instance
        """
        for layer in layers:
            if not isinstance(layer, Layer):
                raise TypeError(f"Expected Layer instance, got {type(layer).__name__}")
            if layer is self:
                raise ValueError(f"Cannot add the group {self} to itself")
            if isinstance(layer, GroupMixin):
                if self in list(layer.descendants()):
                    raise ValueError(
                        "This operation would create a reference loop "
                        f"within the group between {self} and {layer}"
                    )

    def _update_children(self) -> None:
        """Update children's _psd and _parent references."""
        for layer in self:
            # Update PSD reference if needed
            if layer._psd != self._psd:
                if isinstance(layer, PixelLayer):
                    layer._convert_mode(self)
                layer._psd._copy_patterns(self._psd)  # TODO: optimize
                layer._psd = self._psd
            # Update parent reference
            layer._parent = self
            if isinstance(layer, GroupMixin):
                layer._update_children()

    def is_visible(self) -> bool:
        """Returns visibility of the element."""
        return Layer.is_visible(self)  # type: ignore

    def is_group(self) -> bool:
        """Return True if this is a group."""
        return True

    def descendants(self, include_clip: bool = True) -> Iterator[Layer]:
        """
        Return a generator to iterate over all descendant layers.

        :param include_clip: Whether to include clipping layers. Default is True.

        Example::

            # Iterate over all layers
            for layer in psd.descendants():
                print(layer)

            # Iterate over all layers in reverse order
            for layer in reversed(list(psd.descendants())):
                print(layer)
        """
        for layer in self:
            if not include_clip and hasattr(layer, "clipping") and layer.clipping:
                continue
            yield layer
            if isinstance(layer, GroupMixin):
                yield from layer.descendants(include_clip=include_clip)

    def find(self, name: str) -> Layer | None:
        """
        Return the first layer found for the given layer name.

        :param name:
        """
        for layer in self.findall(name):
            return layer
        return None

    def findall(self, name: str) -> Iterator[Layer]:
        """
        Return a generator to iterate over all layers with the given name.

        :param name:
        """
        for layer in self.descendants():
            if layer.name == name:
                yield layer


class Group(GroupMixin, Layer):
    """
    Group of layers.

    Example::

        group = psd[1]
        for layer in group:
            if layer.kind == 'pixel':
                print(layer.name)
    """

    def __init__(
        self,
        parent: GroupMixin,
        record: LayerRecord,
        channels: ChannelDataList,
    ):
        self._layers = []
        self._bounding_record: LayerRecord | None = None
        self._bounding_channels: ChannelDataList | None = None
        Layer.__init__(self, parent, record, channels)

    @property
    def _setting(self) -> SectionDividerSetting | None:
        """Low-level section divider setting."""
        # Can be None.
        return self.tagged_blocks.get_data(Tag.SECTION_DIVIDER_SETTING)

    @property
    def blend_mode(self) -> BlendMode:
        """Blend mode of this layer. Writable."""
        setting = self._setting
        # Use the blend mode from the section divider setting if present.
        if setting is not None and setting.blend_mode is not None:
            return setting.blend_mode
        return super(Group, self).blend_mode

    @blend_mode.setter
    def blend_mode(self, value: str | bytes | BlendMode) -> None:
        _value = BlendMode(value.encode("ascii") if isinstance(value, str) else value)
        if self.blend_mode != _value and self._psd is not None:
            self._psd.mark_updated()
        if _value == BlendMode.PASS_THROUGH:
            self._record.blend_mode = BlendMode.NORMAL
        else:
            self._record.blend_mode = _value
        setting = self._setting
        if setting is not None:
            setting.blend_mode = _value

    # Override Layer's writable position properties with read-only computed ones
    @property
    def left(self) -> int:
        """Left coordinate (computed from children, read-only)."""
        return self.bbox[0]

    @left.setter
    def left(self, value: int) -> None:
        raise NotImplementedError(
            "Cannot set position on Group directly. Position is computed from children."
        )

    @property
    def top(self) -> int:
        """Top coordinate (computed from children, read-only)."""
        return self.bbox[1]

    @top.setter
    def top(self, value: int) -> None:
        raise NotImplementedError(
            "Cannot set position on Group directly. Position is computed from children."
        )

    @property
    def right(self) -> int:
        """Right coordinate (computed from children, read-only)."""
        return self.bbox[2]

    @property
    def bottom(self) -> int:
        """Bottom coordinate (computed from children, read-only)."""
        return self.bbox[3]

    @property
    def clipping(self) -> bool:
        """
        Clipping flag for this layer. Writable.

        :return: `bool`
        """
        if self._psd.compatibility_mode == CompatibilityMode.PHOTOSHOP:
            # In Photoshop, clipping groups are not supported.
            return False
        return self._record.clipping == Clipping.NON_BASE

    @clipping.setter
    def clipping(self, value: bool) -> None:
        if self._psd.compatibility_mode == CompatibilityMode.PHOTOSHOP:
            logger.warning(
                "Cannot set clipping flag on groups in Photoshop compatibility mode."
            )
            return
        clipping = Clipping.NON_BASE if value else Clipping.BASE
        if self._record.clipping != clipping:
            self._psd.mark_updated()
        self._record.clipping = clipping
        self._invalidate_bbox()

    @property
    def open_folder(self) -> bool:
        """
        Returns True if the group is an open folder.

        :return: `bool`
        """
        if self._setting is None:
            raise ValueError("Section divider setting is missing.")
        return self._setting.kind == SectionDivider.OPEN_FOLDER

    @open_folder.setter
    def open_folder(self, value: bool) -> None:
        """
        Sets whether the group is an open folder.

        :param value: `bool`
        """
        if self._setting is None:
            raise ValueError("Section divider setting is missing.")
        kind = SectionDivider.OPEN_FOLDER if value else SectionDivider.CLOSED_FOLDER
        current_kind = self._setting.kind
        if current_kind != kind:
            self._setting.kind = kind
            # This change does not affect pixel data, so no need to mark PSD as updated.

    def is_group(self) -> bool:
        """
        Return True if the layer is a group.

        :return: `bool`
        """
        return True

    def composite(
        self,
        viewport: tuple[int, int, int, int] | None = None,
        force: bool = False,
        color: float | Sequence[float] | np.ndarray = 1.0,
        alpha: float | np.ndarray = 0.0,
        layer_filter: Callable | None = None,
        apply_icc: bool = True,
    ) -> Image.Image | None:
        """
        Composite layer and masks (mask, vector mask, and clipping layers).

        :param viewport: Viewport bounding box specified by (x1, y1, x2, y2)
            tuple. Default is the layer's bbox.
        :param force: Boolean flag to force vector drawing.
        :param color: Backdrop color, as a scalar, a per-channel sequence, or a
            full ``(height, width, channels)`` array.
            The color value should be in [0.0, 1.0]. For example, (1., 0., 0.)
            specifies red in RGB color mode.
        :param alpha: Backdrop alpha in [0.0, 1.0].
        :param layer_filter: Callable that takes a layer as argument and
            returns whether if the layer is composited. Default is
            :py:func:`~psd_tools.api.layers.PixelLayer.is_visible`.
        :return: :py:class:`PIL.Image.Image`.
        """
        from psd_tools.composite import composite_pil  # noqa: PLC0415

        return composite_pil(
            self,
            color,
            alpha,
            viewport,
            layer_filter,
            force,
            as_layer=True,
            apply_icc=apply_icc,
        )

    @staticmethod
    def extract_bbox(
        layers: Sequence[Layer] | GroupMixin,
        include_invisible: bool = False,
        include_clipping: bool = False,
    ) -> tuple[int, int, int, int]:
        """
        Return a bounding box for ``layers``.

        Gives (0, 0, 0, 0) if the layers have no bounding box.

        :param layers: sequence of layers or a group.
        :param include_invisible: include invisible layers in calculation.
        :param include_clipping: include clipping layers in calculation.
            Defaults to False to match visible pixel bounds.
        :return: tuple of four int
        """

        def _get_bbox(layer: Layer, **kwargs: Any) -> tuple[int, int, int, int]:
            if layer.is_group() and isinstance(layer, GroupMixin):
                return Group.extract_bbox(layer, **kwargs)
            else:
                return layer.bbox

        bboxes = [
            _get_bbox(
                layer,
                include_invisible=include_invisible,
                include_clipping=include_clipping,
            )
            for layer in layers
            if (include_invisible or layer.is_visible())
            and (include_clipping or not layer.clipping)
        ]
        bboxes = [bbox for bbox in bboxes if bbox != (0, 0, 0, 0)]
        if len(bboxes) == 0:  # Empty bounding box.
            logger.info("No bounding box could be extracted from the given layers.")
            return (0, 0, 0, 0)
        lefts, tops, rights, bottoms = zip(*bboxes)
        return (min(lefts), min(tops), max(rights), max(bottoms))

    def _set_bounding_records(
        self, _bounding_record: LayerRecord, _bounding_channels: ChannelDataList
    ) -> None:
        # Attributes that store the record for the folder divider.
        # Used when updating the record so that we don't need to recompute
        # Them from the ending layer
        self._bounding_record = _bounding_record
        self._bounding_channels = _bounding_channels
        return

    @classmethod
    def new(
        cls,
        parent: GroupMixin,
        name: str = "Group",
        open_folder: bool = True,
    ) -> Self:
        """
        Create a new Group object.

        Builds the minimal records, data channels and metadata needed to
        include the group in the PSD file.

        :param name: The display name of the group. Default to "Group".
        :param open_folder: Boolean defining whether the folder will be open or closed
            in photoshop. Default to True.
        :param parent: Optional parent folder to move the newly created group into.

        :return: A :py:class:`~psd_tools.api.layers.Group` object
        :raises ValueError: If parent is None
        """
        if parent is None:
            raise ValueError("Parent cannot be None")

        # Create the layer record for the group.
        record = LayerRecord(top=0, left=0, bottom=0, right=0, name=name)
        record.tagged_blocks = TaggedBlocks()
        kind = (
            SectionDivider.OPEN_FOLDER if open_folder else SectionDivider.CLOSED_FOLDER
        )
        record.tagged_blocks.set_data(Tag.SECTION_DIVIDER_SETTING, kind=kind)
        record.tagged_blocks.set_data(Tag.UNICODE_LAYER_NAME, name)
        # TODO: Check the number of channels needed
        record.channel_info = [ChannelInfo(id=i - 1, length=2) for i in range(4)]

        # Create the bounding layer record.
        bounding_record = LayerRecord(
            top=0, left=0, bottom=0, right=0, name="</Layer group>"
        )
        bounding_record.tagged_blocks = TaggedBlocks()
        bounding_record.tagged_blocks.set_data(
            Tag.SECTION_DIVIDER_SETTING, SectionDivider.BOUNDING_SECTION_DIVIDER
        )
        bounding_record.tagged_blocks.set_data(Tag.UNICODE_LAYER_NAME, "</Layer group>")
        bounding_record.channel_info = [
            ChannelInfo(id=i - 1, length=2) for i in range(4)
        ]

        channels = ChannelDataList()
        for _ in range(4):  # TODO: Check the number of channels needed
            channels.append(ChannelData(compression=Compression.RAW, data=b""))
        bounding_channels = channels

        group = cls(parent, record, channels)
        group._set_bounding_records(bounding_record, bounding_channels)
        parent.append(group)
        return group

    @classmethod
    def group_layers(
        cls,
        parent: GroupMixin,
        layers: Sequence[Layer],
        name: str = "Group",
        open_folder: bool = True,
    ) -> Self:
        """
        Deprecated: Use ``psdimage.create_group(layer_list, name)`` instead.

        :param parent: The parent group to add the newly created Group object into.
        :param layers: The layers to group. Can by any subclass of
            :py:class:`~psd_tools.api.layers.Layer`
        :param name: The display name of the group. Default to "Group".
        :param open_folder: Boolean defining whether the folder will be open or closed in
            photoshop. Default to True.

        :return: A :py:class:`~psd_tools.api.layers.Group`
        :raises ValueError: If layers is empty
        """
        if len(layers) == 0:
            raise ValueError("Cannot create a group from an empty list of layers")
        group = cls.new(parent, name, open_folder)
        group.extend(layers)
        return group


class Artboard(Group):
    """
    Artboard is a special kind of group that has a pre-defined viewbox.
    """

    @classmethod
    def _move(kls, group: Group) -> "Artboard":
        """Converts a Group into an Artboard, updating all references as needed.

        :raises ValueError: If group has no parent
        """
        if group.parent is None:
            raise ValueError("Cannot convert a group without a parent to an Artboard")
        self = kls(group.parent, group._record, group._channels)  # type: ignore
        self._layers = group._layers
        if group._bounding_record is not None and group._bounding_channels is not None:
            self._set_bounding_records(group._bounding_record, group._bounding_channels)
        for layer in self._layers:
            layer._parent = self
        if self.parent is None:
            raise ValueError("Artboard parent is None after conversion")
        for index in range(len(self.parent)):
            if group == self.parent[index]:
                if not isinstance(self.parent, GroupMixin):
                    raise TypeError(
                        f"Parent must be GroupMixin, got {type(self.parent).__name__}"
                    )
                self.parent._layers[index] = self
        return self

    def composite(
        self,
        viewport: tuple[int, int, int, int] | None = None,
        force: bool = False,
        color: float | Sequence[float] | np.ndarray | None = None,
        alpha: float | np.ndarray | None = None,
        layer_filter: Callable | None = None,
        apply_icc: bool = True,
    ) -> Image.Image | None:
        """
        Composite layer, automatically applying the artboard's background color.

        When either ``color`` or ``alpha`` is not explicitly provided, reads
        the artboard background from the ARTBOARD_DATA tagged block
        (``artboardBackgroundType`` and ``Clr`` descriptor) and uses the
        missing value or values as the compositing backdrop.
        """
        if color is None or alpha is None:
            artboard_color, artboard_alpha = self._artboard_background_defaults()
            if color is None:
                color = artboard_color
            if alpha is None:
                alpha = artboard_alpha
        # NOTE: The lower-level psd_tools.composite.composite(artboard) function
        # does not inject artboard background.
        return super().composite(
            viewport=viewport,
            force=force,
            color=color,
            alpha=alpha,
            layer_filter=layer_filter,
            apply_icc=apply_icc,
        )

    def _artboard_background_defaults(
        self,
    ) -> tuple[float | tuple[float, ...], float]:
        """Return (color, alpha) based on artboard background settings.

        Reads artboardBackgroundType from ARTBOARD_DATA1/2/3 tagged blocks
        (last one found wins, matching the bbox() iteration pattern).

        Background types (Photoshop scripting convention):
          1 = Transparent, 2 = White, 3 = Black, 4 = Custom color

        Falls back to (1.0, 0.0) — the Group default — on any missing or
        unsupported data.
        """
        data = None
        for key in (Tag.ARTBOARD_DATA1, Tag.ARTBOARD_DATA2, Tag.ARTBOARD_DATA3):
            if key in self.tagged_blocks:
                data = self.tagged_blocks.get_data(key)

        if data is None:
            return 1.0, 0.0

        bg_type = data.get(b"artboardBackgroundType")
        if bg_type is None:
            return 1.0, 0.0

        psd = self._psd
        color_mode = psd.color_mode if psd is not None else ColorMode.RGB

        bg_type = int(bg_type)
        if bg_type == 1:  # Transparent
            return 1.0, 0.0
        elif bg_type in (2, 3):  # White or Black — color-mode aware
            white = bg_type == 2
            if color_mode in (
                ColorMode.RGB,
                ColorMode.GRAYSCALE,
                ColorMode.BITMAP,
                ColorMode.DUOTONE,
            ):
                return (1.0 if white else 0.0), 1.0
            elif color_mode == ColorMode.LAB:
                # LAB: L in [0,1]; a and b are offset-encoded, so neutral is
                # 128/255 rather than 0.5 -- 0.5 truncates to byte 127 on the
                # way out where Photoshop writes 128 (#743).
                return (
                    (1.0 if white else 0.0, LAB_NEUTRAL_CHROMA, LAB_NEUTRAL_CHROMA),
                    1.0,
                )
            elif color_mode == ColorMode.CMYK:
                # CMYK arrays store what is left rather than what is laid down,
                # so 1.0 is no ink: white is (1,1,1,1) and black is full key,
                # (1,1,1,0). Writing the ink-space spelling here put a white
                # artboard background on a CMYK document at solid black (#747).
                return ((1.0, 1.0, 1.0, 1.0) if white else (1.0, 1.0, 1.0, 0.0)), 1.0
            else:
                logger.debug(
                    "Artboard background color not applied: unsupported color mode %s",
                    color_mode,
                )
                return 1.0, 0.0
        elif bg_type == 4:  # Custom color (Clr descriptor, RGB 0-255)
            clr = data.get(Key.Color)
            if clr is None:
                return 1.0, 0.0
            rd = clr.get(Key.Red)
            gn = clr.get(Key.Green)
            bl = clr.get(Key.Blue)
            if rd is None or gn is None or bl is None:
                return 1.0, 0.0
            r, g, b_val = float(rd) / 255.0, float(gn) / 255.0, float(bl) / 255.0
            if color_mode == ColorMode.RGB:
                return (r, g, b_val), 1.0
            elif color_mode in (
                ColorMode.GRAYSCALE,
                ColorMode.BITMAP,
                ColorMode.DUOTONE,
            ):
                lum = rgb_to_grayscale(r, g, b_val)
                return lum, 1.0
            else:
                # NOTE: The Clr descriptor is always RGB regardless of document
                # color mode. Conversion to CMYK, LAB, etc. is non-trivial and
                # not implemented; those modes fall back to the transparent default.
                logger.debug(
                    "Artboard background color not applied: unsupported color mode %s",
                    color_mode,
                )
                return 1.0, 0.0

        return 1.0, 0.0  # Unknown background type

    @property
    def left(self) -> int:
        return self.bbox[0]

    @left.setter
    def left(self, value: int) -> None:
        raise NotImplementedError("Artboard left position is not writable yet.")

    @property
    def top(self) -> int:
        return self.bbox[1]

    @top.setter
    def top(self, value: int) -> None:
        raise NotImplementedError("Artboard top position is not writable yet.")

    @property
    def right(self) -> int:
        return self.bbox[2]

    @property
    def bottom(self) -> int:
        return self.bbox[3]

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """(left, top, right, bottom) tuple."""
        if self._bbox is None:
            data = None
            for key in (Tag.ARTBOARD_DATA1, Tag.ARTBOARD_DATA2, Tag.ARTBOARD_DATA3):
                if key in self.tagged_blocks:
                    data = self.tagged_blocks.get_data(key)
            if data is None:
                raise ValueError("Artboard data not found in tagged blocks")
            rect = data.get(b"artboardRect")
            self._bbox = (
                int(rect.get(b"Left")),
                int(rect.get(b"Top ")),
                int(rect.get(b"Rght")),
                int(rect.get(b"Btom")),
            )
        return self._bbox


class PixelLayer(Layer):
    """
    Layer that has rasterized image in pixels.

    Example::

        assert layer.kind == 'pixel':
        image = layer.composite()
        image.save('layer.png')
    """

    @classmethod
    def frompil(
        cls,
        image: Image.Image,
        parent: GroupMixin,
        name: str = "Layer",
        top: int = 0,
        left: int = 0,
        compression: Compression = Compression.RLE,
        **kwargs: Any,
    ) -> "PixelLayer":
        """
        Create a PixelLayer from a PIL image for a given psd file.

        :param image: The :py:class:`~PIL.Image.Image` object to convert to photoshop
        :param parent: The parent group or PSDImage this layer belongs to.
        :param name: The name of the layer. Defaults to "Layer"
        :param top: Pixelwise offset from the top of the canvas for the new layer.
        :param left: Pixelwise offset from the left of the canvas for the new layer.
        :param compression: Compression algorithm to use for the data.

        :return: A :py:class:`~psd_tools.api.layers.PixelLayer` object
        :raises TypeError: If image is not a PIL Image
        :raises ValueError: If parent is None

        .. note::
            If the image has an alpha channel and the parent PSD mode supports
            layer transparency (e.g. RGBA, LA), the alpha is stored as the
            layer transparency channel and no extra mask is created.  For PSD
            modes that do not carry a transparency band (e.g. RGB, CMYK), the
            alpha channel is instead stored as a pixel mask
            (``USER_LAYER_MASK``).

        .. note::
            On a 16- or 32-bit document the layer is stored at the document's
            depth but with a PIL image's *precision*, which is 8 bits: PIL has
            no 16-bit RGB, CMYK or LAB mode to carry more, and the image is
            converted to :py:attr:`~PSDImage.pil_mode` on the way in. The
            values are widened, not padded -- 128 becomes 32896 at depth 16 --
            so the layer reads back as the image given here.
        """
        if not isinstance(image, Image.Image):
            raise TypeError(f"Expected PIL Image, got {type(image).__name__}")
        if parent is None:
            raise ValueError("Parent cannot be None")

        # Preserve original image to extract alpha for mask creation later.
        original_image = image

        # Convert 1-bit images to 8-bit grayscale
        if image.mode == "1":
            image = image.convert("L")
        image = image.convert(parent._psd.pil_mode)
        if image.mode == "CMYK":
            image = ImageChops.invert(image)

        # Build layer record and channel data list.
        layer_record, channel_data_list = cls._build_layer_record_and_channels(
            image,
            name,
            left,
            top,
            compression,
            version=parent._psd._record.header.version,
            depth=cast(Literal[1, 8, 16, 32], parent._psd._record.header.depth),
        )
        self = cls(parent, layer_record, channel_data_list)
        parent.append(self)

        # Only create a mask if alpha was present in the original image but is
        # NOT preserved in the converted image (e.g. RGB-mode PSD with RGBA
        # input). For alpha-capable PSD modes (RGBA, LA) the alpha is already
        # stored as the transparency channel, so no extra mask is needed.
        if "A" in original_image.getbands() and "A" not in image.getbands():
            self.create_mask(
                original_image, top=top, left=left, compression=compression
            )

        return self

    def _convert_mode(self, parent: GroupMixin) -> "PixelLayer":
        """Re-encode the layer's channels for *parent*'s document.

        Three things about the destination decide how a channel is stored --
        its colour mode, its depth and its file version -- and a move that
        changes any of them leaves channels the destination cannot read. The
        mode is handled by re-rendering through PIL; depth and version are
        handled in place, because the bytes are the same values in a different
        packing and PIL is not needed to repack them.

        Taking the in-place route wherever it applies is also what makes
        widening this guard safe: the PIL route rebuilds the layer record from
        scratch and so drops the layer's opacity, blend mode, mask and tagged
        blocks, and it fires on exactly the moves it fired on before. The
        depth- and version-only moves it now covers keep their record, and
        keep more precision besides -- a 16-bit layer moved to a 32-bit
        document carries 16 bits where ``topil()`` would have narrowed it
        to 8.
        """
        source = self._psd._record.header
        dest = parent._psd._record.header
        if parent._psd.pil_mode != self._psd.pil_mode:
            # Get the current layer image.
            image = self.topil()
            if not isinstance(image, Image.Image):
                raise ValueError("Failed to render the image for mode conversion.")
            # Rebuild layer record and channels.
            layer_record, channel_data_list = self._build_layer_record_and_channels(
                image.convert(parent._psd.pil_mode),
                self.name,
                self.left,
                self.top,
                Compression.RLE,
                version=dest.version,
                depth=cast(Literal[1, 8, 16, 32], dest.depth),
            )
            self._record = layer_record
            self._channels = channel_data_list
        elif (source.depth, source.version) != (dest.depth, dest.version):
            self._reencode_channels(source, dest)
        return self

    @staticmethod
    def _build_layer_record_and_channels(
        image: Image.Image,
        name: str,
        left: int,
        top: int,
        compression: Compression,
        version: int = 1,
        depth: Literal[1, 8, 16, 32] = 8,
        **kwargs: Any,
    ) -> tuple[LayerRecord, ChannelDataList]:
        """Build layer record and channel data list from a PIL image.

        *depth* and *version* are the destination document's, not the image's.
        A PIL image is 8-bit whatever it describes, so taking the depth from it
        wrote a 16- or 32-bit document a channel a half or a quarter of its
        declared length, and the layer read back empty (#867).
        """
        # Initialize the layer record and channel data list.
        layer_record = LayerRecord(
            top=top,
            left=left,
            bottom=top + image.height,
            right=left + image.width,
            channel_info=[],
            **kwargs,
        )
        channel_data_list = ChannelDataList()

        # Set layer name.
        layer_record.name = name

        compression = _compression_for(compression, depth)

        # Transparency channel.
        transparency_data = ChannelData(compression)
        # `getbands()` rather than `has_transparency_data`, which is also true
        # of a "P" image carrying an `info["transparency"]` key -- there is no
        # "A" band to index on one of those, so the lookup below raised.
        if "A" in image.getbands():
            image_bytes = pil_io.encode_channel(
                image.getchannel(image.getbands().index("A")), depth
            )
        else:
            image_bytes = pil_io.encode_opaque_channel(image.width, image.height, depth)
        transparency_data.set_data(
            image_bytes,
            image.width,
            image.height,
            depth,
            version,
        )
        transparency_info = ChannelInfo(
            ChannelID.TRANSPARENCY_MASK, len(transparency_data.data) + 2
        )
        layer_record.channel_info.append(transparency_info)
        channel_data_list.append(transparency_data)

        # Color channels.
        for channel_index in range(pil_io.get_pil_channels(image.mode.rstrip("A"))):
            channel_data = ChannelData(compression)
            channel_data.set_data(
                pil_io.encode_channel(image.getchannel(channel_index), depth),
                image.width,
                image.height,
                depth,
                version,
            )
            channel_info = ChannelInfo(
                id=ChannelID(channel_index), length=len(channel_data.data) + 2
            )
            channel_data_list.append(channel_data)
            layer_record.channel_info.append(channel_info)

        return layer_record, channel_data_list


class SmartObjectLayer(Layer):
    """
    Layer that inserts external data.

    Use :py:attr:`~psd_tools.api.layers.SmartObjectLayer.smart_object`
    attribute to get the external data. See
    :py:class:`~psd_tools.api.smart_object.SmartObject`.

    Example::

        import io
        so = layer.smart_object
        if so.detected_filetype == 'jpg':
            # Use open(external_dir=...) when processing untrusted PSD files.
            with so.open() as f:
                image = Image.open(io.BytesIO(f.read()))
    """

    @property
    def smart_object(self) -> SmartObject:
        """
        Associated smart object.

        :return: :py:class:`~psd_tools.api.smart_object.SmartObject`.
        """
        if not hasattr(self, "_smart_object"):
            self._smart_object = SmartObject(self)
        return self._smart_object


class TypeLayer(Layer):
    """
    Layer that has text and styling information for fonts or paragraphs.

    Text is accessible at :py:attr:`~psd_tools.api.layers.TypeLayer.text`
    property. Styling information for paragraphs is in
    :py:attr:`~psd_tools.api.layers.TypeLayer.engine_dict`.
    Document styling information such as font list is is
    :py:attr:`~psd_tools.api.layers.TypeLayer.resource_dict`.

    Currently, textual information is read-only.

    Example::

        if layer.kind == 'type':
            print(layer.text)
            print(layer.engine_dict['StyleRun'])

            # Extract font for each substring in the text.
            text = layer.engine_dict['Editor']['Text'].value
            fontset = layer.resource_dict['FontSet']
            runlength = layer.engine_dict['StyleRun']['RunLengthArray']
            rundata = layer.engine_dict['StyleRun']['RunArray']
            index = 0
            for length, style in zip(runlength, rundata):
                substring = text[index:index + length]
                stylesheet = style['StyleSheet']['StyleSheetData']
                font = fontset[stylesheet['Font']]
                print('%r gets %s' % (substring, font))
                index += length
    """

    def __init__(self, *args: Any):
        super(TypeLayer, self).__init__(*args)
        self._data = self.tagged_blocks.get_data(Tag.TYPE_TOOL_OBJECT_SETTING)

    @property
    def text(self) -> str:
        r"""
        Text in the layer. Read-only.

        .. note:: New-line character in Photoshop is ``'\r'``.
        """
        return self._data.text_data.get(b"Txt ").value.rstrip("\x00")

    @property
    def text_type(self) -> TextType | None:
        """
        Text type. Read-only.

        :return:
         - :py:attr:`psd_tools.constants.TextType.POINT` for point type text
            (also known as character type)
         - :py:attr:`psd_tools.constants.TextType.PARAGRAPH` for paragraph type text
            (also known as area type)
         - `None` if text type cannot be determined or information is unavailable

        See :py:class:`psd_tools.constants.TextType`.
        """
        shapes = (
            self._engine_data.get("EngineDict", {})
            .get("Rendered", {})
            .get("Shapes", {})
            .get("Children", {})
        )
        if len(shapes) == 1:
            text_type = (
                shapes[0].get("Cookie", {}).get("Photoshop", {}).get("ShapeType", {})
            )
            if text_type in (0, 1):
                return TextType.POINT if text_type == 0 else TextType.PARAGRAPH
            else:
                logger.warning(
                    f"Cannot determine text_type of layer '{self.name}' "
                    "because information inside ShapeType was not found."
                )
        elif not shapes:
            logger.warning(
                f"Cannot determine text_type of layer '{self.name}' "
                "because information inside EngineDict was not found."
            )
        elif len(shapes) > 1:
            logger.warning(
                f"Cannot determine text_type of layer '{self.name}' "
                "because EngineDict has {len(shapes)} shapes."
            )
        return None

    @property
    def transform(self) -> tuple[float, float, float, float, float, float]:
        """Matrix (xx, xy, yx, yy, tx, ty) applies affine transformation."""
        return self._data.transform

    @property
    def _engine_data(self) -> engine_data.EngineData | engine_data.EngineData2:
        """Styling and resource information."""
        return self._data.text_data.get(b"EngineData").value

    @property
    def engine_dict(self) -> engine_data.Dict:
        """Styling information dict."""
        return self._engine_data.get("EngineDict")

    @property
    def resource_dict(self) -> engine_data.Dict:
        """Resource set."""
        return self._engine_data.get("ResourceDict")

    @property
    def document_resources(self) -> engine_data.Dict:
        """Resource set relevant to the document."""
        return self._engine_data.get("DocumentResources")

    @property
    def warp(self) -> DescriptorBlock | None:
        """Warp configuration."""
        return self._data.warp

    @property
    def typesetting(self) -> "TypeSetting":
        """
        Structured typographic data.

        Returns a :py:class:`~psd_tools.api.typesetting.TypeSetting` object
        that provides Pythonic access to fonts, paragraphs, styled runs,
        and default styles without navigating raw engine data dicts.

        Example::

            ts = layer.typesetting
            for paragraph in ts:
                print(paragraph.style.justification)
                for run in paragraph.runs:
                    print(run.text, run.style.font_name, run.style.font_size)

        See also: :py:attr:`engine_dict`, :py:attr:`resource_dict` for raw data.
        """
        if not hasattr(self, "_typesetting"):
            from psd_tools.api.typesetting import TypeSetting  # noqa: PLC0415

            self._typesetting = TypeSetting(
                self.text,
                self.engine_dict,
                self.resource_dict,
            )
        return self._typesetting

    @property
    def font_names(self) -> list[str]:
        """
        List of PostScript font names used in this text layer.

        Convenience shortcut for::

            [font.postscript_name for font in layer.typesetting.fonts]
        """
        return [font.postscript_name for font in self.typesetting.fonts]


class ShapeLayer(Layer):
    """
    Layer that has drawing in vector mask.
    """

    def __init__(self, *args: Any):
        super(ShapeLayer, self).__init__(*args)
        self._bbox: tuple[int, int, int, int] | None = None

    @property
    def left(self) -> int:
        return self.bbox[0]

    @left.setter
    def left(self, value: int) -> None:
        raise NotImplementedError("ShapeLayer left position is not writable yet.")

    @property
    def top(self) -> int:
        return self.bbox[1]

    @top.setter
    def top(self, value: int) -> None:
        raise NotImplementedError("ShapeLayer top position is not writable yet.")

    @property
    def right(self) -> int:
        return self.bbox[2]

    @property
    def bottom(self) -> int:
        return self.bbox[3]

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """(left, top, right, bottom) tuple."""
        if self._bbox is None:
            if self.has_pixels():
                self._bbox = (
                    self._record.left,
                    self._record.top,
                    self._record.right,
                    self._record.bottom,
                )
            elif self.has_origination() and not any(
                x.invalidated for x in self.origination
            ):
                lefts, tops, rights, bottoms = zip(*[x.bbox for x in self.origination])
                self._bbox = (
                    int(min(lefts)),
                    int(min(tops)),
                    int(max(rights)),
                    int(max(bottoms)),
                )
            elif self.has_vector_mask():
                if self.vector_mask is None:
                    raise ValueError(
                        "Vector mask is None despite has_vector_mask() returning True"
                    )
                bbox = self.vector_mask.bbox
                if self._psd is None:
                    raise ValueError("PSD is None for shape layer")
                self._bbox = (
                    int(round(bbox[0] * self._psd.width)),
                    int(round(bbox[1] * self._psd.height)),
                    int(round(bbox[2] * self._psd.width)),
                    int(round(bbox[3] * self._psd.height)),
                )
            else:
                self._bbox = (0, 0, 0, 0)
            if self._bbox is None:
                raise ValueError("Failed to compute bbox for shape layer")
        return self._bbox


class AdjustmentLayer(Layer):
    """Layer that applies specified image adjustment effect."""

    def __init__(self, *args: Any):
        super(AdjustmentLayer, self).__init__(*args)
        self._data = None
        if hasattr(self.__class__, "_KEY"):
            self._data = self.tagged_blocks.get_data(self.__class__._KEY)


class FillLayer(Layer):
    """Layer that fills the canvas region."""

    def __init__(self, *args: Any):
        super(FillLayer, self).__init__(*args)
        self._data = None
        if hasattr(self.__class__, "_KEY"):
            self._data = self.tagged_blocks.get_data(self.__class__._KEY)

    @property
    def right(self) -> int:
        if self._record.right:
            return self._record.right
        if self._psd is None:
            raise ValueError("Cannot determine the right position of the layer.")
        return self._psd.width

    @property
    def bottom(self) -> int:
        if self._record.bottom:
            return self._record.bottom
        if self._psd is None:
            raise ValueError("Cannot determine the right position of the layer.")
        return self._psd.height
