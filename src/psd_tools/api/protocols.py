"""
Protocol definitions for type hints to avoid circular imports.

This module defines Protocol classes that specify the interfaces for Layer and
PSDImage without requiring concrete imports. These protocols allow other modules
to properly type hint their parameters while avoiding circular dependency issues.
"""

from typing import Any, Callable, Iterator, Literal, Optional, Protocol, Union

try:
    from typing import Self
except ImportError:
    from typing_extensions import Self

import numpy as np
from PIL.Image import Image as PILImage

from psd_tools.constants import BlendMode, ChannelID
from psd_tools.psd.layer_and_mask import ChannelDataList, ChannelInfo, LayerRecord
from psd_tools.psd.tagged_blocks import TaggedBlocks


class LayerProtocol(Protocol):
    """
    Protocol defining the Layer interface for type checking.

    This protocol specifies the public interface that all Layer objects must
    implement. It's used by other modules (mask, effects, smart_object, etc.)
    to properly type hint their layer parameters without importing the concrete
    Layer class.
    """

    # Internal attributes accessed by related classes
    # Note: _psd uses Any to allow both PSDImage and PSDProtocol without conflicts
    _record: LayerRecord
    _channels: ChannelDataList
    _psd: Optional[Any]

    @property
    def name(self) -> str:
        """Layer name."""
        ...

    @name.setter
    def name(self, value: str) -> None:
        ...

    @property
    def kind(self) -> str:
        """
        Kind of this layer, such as group, pixel, shape, type, smartobject,
        or psdimage.
        """
        ...

    @property
    def layer_id(self) -> int:
        """Layer ID."""
        ...

    @property
    def visible(self) -> bool:
        """Layer visibility. Doesn't take group visibility into account."""
        ...

    @visible.setter
    def visible(self, value: bool) -> None:
        ...

    def is_visible(self) -> bool:
        """Layer visibility. Takes group visibility into account."""
        ...

    @property
    def opacity(self) -> int:
        """Opacity of this layer in [0, 255] range."""
        ...

    @opacity.setter
    def opacity(self, value: int) -> None:
        ...

    @property
    def parent(self) -> Optional[Any]:
        """Parent of this layer (GroupMixin-like object)."""
        ...

    def is_group(self) -> bool:
        """Return True if the layer is a group."""
        ...

    @property
    def blend_mode(self) -> BlendMode:
        """Blend mode of this layer."""
        ...

    @blend_mode.setter
    def blend_mode(self, value: Union[bytes, str, BlendMode]) -> None:
        ...

    @property
    def left(self) -> int:
        """Left coordinate."""
        ...

    @left.setter
    def left(self, value: int) -> None:
        ...

    @property
    def top(self) -> int:
        """Top coordinate."""
        ...

    @top.setter
    def top(self, value: int) -> None:
        ...

    @property
    def right(self) -> int:
        """Right coordinate."""
        ...

    @property
    def bottom(self) -> int:
        """Bottom coordinate."""
        ...

    @property
    def width(self) -> int:
        """Width of the layer."""
        ...

    @property
    def height(self) -> int:
        """Height of the layer."""
        ...

    @property
    def offset(self) -> tuple[int, int]:
        """(left, top) tuple."""
        ...

    @offset.setter
    def offset(self, value: tuple[int, int]) -> None:
        ...

    @property
    def size(self) -> tuple[int, int]:
        """(width, height) tuple."""
        ...

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """(left, top, right, bottom) tuple."""
        ...

    @property
    def tagged_blocks(self) -> TaggedBlocks:
        """Tagged blocks associated with this layer."""
        ...

    def has_pixels(self) -> bool:
        """Returns True if the layer has associated pixels."""
        ...

    def has_mask(self) -> bool:
        """Returns True if the layer has a mask."""
        ...

    @property
    def mask(self) -> Optional[Any]:
        """
        Returns mask associated with this layer.

        :return: Mask object or None
        """
        ...

    def has_vector_mask(self) -> bool:
        """Returns True if the layer has a vector mask."""
        ...

    def topil(
        self, channel: Optional[int] = None, apply_icc: bool = True
    ) -> Optional[PILImage]:
        """
        Get PIL Image of the layer.

        :param channel: Which channel to return.
        :param apply_icc: Whether to apply ICC profile conversion to sRGB.
        :return: PIL Image object, or None if the layer has no pixels.
        """
        ...

    def numpy(
        self, channel: Optional[str] = None, real_mask: bool = True
    ) -> Optional[np.ndarray]:
        """
        Get NumPy array of the layer.

        :param channel: Which channel to return.
        :param real_mask: Whether to use real mask.
        :return: NumPy array.
        """
        ...

    def composite(
        self,
        viewport: Optional[tuple[int, int, int, int]] = None,
        force: bool = False,
        color: Union[float, tuple[float, ...], np.ndarray] = 1.0,
        alpha: Union[float, np.ndarray] = 0.0,
        layer_filter: Optional[Callable] = None,
        apply_icc: bool = True,
    ) -> Optional[PILImage]:
        """
        Composite the layer.

        :param viewport: Viewport bounding box.
        :param force: Force vector drawing.
        :param color: Backdrop color (float, tuple, or ndarray).
        :param alpha: Backdrop alpha (float or ndarray).
        :param layer_filter: Layer filter callable.
        :param apply_icc: Whether to apply ICC profile conversion.
        :return: PIL Image, or None if composition not available.
        """
        ...


