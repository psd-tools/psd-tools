"""
Mask module.
"""

import logging
from typing import Any

from PIL.Image import Image as PILImage

from psd_tools.constants import ChannelID
from psd_tools.psd.layer_and_mask import MaskData, MaskFlags

logger = logging.getLogger(__name__)


class Mask(object):
    """Mask data attached to a layer.

    There are two distinct internal mask data: user mask and vector mask.
    User mask refers any pixel-based mask whereas vector mask refers a mask
    from a shape path. Internally, two masks are combined and referred
    real mask.
    """

    def __init__(self, layer: Any):  # TODO: Circular import
        self._layer = layer
        self._data: MaskData = layer._record.mask_data

    @property
    def background_color(self) -> int:
        """Background color."""
        if self._has_real():
            return self._data.real_background_color
        return self._data.background_color

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """BBox"""
        return self.left, self.top, self.right, self.bottom

    @property
    def left(self) -> int:
        """Left coordinate."""
        if self._has_real():
            return self._data.real_left
        return self._data.left

    @property
    def right(self) -> int:
        """Right coordinate."""
        if self._has_real():
            return self._data.real_right
        return self._data.right

    @property
    def top(self) -> int:
        """Top coordinate."""
        if self._has_real():
            return self._data.real_top
        return self._data.top

    @property
    def bottom(self) -> int:
        """Bottom coordinate."""
        if self._has_real():
            return self._data.real_bottom
        return self._data.bottom

    @property
    def width(self) -> int:
        """Width."""
        return self.right - self.left

    @property
    def height(self) -> int:
        """Height."""
        return self.bottom - self.top

    @property
    def size(self) -> tuple[int, int]:
        """(Width, Height) tuple."""
        return self.width, self.height

    @property
    def disabled(self) -> bool:
        """Disabled."""
        return self._data.flags.mask_disabled

    @property
    def flags(self) -> MaskFlags:
        """Flags."""
        return self._data.flags

    @property
    def parameters(self):
        """Parameters."""
        return self._data.parameters

    @property
    def real_flags(self) -> MaskFlags | None:
        """Real flag."""
        return self._data.real_flags

    def _has_real(self) -> bool:
        """Return True if the mask has real flags."""
        return self.real_flags is not None and self.real_flags.parameters_applied

    def topil(self, real: bool=True, **kwargs: Any) -> PILImage | None:
        """
        Get PIL Image of the mask.

        :param real: When True, returns pixel + vector mask combined.
        :return: PIL Image object, or None if the mask is empty.
        """
        if real and self._has_real():
            channel = ChannelID.REAL_USER_LAYER_MASK
        else:
            channel = ChannelID.USER_LAYER_MASK
        return self._layer.topil(channel, **kwargs)

    def __repr__(self) -> str:
        return "%s(offset=(%d,%d) size=%dx%d)" % (
            self.__class__.__name__,
            self.left,
            self.top,
            self.width,
            self.height,
        )
