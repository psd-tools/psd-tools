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


class VectorMask(object):
    def __init__(self, setting):
        self._setting = setting

    @property
    def invert(self):
        return self._setting.invert

    @property
    def not_link(self):
        return self._setting.not_link

    @property
    def disable(self):
        return self._setting.disable

    @property
    def path(self):
        return self._setting.path

    @property
    def initial_fill_rule(self):
        for p in self.path:
            if p.get('selector') == PathResource.INITIAL_FILL_RULE_RECORD:
                return p.get('initial_fill_rule', 0)
        return 0

    @property
    def num_knots(self):
        keys = {
            PathResource.OPEN_SUBPATH_LENGTH_RECORD,
            PathResource.CLOSED_SUBPATH_LENGTH_RECORD,
        }
        for p in self.path:
            if p.get('selector') in keys:
                return p.get('num_knot_records', 0)
        return 0

    @property
    def closed(self):
        for p in self.path:
            if p.get('selector') in PathResource.CLOSED_SUBPATH_LENGTH_RECORD:
                return True
        return False

    @property
    def knots(self):
        keys = (
            PathResource.CLOSED_SUBPATH_BEZIER_KNOT_LINKED,
            PathResource.CLOSED_SUBPATH_BEZIER_KNOT_UNLINKED,
            PathResource.OPEN_SUBPATH_BEZIER_KNOT_LINKED,
            PathResource.OPEN_SUBPATH_BEZIER_KNOT_UNLINKED
        )
        return [p for p in self.path if p.get('selector') in keys]

    @property
    def anchors(self):
        return [p.get('anchor') for p in self.knots]
