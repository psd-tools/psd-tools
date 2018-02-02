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
    def stroke_style_line_width(self):
        return self.get(b'strokeStyleLineWidth')

    @property
    def stroke_style_line_dash_offset(self):
        return self.get(b'strokeStyleLineDashOffset')

    @property
    def stroke_style_miter_limit(self):
        return self.get(b'strokeStyleMiterLimit')

    @property
    def stroke_style_line_cap_type(self):
        return self.get(b'strokeStyleLineCapType')

    @property
    def stroke_style_line_cap_type(self):
        return self.get(b'strokeStyleLineCapType')

    @property
    def stroke_style_line_join_type(self):
        return self.get(b'strokeStyleLineJoinType')

    @property
    def stroke_style_line_alignment(self):
        return self.get(b'strokeStyleLineAlignment')

    @property
    def stroke_style_scale_lock(self):
        return self.get(b'strokeStyleScaleLock')

    @property
    def stroke_style_stroke_adjust(self):
        return self.get(b'strokeStyleStrokeAdjust')

    @property
    def stroke_style_line_dash_set(self):
        return self.get(b'strokeStyleLineDashSet')

    @property
    def stroke_style_blend_mode(self):
        return self.get(b'strokeStyleBlendMode')

    @property
    def stroke_style_opacity(self):
        return self.get(b'strokeStyleOpacity')

    @property
    def stroke_style_content(self):
        return self.get(b'strokeStyleContent')

    def __repr__(self):
        return __repr__(self._descriptor)
