# -*- coding: utf-8 -*-
"""Shape layer API."""

from __future__ import absolute_import
import logging
from psd_tools.debug import pretty_namedtuple
from psd_tools.constants import TaggedBlock, PathResource

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


Path = pretty_namedtuple("Path", "closed num_knots knots")
Knot = pretty_namedtuple("Knot", "anchor leaving_knot preceding_knot")


class VectorMask(object):
    """Shape path data."""
    _KNOT_KEYS = (
        PathResource.CLOSED_SUBPATH_BEZIER_KNOT_LINKED,
        PathResource.CLOSED_SUBPATH_BEZIER_KNOT_UNLINKED,
        PathResource.OPEN_SUBPATH_BEZIER_KNOT_LINKED,
        PathResource.OPEN_SUBPATH_BEZIER_KNOT_UNLINKED,
    )

    def __init__(self, setting):
        self._setting = setting
        self._paths = []
        self._build()

    def _build(self):
        for p in self._setting.path:
            selector = p.get('selector')
            if selector == PathResource.CLOSED_SUBPATH_LENGTH_RECORD:
                self._paths.append(Path(True, p.get('num_knot_records'), []))
            elif selector == PathResource.OPEN_SUBPATH_LENGTH_RECORD:
                self._paths.append(Path(False, p.get('num_knot_records'), []))
            elif selector in self._KNOT_KEYS:
                knot = Knot(p.get('anchor'),
                            p.get('control_leaving_knot'),
                            p.get('control_preceding_knot'))
                self._paths[-1].knots.append(knot)
            elif selector == PathResource.PATH_FILL_RULE_RECORD:
                pass
            elif selector == PathResource.CLIPBOARD_RECORD:
                self._clipboard_record = p
            elif selector == PathResource.INITIAL_FILL_RULE_RECORD:
                self._initial_fill_rule = p.get('initial_fill_rule', 0)
        for path in self.paths:
            assert path.num_knots == len(path.knots)

    @property
    def invert(self):
        return self._setting.invert

    @property
    def not_link(self):
        return self._setting.not_link

    @property
    def disabled(self):
        return self._setting.disable

    @property
    def paths(self):
        return self._paths

    @property
    def initial_fill_rule(self):
        return self._initial_fill_rule

    @property
    def anchors(self):
        return [p['anchor'] for p in self._setting.path
                if p.get('selector') in self._KNOT_KEYS]
