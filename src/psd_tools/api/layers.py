"""
Layer module.
"""

from __future__ import annotations

import logging
from typing import (
    Any,
    Callable,
    Iterable,
    Iterator,
    Protocol,
    TypeVar,
    runtime_checkable,
)

try:
    from typing import Self
except ImportError:
    from typing_extensions import Self

import numpy as np
from PIL.Image import Image as PILImage

import psd_tools.psd.engine_data as engine_data
from psd_tools.api.effects import Effects
from psd_tools.api.mask import Mask
from psd_tools.api.pil_io import get_pil_channels, get_pil_depth
from psd_tools.api.shape import Origination, Stroke, VectorMask
from psd_tools.api.smart_object import SmartObject
from psd_tools.constants import (
    BlendMode,
    ChannelID,
    Clipping,
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
from psd_tools.psd.patterns import Patterns
from psd_tools.psd.tagged_blocks import (
    ProtectedSetting,
    SectionDividerSetting,
    TaggedBlocks,
)
from psd_tools.terminology import Key

logger = logging.getLogger(__name__)


TGroupMixin = TypeVar("TGroupMixin", bound="GroupMixin")


class Layer(object):
    def __init__(
        self,
        psd: Any,
        record: LayerRecord,
        channels: ChannelDataList,
        parent: TGroupMixin | None,
    ):
        from psd_tools.api.psd_image import PSDImage  # Circular import

        assert isinstance(psd, PSDImage) or psd is None

        self._psd: PSDImage | None = psd
        self._record = record
        self._channels = channels
        self._parent: GroupMixin | None = parent
        self._clip_layers: list[Self] = []
        self._has_clip_target = True

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
        assert len(value) < 256, "Layer name too long (%d) %s" % (len(value), value)
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
            self._bbox: tuple[int, int, int, int] | None = None
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
        self._invalidate_bbox()
        self._record.flags.visible = bool(value)

    def is_visible(self) -> bool:
        """
        Layer visibility. Takes group visibility in account.

        :return: `bool`
        """
        return self.visible and self.parent is not None and self.parent.is_visible()  # type: ignore

    @property
    def opacity(self) -> int:
        """
        Opacity of this layer in [0, 255] range. Writable.

        :return: int
        """
        return self._record.opacity

    @opacity.setter
    def opacity(self, value: int) -> None:
        assert 0 <= value and value <= 255
        self._record.opacity = int(value)

    @property
    def parent(self) -> TGroupMixin | None:
        """Parent of this layer."""
        return self._parent  # type: ignore

    def is_group(self) -> bool:
        """
        Return True if the layer is a group.

        :return: `bool`
        """
        return isinstance(self, GroupMixin)

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
        self._record.blend_mode = BlendMode(value)

    @property
    def left(self) -> int:
        """
        Left coordinate. Writable.

        :return: int
        """
        return self._record.left

    @left.setter
    def left(self, value: int) -> None:
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
        `topil` method returns :py:class:`PIL.Image`.

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

        Example using the constants of ProtectedFlags and bitwise or operation to lock both pixels and positions::

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
    ) -> PILImage | None:
        """
        Get PIL Image of the layer.

        :param channel: Which channel to return; e.g., 0 for 'R' channel in RGB
            image. See :py:class:`~psd_tools.constants.ChannelID`. When `None`,
            the method returns all the channels supported by PIL modes.
        :param apply_icc: Whether to apply ICC profile conversion to sRGB.
        :return: :py:class:`PIL.Image`, or `None` if the layer has no pixels.

        Example::

            from psd_tools.constants import ChannelID

            image = layer.topil()
            red = layer.topil(ChannelID.CHANNEL_0)
            alpha = layer.topil(ChannelID.TRANSPARENCY_MASK)

        .. note:: Not all of the PSD image modes are supported in
            :py:class:`PIL.Image`. For example, 'CMYK' mode cannot include
            alpha channel in PIL. In this case, topil drops alpha channel.
        """
        from .pil_io import convert_layer_to_pil

        return convert_layer_to_pil(self, channel, apply_icc)

    def numpy(
        self, channel: str | None = None, real_mask: bool = True
    ) -> np.ndarray | None:
        """
        Get NumPy array of the layer.

        :param channel: Which channel to return, can be 'color',
            'shape', 'alpha', or 'mask'. Default is 'color+alpha'.
        :return: :py:class:`numpy.ndarray` or None if there is no pixel.
        """
        from .numpy_io import get_array

        return get_array(self, channel, real_mask=real_mask)

    def composite(
        self,
        viewport: tuple[int, int, int, int] | None = None,
        force: bool = False,
        color: float | tuple[float, ...] | np.ndarray = 1.0,
        alpha: float | np.ndarray = 0.0,
        layer_filter: Callable | None = None,
        apply_icc: bool = True,
    ) -> PILImage | None:
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
        :return: :py:class:`PIL.Image` or `None`.
        """
        from psd_tools.composite import composite_pil

        return composite_pil(
            self, color, alpha, viewport, layer_filter, force, apply_icc=apply_icc
        )

    def has_clip_layers(self) -> bool:
        """
        Returns True if the layer has associated clipping.

        :return: `bool`
        """
        return len(self.clip_layers) > 0

    @property
    def clip_layers(self) -> list[Self]:
        """
        Clip layers associated with this layer.

        :return: list of layers
        """
        return self._clip_layers

    @property
    def clipping_layer(self) -> bool:
        """
        Clipping flag for this layer. Writable.

        :return: `bool`
        """
        return self._record.clipping == Clipping.NON_BASE

    @clipping_layer.setter
    def clipping_layer(self, value: bool) -> None:
        if self._psd:
            self._record.clipping = Clipping.NON_BASE if value else Clipping.BASE
            self._psd._compute_clipping_layers()

    def has_effects(self) -> bool:
        """
        Returns True if the layer has effects.

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
        if not has_effect_tag:
            return False
        if not self.effects.enabled:
            return False
        for effect in self.effects:
            if effect.enabled:
                return True
        return False

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

    def __repr__(self) -> str:
        has_size = self.width > 0 and self.height > 0
        return "%s(%r%s%s%s%s)" % (
            self.__class__.__name__,
            self.name,
            " size=%dx%d" % (self.width, self.height) if has_size else "",
            " invisible" if not self.visible else "",
            " mask" if self.has_mask() else "",
            " effects" if self.has_effects() else "",
        )

    # Structure operations, supposes unique references to layers, deep copy might be needed in the future
    def delete_layer(self) -> Self:
        """
        Deletes the layer and all its child layers if the layer is a group from its parent (group or psdimage).
        """

        if self.parent is not None and isinstance(self.parent, GroupMixin):
            if self in self.parent:
                self.parent.remove(self)
            self.parent._update_psd_record()
        else:
            logger.warning(
                "Cannot delete layer {} because there is no parent.".format(self)
            )

        return self

    def move_to_group(self, group: "GroupMixin") -> Self:
        """
        Moves the layer to the given group, updates the tree metadata as needed.

        :param group: The group the current layer will be moved into.
        """

        assert isinstance(group, GroupMixin)
        assert group is not self

        if isinstance(self, GroupMixin):
            assert (
                group not in self.descendants()
            ), "Cannot move group {} into its descendant {}".format(self, group)

        if self.parent is not None and isinstance(self.parent, GroupMixin):
            if self in self.parent:
                self.parent.remove(self)

        group.append(self)

        return self

    def move_up(self, offset: int = 1) -> Self:
        """
        Moves the layer up a certain offset within the group the layer is in.

        :param offset:
        """

        assert self.parent is not None and isinstance(self.parent, GroupMixin)

        newindex = self.parent.index(self) + offset

        if newindex < 0:
            newindex = 0
        elif newindex >= len(self.parent):
            newindex = len(self.parent) - 1

        self.parent.remove(self)
        self.parent.insert(newindex, self)

        return self

    def move_down(self, offset: int = 1) -> Self:
        """
        Moves the layer down a certain offset within the group the layer is in.

        :param offset:
        """

        return self.move_up(-1 * offset)

    def _fetch_tagged_blocks(self, target_psd: Any) -> None:  # Circular import
        # Retrieve the patterns contained in the layer current ._psd and add them to the target psd
        _psd = target_psd

        effects = [effect for effect in self.effects if effect.has_patterns()]
        pattern_ids = [
            effect.pattern[Key.ID].value.rstrip("\x00")  # type: ignore
            for effect in effects
        ]

        if pattern_ids:
            psd_global_blocks = _psd.tagged_blocks

            if psd_global_blocks is None:
                psd_global_blocks = TaggedBlocks()
                _psd._record.layer_and_mask_information.tagged_blocks = (
                    psd_global_blocks
                )

            if Tag.PATTERNS1 not in psd_global_blocks.keys():
                psd_global_blocks.set_data(Tag.PATTERNS1, Patterns())

            sourcePatterns = []
            for tag in (Tag.PATTERNS1, Tag.PATTERNS2, Tag.PATTERNS3):
                if (
                    self._psd is not None
                    and self._psd.tagged_blocks is not None
                    and tag in self._psd.tagged_blocks
                ):
                    sourcePatterns.extend(self._psd.tagged_blocks.get_data(tag))

            # TODO: Use the exact tag.
            psd_global_blocks.get(Tag.PATTERNS1).data.extend(
                [
                    pattern
                    for pattern in sourcePatterns
                    if pattern.pattern_id in pattern_ids
                    and pattern.pattern_id
                    not in [
                        targetPattern.pattern_id
                        for targetPattern in psd_global_blocks.get(Tag.PATTERNS1).data
                    ]
                ]
            )


