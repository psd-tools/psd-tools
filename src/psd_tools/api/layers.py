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
from typing import (
    Any,
    Callable,
    Iterable,
    Iterator,
    Optional,
    Protocol,
    Sequence,
    TypeVar,
    Union,
    runtime_checkable,
)

try:
    from typing import Self  # type: ignore[attr-defined]
except ImportError:
    from typing_extensions import Self

import numpy as np
from PIL import Image, ImageChops

import psd_tools.psd.engine_data as engine_data
from psd_tools.api import pil_io
from psd_tools.api.effects import Effects
from psd_tools.api.mask import Mask
from psd_tools.api.protocols import GroupMixinProtocol, LayerProtocol, PSDProtocol
from psd_tools.api.shape import Origination, Stroke, VectorMask
from psd_tools.api.smart_object import SmartObject
from psd_tools.constants import (
    BlendMode,
    ChannelID,
    Clipping,
    CompatibilityMode,
    Compression,
    ProtectedFlags,
    SectionDivider,
    Tag,
    TextType,
)
from psd_tools.psd.descriptor import DescriptorBlock
from psd_tools.psd.layer_and_mask import (
    ChannelData,
    ChannelDataList,
    ChannelInfo,
    LayerRecord,
)
from psd_tools.psd.tagged_blocks import (
    ProtectedSetting,
    SectionDividerSetting,
    TaggedBlocks,
)

logger = logging.getLogger(__name__)


TGroupMixin = TypeVar("TGroupMixin", bound="GroupMixin")