class GroupMixinProtocol(Protocol):
    """
    Protocol defining the GroupMixin interface.

    This protocol is used for objects that behave like groups (can contain
    child layers). Both Group layers and PSDImage implement this protocol.
    """

    def __len__(self) -> int:
        """Number of child layers."""
        ...

    def __iter__(self) -> Iterator[LayerProtocol]:
        """Iterate over child layers."""
        ...

    def __getitem__(self, index: int) -> LayerProtocol:
        """Get child layer by index."""
        ...

    def is_visible(self) -> bool:
        """Returns visibility of the element."""
        ...

    def is_group(self) -> bool:
        """Return True if this is a group."""
        ...

    @property
    def parent(self) -> Optional[Any]:
        """Parent of this group (GroupMixin-like object or None)."""
        ...

    def descendants(
        self, include_clip: bool = True
    ) -> Iterator[LayerProtocol]:
        """
        Return a generator to iterate over all descendant layers.

        :param include_clip: Whether to include clip layers.
        :return: Iterator of layers.
        """
        ...


class PSDProtocol(GroupMixinProtocol, Protocol):
    """
    Protocol defining the PSDImage interface for type checking.

    This protocol specifies the public interface that PSDImage objects must
    implement. It's used by other modules to properly type hint their psd
    parameters without importing the concrete PSDImage class.

    Note: PSDImage implements GroupMixin, so this protocol extends
    GroupMixinProtocol.
    """

    # Internal attributes accessed by related classes
    _record: Any  # psd_tools.psd.PSD

    @property
    def name(self) -> str:
        """Document name."""
        ...

    @property
    def kind(self) -> str:
        """Return 'psdimage'."""
        ...

    @property
    def width(self) -> int:
        """Width of the document."""
        ...

    @property
    def height(self) -> int:
        """Height of the document."""
        ...

    @property
    def size(self) -> tuple[int, int]:
        """(width, height) tuple."""
        ...

    @property
    def depth(self) -> int:
        """Depth of the document (8, 16, or 32 bits)."""
        ...

    @property
    def channels(self) -> int:
        """Number of color channels."""
        ...

    @property
    def color_mode(self) -> Any:  # ColorMode enum
        """Color mode of the document."""
        ...

    @property
    def version(self) -> int:
        """Version of the PSD file (1 for PSD, 2 for PSB)."""
        ...

    @property
    def image_resources(self) -> Any:  # ImageResources
        """Image resources section."""
        ...

    @property
    def tagged_blocks(self) -> TaggedBlocks:
        """Tagged blocks associated with the document."""
        ...

    @property
    def visible(self) -> bool:
        """Visibility of the document."""
        ...

    def has_preview(self) -> bool:
        """Returns if the document has real merged data."""
        ...

    def is_updated(self) -> bool:
        """Returns whether the layer tree has been updated."""
        ...

    def _mark_updated(self) -> None:
        """Mark the layer tree as updated."""
        ...

    def topil(
        self, channel: Union[int, ChannelID, None] = None, apply_icc: bool = True
    ) -> Optional[PILImage]:
        """
        Get PIL Image of the document.

        :param channel: Which channel to return.
        :param apply_icc: Whether to apply ICC profile conversion to sRGB.
        :return: PIL Image object, or None if not available.
        """
        ...

    def numpy(
        self, channel: Optional[Literal["color", "shape", "alpha", "mask"]] = None
    ) -> np.ndarray:
        """
        Get NumPy array of the document.

        :param channel: Which channel to return.
        :return: NumPy array.
        """
        ...

    def composite(
        self,
        viewport: Optional[tuple[int, int, int, int]] = None,
        force: bool = False,
        color: Union[float, tuple[float, ...], np.ndarray, None] = 1.0,
        alpha: Union[float, np.ndarray] = 0.0,
        layer_filter: Optional[Callable] = None,
        ignore_preview: bool = False,
        apply_icc: bool = True,
    ) -> PILImage:
        """
        Composite the PSD document.

        :param viewport: Viewport bounding box.
        :param force: Force vector drawing.
        :param color: Backdrop color.
        :param alpha: Backdrop alpha.
        :param layer_filter: Layer filter callable.
        :param ignore_preview: Whether to skip using pre-composed preview.
        :param apply_icc: Whether to apply ICC profile conversion.
        :return: PIL Image.
        """
        ...
