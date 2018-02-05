# -*- coding: utf-8 -*-
"""Shape layer API."""

from __future__ import absolute_import
import inspect
import logging
from psd_tools.constants import TaggedBlock

logger = logging.getLogger(__name__)


class StrokeStyle(object):
    def __init__(self, descriptor):
        self._descriptor = descriptor
        assert self.get(b'classID') == b'strokeStyle'

    def get(self, key, default=None):
        return self._descriptor.get(key, default)

    @property
    def stroke_enabled(self):
        return self.get(b'strokeEnabled')

    @property
    def fill_enabled(self):
        return self.get(b'fillEnabled')

    @property
    def line_width(self):
        return self.get(b'strokeStyleLineWidth')

    @property
    def line_dash_set(self):
        return self.get(b'strokeStyleLineDashSet')

    @property
    def line_dash_offset(self):
        return self.get(b'strokeStyleLineDashOffset', 0)

    @property
    def miter_limit(self):
        return self.get(b'strokeStyleMiterLimit')

    @property
    def line_cap_type(self):
        return self.get(b'strokeStyleLineCapType')

    @property
    def line_join_type(self):
        return self.get(b'strokeStyleLineJoinType')

    @property
    def line_alignment(self):
        return self.get(b'strokeStyleLineAlignment')

    @property
    def scale_lock(self):
        return self.get(b'strokeStyleScaleLock')

    @property
    def stroke_adjust(self):
        return self.get(b'strokeStyleStrokeAdjust')

    @property
    def blend_mode(self):
        return self.get(b'strokeStyleBlendMode')

    @property
    def opacity(self):
        return self.get(b'strokeStyleOpacity')

    @property
    def content(self):
        return self.get(b'strokeStyleContent')

    def __repr__(self):
        return self._descriptor.__repr__()