@runtime_checkable
class GroupMixin(Protocol):
    _bbox: tuple[int, int, int, int] | None = None
    _layers: list[Layer]
    _psd: Any  # TODO: Circular import

    @property
    def left(self) -> int:
        return self.bbox[0]

    @property
    def top(self) -> int:
        return self.bbox[1]

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
            self._bbox = Group.extract_bbox(self)
        return self._bbox

    def __len__(self) -> int:
        return self._layers.__len__()

    def __iter__(self) -> Iterator[Layer]:
        return self._layers.__iter__()

    def __getitem__(self, key) -> Layer:
        return self._layers.__getitem__(key)

    def __setitem__(self, key, value) -> None:
        self._check_valid_layers(value)

        self._layers.__setitem__(key, value)

        self._update_layer_metadata()
        self._update_psd_record()

    def __delitem__(self, key) -> None:
        self._update_psd_record()
        self._layers.__delitem__(key)

    def append(self, layer: Layer) -> None:
        """
        Add a layer to the end (top) of the group

        :param layer: The layer to add
        """

        assert layer is not self
        self.extend([layer])

    def extend(self, layers: Iterable[Layer]) -> None:
        """
        Add a list of layers to the end (top) of the group

        :param layers: The layers to add
        """

        self._check_valid_layers(layers)
        self._layers.extend(layers)
        self._update_layer_metadata()
        self._update_psd_record()

    def insert(self, index: int, layer: Layer) -> None:
        """
        Insert the given layer at the specified index.

        :param index:
        :param layer:
        """

        self._check_valid_layers(layer)
        self._layers.insert(index, layer)
        self._update_layer_metadata()
        self._update_psd_record()

    def remove(self, layer: Layer) -> Self:
        """
        Removes the specified layer from the group

        :param layer:
        """

        self._layers.remove(layer)
        self._update_psd_record()
        return self

    def pop(self, index: int = -1) -> Layer:
        """
        Removes the specified layer from the list and returns it.

        :param index:
        """

        popLayer = self._layers.pop(index)
        self._update_psd_record()
        return popLayer

    def clear(self) -> None:
        """
        Clears the group.
        """

        self._layers.clear()
        self._update_psd_record()

    def index(self, layer: Layer) -> int:
        """
        Returns the index of the specified layer in the group.

        :param layer:
        """

        return self._layers.index(layer)

    def count(self, layer: Layer) -> int:
        """
        Counts the number of occurences of a layer in the group.

        :param layer:
        """

        return self._layers.count(layer)

    def _check_valid_layers(self, layers: Layer | Iterable[Layer]) -> None:
        assert layers is not self, "Cannot add the group {} to itself.".format(self)

        if isinstance(layers, Layer):
            layers = [layers]

        for layer in layers:
            assert isinstance(layer, Layer)
            if isinstance(layer, GroupMixin):
                assert (
                    self not in list(layer.descendants())
                ), "This operation would create a reference loop within the group between {} and {}.".format(
                    self, layer
                )

    def _update_layer_metadata(self) -> None:
        from psd_tools.api.psd_image import PSDImage  # Circular import

        _psd: PSDImage | None = self if isinstance(self, PSDImage) else self._psd

        for layer in self.descendants():
            if layer._psd != _psd and _psd is not None:
                if isinstance(layer, PixelLayer):
                    layer._convert(_psd)

                layer._fetch_tagged_blocks(_psd)  # type: ignore
                layer._psd = _psd

        for layer in self._layers[:]:
            layer._parent = self

    def _update_psd_record(self) -> None:
        from psd_tools.api.psd_image import PSDImage  # Circular import

        if isinstance(self, PSDImage):
            self._updated_layers = True  # type: ignore
        elif self._psd is not None:
            self._psd._updated_layers = True

    def descendants(self, include_clip: bool = True) -> Iterator[Layer]:
        """
        Return a generator to iterate over all descendant layers.

        Example::

            # Iterate over all layers
            for layer in psd.descendants():
                print(layer)

            # Iterate over all layers in reverse order
            for layer in reversed(list(psd.descendants())):
                print(layer)

        :param include_clip: include clipping layers.
        """
        for layer in self:
            yield layer
            if isinstance(layer, GroupMixin):
                for child in layer.descendants(include_clip):
                    yield child
            if include_clip and hasattr(layer, "clip_layers"):
                for clip_layer in layer.clip_layers:
                    yield clip_layer

    def find(self, name: str) -> Layer | None:
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

    @staticmethod
    def extract_bbox(
        layers, include_invisible: bool = False
    ) -> tuple[int, int, int, int]:
        """
        Returns a bounding box for ``layers`` or (0, 0, 0, 0) if the layers
        have no bounding box.

        :param include_invisible: include invisible layers in calculation.
        :return: tuple of four int
        """

        def _get_bbox(layer, **kwargs):
            if layer.is_group():
                return Group.extract_bbox(layer, **kwargs)
            else:
                return layer.bbox

        if not hasattr(layers, "__iter__"):
            layers = [layers]

        bboxes = [
            _get_bbox(layer, include_invisible=include_invisible)
            for layer in layers
            if include_invisible or layer.is_visible()
        ]
        bboxes = [bbox for bbox in bboxes if bbox != (0, 0, 0, 0)]
        if len(bboxes) == 0:  # Empty bounding box.
            return (0, 0, 0, 0)
        lefts, tops, rights, bottoms = zip(*bboxes)
        return (min(lefts), min(tops), max(rights), max(bottoms))

    def __init__(
        self,
        psd: Any,
        record: LayerRecord,
        channels: ChannelDataList,
        parent: TGroupMixin | None,
    ):
        self._layers = []
        self._bounding_record = None
        self._bounding_channels = None
        Layer.__init__(self, psd, record, channels, parent)

    @property
    def _setting(self) -> SectionDividerSetting | None:
        # Can be None.
        return self.tagged_blocks.get_data(Tag.SECTION_DIVIDER_SETTING)

    @property
    def blend_mode(self) -> BlendMode:
        setting = self._setting
        if setting is not None:
            return setting.blend_mode
        return super(Group, self).blend_mode

    @blend_mode.setter
    def blend_mode(self, value: str | bytes | BlendMode) -> None:
        _value = BlendMode(value.encode("ascii") if isinstance(value, str) else value)
        if _value == BlendMode.PASS_THROUGH:
            self._record.blend_mode = BlendMode.NORMAL
        else:
            self._record.blend_mode = _value
        setting = self._setting
        if setting is not None:
            setting.blend_mode = _value

    def composite(
        self,
        viewport: tuple[int, int, int, int] | None = None,
        force: bool = False,
        color: float | tuple[float, ...] | np.ndarray = 1.0,
        alpha: float | np.ndarray = 0.0,
        layer_filter: Callable | None = None,
        apply_icc: bool = True,
    ):
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
        :return: :py:class:`PIL.Image`.
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

    def _set_bounding_records(self, _bounding_record, _bounding_channels) -> None:
        # Attributes that store the record for the folder divider.
        # Used when updating the record so that we don't need to recompute
        # Them from the ending layer
        self._bounding_record = _bounding_record
        self._bounding_channels = _bounding_channels

        return

    @classmethod
    def new(
        cls,
        name: str = "Group",
        open_folder: bool = True,
        parent: GroupMixin | None = None,
    ) -> Self:
        """
        Create a new Group object with minimal records and data channels and metadata to properly include the group in the PSD file.

        :param name: The display name of the group. Default to "Group".
        :param open_folder: Boolean defining whether the folder will be open or closed in photoshop. Default to True.
        :param parent: Optional parent folder to move the newly created group into.

        :return: A :py:class:`~psd_tools.api.layers.Group` object
        """

        record = LayerRecord(top=0, left=0, bottom=0, right=0, name=name)
        record.tagged_blocks = TaggedBlocks()

        record.tagged_blocks.set_data(
            Tag.SECTION_DIVIDER_SETTING,
            SectionDivider.OPEN_FOLDER if open_folder else SectionDivider.CLOSED_FOLDER,
        )
        record.tagged_blocks.set_data(Tag.UNICODE_LAYER_NAME, name)

        _bounding_record = LayerRecord(
            top=0, left=0, bottom=0, right=0, name="</Layer group>"
        )
        _bounding_record.tagged_blocks = TaggedBlocks()

        _bounding_record.tagged_blocks.set_data(
            Tag.SECTION_DIVIDER_SETTING, SectionDivider.BOUNDING_SECTION_DIVIDER
        )
        _bounding_record.tagged_blocks.set_data(
            Tag.UNICODE_LAYER_NAME, "</Layer group>"
        )

        record.channel_info = [ChannelInfo(id=i - 1, length=2) for i in range(4)]
        _bounding_record.channel_info = [
            ChannelInfo(id=i - 1, length=2) for i in range(4)
        ]

        channels = ChannelDataList()
        for i in range(4):
            channels.append(ChannelData(compression=Compression.RAW, data=b""))

        _bounding_channels = channels

        group = cls(None, record, channels, None)

        group._set_bounding_records(_bounding_record, _bounding_channels)

        if parent is not None and isinstance(parent, GroupMixin):
            group.move_to_group(parent)

        return group

    @classmethod
    def group_layers(
        cls,
        layers: list[Layer],
        name: str = "Group",
        parent: GroupMixin | None = None,
        open_folder: bool = True,
    ):
        """
        Create a new Group object containing the given layers and moved into the parent folder.

        If no parent is provided, the group will be put in place of the first layer in the given list. Example below:

        :param layers: The layers to group. Can by any subclass of :py:class:`~psd_tools.api.layers.Layer`
        :param name: The display name of the group. Default to "Group".
        :param parent: The parent group to add the newly created Group object into.
        :param open_folder: Boolean defining whether the folder will be open or closed in photoshop. Default to True.

        :return: A :py:class:`~psd_tools.api.layers.Group`
        """

        assert len(layers) > 0

        if parent is None and isinstance(layers[0]._parent, GroupMixin):
            parent = layers[0]._parent
        else:
            # Newly created groups do not have a parent yet.
            logger.debug("Failed to find a parent for the new group.")

        group = cls.new(name, open_folder)
        for layer in layers:
            layer.move_to_group(group)
        if isinstance(parent, GroupMixin):
            parent.append(group)
        return group


