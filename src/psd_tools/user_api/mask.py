# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, print_function

from psd_tools.user_api import pil_support
from psd_tools.user_api.psd_image import BBox


class Mask(object):
    """Mask data attached to a layer."""
    def __init__(self, layer):
        self.mask_data = layer._record.mask_data
        self._decoded_data = layer._psd.decoded_data
        self._layer_index = layer._index

    @property
    def background_color(self):
        """Background color."""
        return self.get_background_color()

    def get_background_color(self, real=True):
        """Get background color."""
        if real and self.mask_data.real_background_color:
            return self.mask_data.real_background_color
        return self.mask_data.background_color

    @property
    def bbox(self):
        """BBox"""
        return self.get_bbox()

    @property
    def left(self):
        """Left coordinate."""
        if self.mask_data.real_flags:
            return self.mask_data.real_left
        return self.mask_data.left

    @property
    def right(self):
        """Right coordinate."""
        if self.mask_data.real_flags:
            return self.mask_data.real_right
        return self.mask_data.right

    @property
    def top(self):
        """Top coordinate."""
        if self.mask_data.real_flags:
            return self.mask_data.real_top
        return self.mask_data.top

    @property
    def bottom(self):
        """Bottom coordinate."""
        if self.mask_data.real_flags:
            return self.mask_data.real_bottom
        return self.mask_data.bottom

    @property
    def width(self):
        """Width."""
        return self.right - self.left

    @property
    def height(self):
        """Height."""
        return self.bottom - self.top

    @property
    def disabled(self):
        """Height."""
        return self.mask_data.flags.mask_disabled

    def get_bbox(self, real=True):
        """
        Get BBox(x1, y1, x2, y2) namedtuple with mask bounding box.

        :param real: When False, ignore real flags.
        """
        if real and self.mask_data.real_flags:
            return BBox(self.mask_data.real_left, self.mask_data.real_top,
                        self.mask_data.real_right, self.mask_data.real_bottom)
        else:
            return BBox(self.mask_data.left, self.mask_data.top,
                        self.mask_data.right, self.mask_data.bottom)

    def has_box(self):
        """Return True if the mask has a valid bbox."""
        return self.width > 0 and self.height > 0

    def is_valid(self):
        """(Deprecated) Use `has_box`"""
        return self.has_box()

    def as_PIL(self, real=True):
        """
        Returns a PIL image for the mask.

        If ``real`` is True, extract real mask consisting of both bitmap
        and vector mask.

        Returns ``None`` if the mask has zero size.
        """
        if not self.has_box():
            return None
        return pil_support.extract_layer_mask(self._decoded_data,
                                              self._layer_index,
                                              real)

    def __repr__(self):
        return "<%s: size=%dx%d, x=%d, y=%d>" % (
            self.__class__.__name__.lower(), self.width, self.height,
            self.left, self.right)
