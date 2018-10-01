# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, print_function

import logging
from collections import namedtuple

logger = logging.getLogger(__name__)


class BBox(namedtuple('BBox', 'x1, y1, x2, y2')):
    """
    Bounding box tuple representing (x1, y1, x2, y2).
    """
    @property
    def width(self):
        """Width of the bounding box."""
        return self.x2 - self.x1

    @property
    def height(self):
        """Height of the bounding box."""
        return self.y2 - self.y1

    @property
    def left(self):
        """Alias of x1."""
        return self.x1

    @property
    def right(self):
        """Alias of x2."""
        return self.x2

    @property
    def top(self):
        """Alias of y1."""
        return self.y1

    @property
    def bottom(self):
        """Alias of y2."""
        return self.y2

    def is_empty(self):
        """Return True if the box does not have an area."""
        return self.width <= 0 or self.height <= 0

    def intersect(self, bbox):
        """Intersect of two bounding boxes."""
        return BBox(max(self.x1, bbox.x1),
                    max(self.y1, bbox.y1),
                    min(self.x2, bbox.x2),
                    min(self.y2, bbox.y2))

    def union(self, bbox):
        """Union of two boxes."""
        return BBox(min(self.x1, bbox.x1),
                    min(self.y1, bbox.y1),
                    max(self.x2, bbox.x2),
                    max(self.y2, bbox.y2))

    def offset(self, point):
        """Subtract offset point from the bounding box."""
        return BBox(self.x1 - point[0], self.y1 - point[1],
                    self.x2 - point[0], self.y2 - point[1])


class Pattern(object):
    """Pattern data."""
    def __init__(self, pattern):
        self._pattern = pattern

    @property
    def pattern_id(self):
        """Pattern UUID."""
        return self._pattern.pattern_id

    @property
    def name(self):
        """Name of the pattern."""
        return self._pattern.name

    @property
    def width(self):
        """Width of the pattern."""
        return self._pattern.point[1]

    @property
    def height(self):
        """Height of the pattern."""
        return self._pattern.point[0]

    def as_PIL(self):
        """Returns a PIL image for this pattern."""
        return pil_support.pattern_to_PIL(self._pattern)

    def __repr__(self):
        return "<%s: name='%s' size=%dx%d>" % (
            self.__class__.__name__.lower(), self.name, self.width,
            self.height)