class Artboard(Group):
    """
    Artboard is a special kind of group that has a pre-defined viewbox.
    """

    @classmethod
    def _move(kls, group: Group) -> "Artboard":
        assert group.parent is not None
        self = kls(group._psd, group._record, group._channels, group.parent)  # type: ignore
        self._layers = group._layers
        self._set_bounding_records(group._bounding_record, group._bounding_channels)
        for layer in self._layers:
            layer._parent = self
        assert self.parent is not None
        for index in range(len(self.parent)):
            if group == self.parent[index]:
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
            assert data is not None
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
        pil_im: PILImage,
        psd_file: Any | None = None,  # TODO: Fix circular import
        layer_name: str = "Layer",
        top: int = 0,
        left: int = 0,
        compression: Compression = Compression.RLE,
        **kwargs: Any,
    ) -> "PixelLayer":
        """
        Creates a PixelLayer from a PIL image for a given psd file.

        :param pil_im: The :py:class:`~PIL.Image` object to convert to photoshop
        :param psdfile: The psd file the image will be converted for.
        :param layer_name: The name of the layer. Defaults to "Layer"
        :param top: Pixelwise offset from the top of the canvas for the new layer.
        :param left: Pixelwise offset from the left of the canvas for the new layer.
        :param compression: Compression algorithm to use for the data.

        :return: A :py:class:`~psd_tools.api.layers.PixelLayer` object
        """

        assert pil_im

        if pil_im.mode == "1":
            pil_im = pil_im.convert("L")

        if psd_file is not None:
            pil_im = pil_im.convert(psd_file.pil_mode)
        else:
            logger.warning(
                "No psd file was provided, it will not be possible to convert it when moving to another psd. Might create corrupted psds."
            )

        if pil_im.mode == "CMYK":
            from PIL import ImageChops

            pil_im = ImageChops.invert(pil_im)

        layer_record = LayerRecord(
            top=top,
            left=left,
            bottom=top + pil_im.height,
            right=left + pil_im.width,
            **kwargs,
        )
        channel_data_list = ChannelDataList()

        layer_record.name = layer_name
        layer_record.channel_info = [ChannelInfo(ChannelID.TRANSPARENCY_MASK, 2)]

        # Initialize the alpha channel to full opacity, photoshop sometimes didn't handle the file when not done
        channel_data_list.append(ChannelData(compression))
        channel_data_list[0].set_data(
            b"\xff" * (pil_im.width * pil_im.height),
            pil_im.width,
            pil_im.height,
            get_pil_depth(pil_im.mode.rstrip("A")),
        )
        layer_record.channel_info[0].length = len(channel_data_list[0].data) + 2

        for channel_index in range(get_pil_channels(pil_im.mode.rstrip("A"))):
            channel_data = ChannelData(compression)
            channel_data.set_data(
                pil_im.getchannel(channel_index).tobytes(),
                pil_im.width,
                pil_im.height,
                get_pil_depth(pil_im.mode.rstrip("A")),
            )

            channel_info = ChannelInfo(
                id=ChannelID(channel_index), length=len(channel_data.data) + 2
            )

            channel_data_list.append(channel_data)
            layer_record.channel_info.append(channel_info)

        if pil_im.has_transparency_data:
            # Need check for other types of transparency, palette for "indexed" mode
            transparency_channel_index = pil_im.getbands().index("A")

            channel_data_list[0].set_data(
                pil_im.getchannel(transparency_channel_index).tobytes(),
                pil_im.width,
                pil_im.height,
                get_pil_depth(pil_im.mode.rstrip("A")),
            )
            layer_record.channel_info[0].length = len(channel_data_list[0].data) + 2

        self = cls(psd_file, layer_record, channel_data_list, None)

        return self

    def _convert(self, target_psd: Any) -> "PixelLayer":
        # assert self._psd is not None, "This layer cannot be converted because it has no psd file linked."

        if self._psd is None:
            logger.warning(
                "This layer {} cannot be converted to the target psd".format(self)
            )
            return self

        if target_psd.pil_mode == self._psd.pil_mode:
            return self

        rendered_image = self.composite()
        if not isinstance(rendered_image, PILImage):
            raise ValueError("Failed to render the image for conversion.")

        new_layer = PixelLayer.frompil(
            rendered_image,
            target_psd,
            self.name,
            self.top,
            self.left,
            self._channels[0].compression,
        )

        self._record.channel_info = new_layer._record.channel_info
        self._channels = new_layer._channels

        return self


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
    def text_type(self) -> TextType | None:
        """
        Text type. Read-only.

        :return:
         - :py:attr:`psd_tools.constants.TextType.POINT` for point type text (also known as character type)
         - :py:attr:`psd_tools.constants.TextType.PARAGRAPH` for paragraph type text (also known as area type)
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
                    f"Cannot determine text_type of layer '{self.name}' because information inside ShapeType was not found."
                )
        elif not shapes:
            logger.warning(
                f"Cannot determine text_type of layer '{self.name}' because information inside EngineDict was not found."
            )
        elif len(shapes) > 1:
            logger.warning(
                f"Cannot determine text_type of layer '{self.name}' because EngineDict has {len(shapes)} shapes."
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
                assert self.vector_mask is not None
                bbox = self.vector_mask.bbox
                assert self._psd is not None
                self._bbox = (
                    int(round(bbox[0] * self._psd.width)),
                    int(round(bbox[1] * self._psd.height)),
                    int(round(bbox[2] * self._psd.width)),
                    int(round(bbox[3] * self._psd.height)),
                )
            else:
                self._bbox = (0, 0, 0, 0)
            assert self._bbox is not None
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