class Layer(LayerProtocol):
    def __init__(
        self,
        parent: "GroupMixin",
        record: LayerRecord,
        channels: ChannelDataList,
    ):
        self._psd = parent._psd
        self._parent: Optional["GroupMixinProtocol"] = parent
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
        Kind of this layer, such as group, pixel, shape, type, smartobject,
        or psdimage. Class name without `layer` suffix.

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
            self._bbox: Optional[tuple[int, int, int, int]] = None
        if isinstance(self.parent, (Group, Artboard)):
            self.parent._invalidate_bbox()

    @property
    def visible(self) -> bool:
        """
        Layer visibility. Doesn't take group visibility in account. Writable.

        :return: `bool`
        """
        return self._record.flags.visible

    @visible.setter
    def visible(self, value: bool) -> None:
        if self.visible != value and self._psd is not None:
            self._psd._mark_updated()
        self._invalidate_bbox()
        self._record.flags.visible = bool(value)

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
            self._psd._mark_updated()
        self._record.opacity = int(value)

    @property
    def parent(self) -> Optional[GroupMixinProtocol]:
        """Parent of this layer."""
        return self._parent  # type: ignore

    def next_sibling(self, visible: bool = False) -> Optional[Self]:
        """Next sibling of this layer."""
        if self.parent is None:
            return None
        index = self.parent.index(self)  # type: ignore
        for i in range(index + 1, len(self.parent)):
            if not visible or self.parent[i].visible:
                return self.parent[i]  # type: ignore[return-value]
        return None

    def previous_sibling(self, visible: bool = False) -> Optional[Self]:
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
    def blend_mode(self, value: Union[bytes, str, BlendMode]) -> None:
        if isinstance(value, str):
            value = value.encode("ascii")
        blend_mode = BlendMode(value)
        if self.blend_mode != blend_mode:
            self._psd._mark_updated()
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
            self._psd._mark_updated()
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
            self._psd._mark_updated()
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
        Returns True if the layer has associated pixels. When this is True,
        `topil` method returns :py:class:`PIL.Image.Image`.

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
    def mask(self) -> Optional[Mask]:
        """
        Returns mask associated with this layer.

        :return: :py:class:`~psd_tools.api.mask.Mask` or `None`
        """
        if not hasattr(self, "_mask"):
            self._mask = Mask(self) if self.has_mask() else None
        return self._mask

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
    def vector_mask(self) -> Optional[VectorMask]:
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
    def stroke(self) -> Optional[Stroke]:
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
    def locks(self) -> Optional[ProtectedSetting]:
        protected_settings_block = self.tagged_blocks.get(Tag.PROTECTED_SETTING)

        if protected_settings_block is not None:
            return protected_settings_block.data

        return None

    def topil(
        self, channel: Optional[int] = None, apply_icc: bool = True
    ) -> Optional[Image.Image]:
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
        from .pil_io import convert_layer_to_pil

        return convert_layer_to_pil(self, channel, apply_icc)

    def numpy(
        self, channel: Optional[str] = None, real_mask: bool = True
    ) -> Optional[np.ndarray]:
        """
        Get NumPy array of the layer.

        :param channel: Which channel to return, can be 'color',
            'shape', 'alpha', or 'mask'. Default is 'color+alpha'.
        :return: :py:class:`numpy.ndarray` or None if there is no pixel.
        """
        from . import numpy_io

        return numpy_io.get_array(self, channel, real_mask=real_mask)

    def composite(
        self,
        viewport: Optional[tuple[int, int, int, int]] = None,
        force: bool = False,
        color: Union[float, tuple[float, ...], np.ndarray] = 1.0,
        alpha: Union[float, np.ndarray] = 0.0,
        layer_filter: Optional[Callable] = None,
        apply_icc: bool = True,
    ) -> Optional[Image.Image]:
        """
        Composite layer and masks (mask, vector mask, and clipping layers).

        :param viewport: Viewport bounding box specified by (x1, y1, x2, y2)
            tuple. Default is the layer's bbox.
        :param force: Boolean flag to force vector drawing.
        :param color: Backdrop color specified by scalar or tuple of scalar.
            The color value should be in [0.0, 1.0]. For example, (1., 0., 0.)
            specifies red in RGB color mode.
        :param alpha: Backdrop alpha in [0.0, 1.0].
        :param layer_filter: Callable that takes a layer as argument and
            returns whether if the layer is composited. Default is
            :py:func:`~psd_tools.api.layers.PixelLayer.is_visible`.
        :return: :py:class:`PIL.Image.Image` or `None`.
        """
        from psd_tools.composite import composite_pil

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
            self._psd._mark_updated()
        self._record.clipping = clipping

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

    def has_effects(self, enabled: bool = True, name: Optional[str] = None) -> bool:
        """
        Returns True if the layer has effects.

        :param enabled: If True, check for enabled effects.
        :param name: If given, check for specific effect type.
        :return: `bool`
        """
        has_effect_tag = any(
            tag in self.tagged_blocks
            for tag in (
                Tag.OBJECT_BASED_EFFECTS_LAYER_INFO,
                Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V0,
                Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V1,
            )
        )
        # No effects tag.
        if not has_effect_tag:
            return False

        # Global enable flag check.
        if enabled and not self.effects.enabled:
            return False

        # No specific effect type, check for any effect.
        if name is None:
            if enabled:
                return any(effect.enabled for effect in self.effects)
            return True

        # Check for specific effect type and enabled state.
        return any(self.effects.find(name, enabled))

    @property
    def effects(self) -> Effects:
        """
        Layer effects.

        :return: :py:class:`~psd_tools.api.effects.Effects`
        """
        if not hasattr(self, "_effects"):
            self._effects = Effects(self)
        return self._effects

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
            self._psd._mark_updated()
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
            self._psd._mark_updated()
        self.tagged_blocks.set_data(
            Tag.REFERENCE_POINT, [float(value[0]), float(value[1])]
        )

    def __repr__(self) -> str:
        has_size = self.width > 0 and self.height > 0
        return "%s(%r%s%s%s%s%s)" % (
            self.__class__.__name__,
            self.name,
            " size=%dx%d" % (self.width, self.height) if has_size else "",
            " invisible" if not self.visible else "",
            " clip" if self.clipping else "",
            " mask" if self.has_mask() else "",
            " effects" if self.has_effects() else "",
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


@runtime_checkable
class GroupMixin(GroupMixinProtocol, Protocol):
    _psd: PSDProtocol
    _bbox: Optional[tuple[int, int, int, int]] = None
    _layers: list[Layer]

    # Note: left, top, right, bottom properties are inherited from Layer
    # and computed via bbox. Groups compute bbox from children, not from _record.

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """(left, top, right, bottom) tuple computed from children."""
        if self._bbox is None:
            self._bbox = Group.extract_bbox(self)
        return self._bbox

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
        self.insert(key, value)

    def __delitem__(self, key: int) -> None:
        self.remove(self._layers[key])

    def append(self, layer: Layer) -> None:
        """
        Add a layer to the end (top) of the group.

        This operation rewrites the internal references of the layer.
        Adding the same layer will not create a duplicate.

        :param layer: The layer to add.
        :raises TypeError: If the provided object is not a Layer instance.
        :raises ValueError: If attempting to add a group to itself.
        """
        self.extend([layer])

    def extend(self, layers: Iterable[Layer]) -> None:
        """
        Add a list of layers to the end (top) of the group.

        This operation rewrites the internal references of the layers.
        Adding the same layer will not create a duplicate.

        :param layers: The layers to add.
        :raises TypeError: If the provided object is not a Layer instance.
        :raises ValueError: If attempting to add a group to itself.
        """
        self._check_insertion(layers)
        # Remove parent's reference to the layers.
        for layer in layers:
            # NOTE: New or removed layers may not be in the parent container.
            if isinstance(layer.parent, GroupMixin) and layer in layer.parent:
                layer.parent._layers.remove(layer)  # Skip checks for performance
        self._layers.extend(layers)
        self._update_children()
        self._psd._update_record()

    def insert(self, index: int, layer: Layer) -> None:
        """
        Insert the given layer at the specified index.

        This operation rewrites the internal references of the layer.

        :param index: The index to insert the layer at.
        :param layer: The layer to insert.
        :raises TypeError: If the provided object is not a Layer instance.
        :raises ValueError: If attempting to add a group to itself.
        """
        self._check_insertion([layer])
        # Remove parent's reference to the layer.
        if isinstance(layer.parent, GroupMixin) and layer in layer.parent:
            layer.parent._layers.remove(layer)  # Skip checks for performance
        self._layers.insert(index, layer)
        self._update_children()
        self._psd._update_record()

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
        for layer in self._layers:
            layer._parent = None
        self._layers.clear()
        self._psd._update_record()

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

    def _check_insertion(self, layers: Iterable[Layer]) -> None:
        """Check that the given layers can be added to this group.

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

    def find(self, name: str) -> Optional[Layer]:
        """
        Returns the first layer found for the given layer name

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
        self._bounding_record: Optional[LayerRecord] = None
        self._bounding_channels: Optional[ChannelDataList] = None
        Layer.__init__(self, parent, record, channels)

    @property
    def _setting(self) -> Optional[SectionDividerSetting]:
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
    def blend_mode(self, value: Union[str, bytes, BlendMode]) -> None:
        _value = BlendMode(value.encode("ascii") if isinstance(value, str) else value)
        if self.blend_mode != _value and self._psd is not None:
            self._psd._mark_updated()
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
            self._psd._mark_updated()
        self._record.clipping = clipping

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
        viewport: Optional[tuple[int, int, int, int]] = None,
        force: bool = False,
        color: Union[float, tuple[float, ...], np.ndarray] = 1.0,
        alpha: Union[float, np.ndarray] = 0.0,
        layer_filter: Optional[Callable] = None,
        apply_icc: bool = True,
    ) -> Optional[Image.Image]:
        """
        Composite layer and masks (mask, vector mask, and clipping layers).

        :param viewport: Viewport bounding box specified by (x1, y1, x2, y2)
            tuple. Default is the layer's bbox.
        :param force: Boolean flag to force vector drawing.
        :param color: Backdrop color specified by scalar or tuple of scalar.
            The color value should be in [0.0, 1.0]. For example, (1., 0., 0.)
            specifies red in RGB color mode.
        :param alpha: Backdrop alpha in [0.0, 1.0].
        :param layer_filter: Callable that takes a layer as argument and
            returns whether if the layer is composited. Default is
            :py:func:`~psd_tools.api.layers.PixelLayer.is_visible`.
        :return: :py:class:`PIL.Image.Image`.
        """
        from psd_tools.composite import composite_pil

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
        layers: Union[Sequence[Layer], GroupMixin], include_invisible: bool = False
    ) -> tuple[int, int, int, int]:
        """
        Returns a bounding box for ``layers`` or (0, 0, 0, 0) if the layers
        have no bounding box.

        :param layers: sequence of layers or a group.
        :param include_invisible: include invisible layers in calculation.
        :return: tuple of four int
        """

        def _get_bbox(layer: Layer, **kwargs: Any) -> tuple[int, int, int, int]:
            if layer.is_group() and isinstance(layer, GroupMixin):
                return Group.extract_bbox(layer, **kwargs)
            else:
                return layer.bbox

        bboxes = [
            _get_bbox(layer, include_invisible=include_invisible)
            for layer in layers
            if include_invisible or layer.is_visible()
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
        Create a new Group object with minimal records and data channels and metadata
        to properly include the group in the PSD file.

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
        :param psdimage: The target psdimage the image will be converted for.
        :param name: The name of the layer. Defaults to "Layer"
        :param top: Pixelwise offset from the top of the canvas for the new layer.
        :param left: Pixelwise offset from the left of the canvas for the new layer.
        :param compression: Compression algorithm to use for the data.

        :return: A :py:class:`~psd_tools.api.layers.PixelLayer` object
        :raises TypeError: If image is not a PIL Image or parent is None
        """
        if not isinstance(image, Image.Image):
            raise TypeError(f"Expected PIL Image, got {type(image).__name__}")
        if parent is None:
            raise ValueError("Parent cannot be None")

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
        )
        self = cls(parent, layer_record, channel_data_list)
        parent.append(self)
        return self

    def _convert_mode(self, parent: GroupMixin) -> "PixelLayer":
        """Convert the image format to match the given group."""
        if parent._psd.pil_mode == self._psd.pil_mode:
            return self

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
        )
        self._record = layer_record
        self._channels = channel_data_list
        return self

    @staticmethod
    def _build_layer_record_and_channels(
        image: Image.Image,
        name: str,
        left: int,
        top: int,
        compression: Compression,
        **kwargs: Any,
    ) -> tuple[LayerRecord, ChannelDataList]:
        """Build layer record and channel data list from a PIL image."""

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

        # Transparency channel.
        transparency_data = ChannelData(compression)
        if image.has_transparency_data:
            # TODO: Need check for other types of transparency, palette for "indexed" mode
            image_bytes = image.getchannel(image.getbands().index("A")).tobytes()
        else:
            image_bytes = b"\xff" * (image.width * image.height)
        transparency_data.set_data(
            image_bytes,
            image.width,
            image.height,
            pil_io.get_pil_depth(image.mode.rstrip("A")),
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
                image.getchannel(channel_index).tobytes(),
                image.width,
                image.height,
                pil_io.get_pil_depth(image.mode.rstrip("A")),
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
        if layer.smart_object.filetype == 'jpg':
            image = Image.open(io.BytesIO(layer.smart_object.data))
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
        """
        Text in the layer. Read-only.

        .. note:: New-line character in Photoshop is `'\\\\r'`.
        """
        return self._data.text_data.get(b"Txt ").value.rstrip("\x00")

    @property
    def text_type(self) -> Optional[TextType]:
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
    def _engine_data(self) -> Union[engine_data.EngineData, engine_data.EngineData2]:
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
    def warp(self) -> Optional[DescriptorBlock]:
        """Warp configuration."""
        return self._data.warp


class ShapeLayer(Layer):
    """
    Layer that has drawing in vector mask.
    """

    def __init__(self, *args: Any):
        super(ShapeLayer, self).__init__(*args)
        self._bbox: Optional[tuple[int, int, int, int]] = None

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
