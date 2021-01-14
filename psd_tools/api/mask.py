"""
Mask module.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools.api.pil_io import convert_mask_to_pil

logger = logging.getLogger(__name__)


class Mask(object):
    """Mask data attached to a layer.

    There are two distinct internal mask data: user mask and vector mask.
    User mask refers any pixel-based mask whereas vector mask refers a mask
    from a shape path. Internally, two masks are combined and referred
    real mask.
    """
    def __init__(self, layer):
        self._layer = layer
        self._data = layer._record.mask_data

    @property
    def background_color(self):
        """Background color."""
        if self._has_real():
            return self._data.real_background_color
        return self._data.background_color

    @property
    def bbox(self):
        """BBox"""
        return self.left, self.top, self.right, self.bottom

    @property
    def left(self):
        """Left coordinate."""
        if self._has_real():
            return self._data.real_left
        return self._data.left

    @property
    def right(self):
        """Right coordinate."""
        if self._has_real():
            return self._data.real_right
        return self._data.right

    @property
    def top(self):
        """Top coordinate."""
        if self._has_real():
            return self._data.real_top
        return self._data.top

    @property
    def bottom(self):
        """Bottom coordinate."""
        if self._has_real():
            return self._data.real_bottom
        return self._data.bottom

    @property
    def width(self):
        """Width."""
        return self.right - self.left

    @property
    def height(self):
        """Height."""
        return self.bottom - self.top

    @property
    def size(self):
        """(Width, Height) tuple."""
        return self.width, self.height

    @property
    def disabled(self):
        """Disabled."""
        return self._data.flags.mask_disabled

    @property
    def flags(self):
        """Flags."""
        return self._data.flags

    @property
    def parameters(self):
        """Parameters."""
        return self._data.parameters

    @property
    def real_flags(self):
        """Real flag."""
        return self._data.real_flags

    def _has_real(self):
        """Return True if the mask has real flags."""
        return (
            self.real_flags is not None and self.real_flags.parameters_applied
        )

    def topil(self):
        """
        Get PIL Image of the mask.

        :return: PIL Image object, or None if the mask is empty.
        """
        if self.width == 0 or self.height == 0:
            return None
        return convert_mask_to_pil(self)

    def __repr__(self):
        return '%s(offset=(%d,%d) size=%dx%d)' % (
            self.__class__.__name__, self.left, self.top, self.width,
            self.height,
        )
