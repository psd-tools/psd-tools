# -*- coding: utf-8 -*-
"""Shape layer API."""

from __future__ import absolute_import
import logging
from psd_tools.debug import pretty_namedtuple
from psd_tools.constants import TaggedBlock, PathResource

logger = logging.getLogger(__name__)


class StrokeStyle(object):
    """StrokeStyle contains decorative infromation for strokes."""
    STROKE_STYLE_LINE_CAP_TYPES = {
        b'strokeStyleButtCap': 'butt',
        b'strokeStyleRoundCap': 'round',
        b'strokeStyleSquareCap': 'square',
    }

    STROKE_STYLE_LINE_JOIN_TYPES = {
        b'strokeStyleMiterJoin': 'miter',
        b'strokeStyleRoundJoin': 'round',
        b'strokeStyleBevelJoin': 'bevel',
    }

    STROKE_STYLE_LINE_ALIGNMENTS = {
        b'strokeStyleAlignInside': 'inner',
        b'strokeStyleAlignOutside': 'outer',
        b'strokeStyleAlignCenter': 'center',
    }

    def __init__(self, descriptor):
        self._descriptor = descriptor
        assert self.get(b'classID') == b'strokeStyle'

    def get(self, key, default=None):
        return self._descriptor.get(key, default)

    @property
    def enabled(self):
        """If the stroke is enabled."""
        return self.get(b'strokeEnabled')

    @property
    def fill_enabled(self):
        """If the stroke fill is enabled."""
        return self.get(b'fillEnabled')

    @property
    def line_width(self):
        """Stroke width in float."""
        return self.get(b'strokeStyleLineWidth', 1.0)

    @property
    def line_dash_set(self):
        """
        Line dash set in list of float.

        :rtype: list
        """
        return self.get(b'strokeStyleLineDashSet')

    @property
    def line_dash_offset(self):
        """
        Line dash offset in float.

        :rtype: float
        """
        return self.get(b'strokeStyleLineDashOffset', 0.0)

    @property
    def miter_limit(self):
        """Miter limit in float."""
        return self.get(b'strokeStyleMiterLimit')

    @property
    def line_cap_type(self):
        """Cap type, one of `butt`, `round`, `square`."""
        key = self.get(b'strokeStyleLineCapType')
        return self.STROKE_STYLE_LINE_CAP_TYPES.get(key, str(key))

    @property
    def line_join_type(self):
        """Join type, one of `miter`, `round`, `bevel`."""
        key =  self.get(b'strokeStyleLineJoinType')
        return self.STROKE_STYLE_LINE_JOIN_TYPES.get(key, str(key))

    @property
    def line_alignment(self):
        """Alignment, one of `inner`, `outer`, `center`."""
        key =  self.get(b'strokeStyleLineAlignment')
        return self.STROKE_STYLE_LINE_ALIGNMENTS.get(key, str(key))

    @property
    def scale_lock(self):
        return self.get(b'strokeStyleScaleLock')

    @property
    def stroke_adjust(self):
        """Stroke adjust"""
        return self.get(b'strokeStyleStrokeAdjust')

    @property
    def blend_mode(self):
        """Blend mode."""
        return self.get(b'strokeStyleBlendMode')

    @property
    def opacity(self):
        """Opacity from 0 to 100."""
        return self.get(b'strokeStyleOpacity', 100)

    @property
    def content(self):
        """
        Fill effect, one of
        :py:class:`~psd_tools.user_api.effects.ColorOverlay`,
        :py:class:`~psd_tools.user_api.effects.PatternOverlay`,
        or :py:class:`~psd_tools.user_api.effects.GradientOverlay`.

        :rtype: :py:class:`~psd_tools.user_api.effects._OverlayEffect`
        """
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
        """Invert the mask."""
        return self._setting.invert

    @property
    def not_link(self):
        """If the knots are not linked."""
        return self._setting.not_link

    @property
    def disabled(self):
        """If the mask is disabled."""
        return self._setting.disable

    @property
    def paths(self):
        """
        List of `Path`. Path contains `closed`, `num_knots`, and `knots`.

        :rtype: Path
        """
        return self._paths

    @property
    def initial_fill_rule(self):
        """
        Initial fill rule.

        When 0, fill inside of the path. When 1, fill outside of the shape.
        """
        return self._initial_fill_rule

    @property
    def anchors(self):
        """List of vertices of all subpaths."""
        return [p['anchor'] for p in self._setting.path
                if p.get('selector') in self._KNOT_KEYS]
