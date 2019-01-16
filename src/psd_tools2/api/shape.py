"""
Shape module.
"""

from __future__ import absolute_import
import logging

from psd_tools2.psd.vector import (
    Subpath, PathFillRule, InitialFillRule, ClipboardRecord
)

logger = logging.getLogger(__name__)


class VectorMask(object):
    """Shape path data."""

    def __init__(self, data):
        self._data = data
        self._build()

    def _build(self):
        self._paths = []
        self._clipboard_record = None
        self._initial_fill_rule = None
        for x in self._data.path:
            if isinstance(x, InitialFillRule):
                self._initial_fill_rule = x
            elif isinstance(x, ClipboardRecord):
                self._clipboard_record = x
            elif isinstance(x, Subpath):
                self._paths.append(x)

    @property
    def inverted(self):
        """Invert the mask."""
        return self._data.invert

    @property
    def not_linked(self):
        """If the knots are not linked."""
        return self._data.not_link

    @property
    def disabled(self):
        """If the mask is disabled."""
        return self._data.disable

    @property
    def paths(self):
        """
        List of :py:class:`~psd_tools2.psd.vector.Subpath`. Subpath is a
        list-like structure that contains one or more
        :py:class:`~psd_tools2.psd.vector.Knot` items. Knot contains
        relative coordinates of control points for a Bezier curve.

        In PSD, path fill rule is even-odd.

        :return: List of Subpath.
        """
        return self._paths

    @property
    def initial_fill_rule(self):
        """
        Initial fill rule.

        When 0, fill inside of the path. When 1, fill outside of the shape.
        """
        return self._initial_fill_rule.value

    @initial_fill_rule.setter
    def initial_fill_rule(self, value):
        assert value in (0, 1)
        self._initial_fill_rule.value = value

    @property
    def clipboard_record(self):
        """
        Clipboard record containing bounding box information.

        Depending on the Photoshop version, this field can be `None`.
        """
        return self._clipboard_record

    def __repr__(self):
        return '%s(paths=%d%s)' % (
            self.__class__.__name__,
            len(self.paths),
            ' disabled' if self.disabled else '',
        )


class Stroke(object):
    """
    Stroke contains decorative infromation for strokes.

    This is a thin wrapper around
    :py:class:`~psd_tools2.psd.descriptor.Descriptor` structure.
    Check `_data` attribute to get the raw data.
    """
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

    def __init__(self, data):
        self._data = data
        assert self._data.classID == b'strokeStyle'

    @property
    def enabled(self):
        """If the stroke is enabled."""
        return bool(self._data.get(b'strokeEnabled'))

    @property
    def fill_enabled(self):
        """If the stroke fill is enabled."""
        return bool(self._data.get(b'fillEnabled'))

    @property
    def line_width(self):
        """Stroke width in float."""
        return self._data.get(b'strokeStyleLineWidth')

    @property
    def line_dash_set(self):
        """
        Line dash set in list of
        :py:class:`~psd_tools.decoder.actions.UnitFloat`.

        :rtype: list
        """
        return self._data.get(b'strokeStyleLineDashSet')

    @property
    def line_dash_offset(self):
        """
        Line dash offset in float.

        :rtype: float
        """
        return self._data.get(b'strokeStyleLineDashOffset')

    @property
    def miter_limit(self):
        """Miter limit in float."""
        return self._data.get(b'strokeStyleMiterLimit')

    @property
    def line_cap_type(self):
        """Cap type, one of `butt`, `round`, `square`."""
        key = self._data.get(b'strokeStyleLineCapType').enum
        return self.STROKE_STYLE_LINE_CAP_TYPES.get(key, str(key))

    @property
    def line_join_type(self):
        """Join type, one of `miter`, `round`, `bevel`."""
        key = self._data.get(b'strokeStyleLineJoinType').enum
        return self.STROKE_STYLE_LINE_JOIN_TYPES.get(key, str(key))

    @property
    def line_alignment(self):
        """Alignment, one of `inner`, `outer`, `center`."""
        key = self._data.get(b'strokeStyleLineAlignment').enum
        return self.STROKE_STYLE_LINE_ALIGNMENTS.get(key, str(key))

    @property
    def scale_lock(self):
        return self._data.get(b'strokeStyleScaleLock')

    @property
    def stroke_adjust(self):
        """Stroke adjust"""
        return self._data.get(b'strokeStyleStrokeAdjust')

    @property
    def blend_mode(self):
        """Blend mode."""
        return self._data.get(b'strokeStyleBlendMode').enum

    @property
    def opacity(self):
        """Opacity value."""
        return self._data.get(b'strokeStyleOpacity')

    @property
    def content(self):
        """
        Fill effect.
        """
        return self._data.get(b'strokeStyleContent')

    def __repr__(self):
        return '%s(width=%g)' % (
            self.__class__.__name__, self.line_width
        )


class Origination(object):
    """
    Vector origination.

    Vector origination keeps live shape properties for some of the primitive
    shapes.
    """
    @classmethod
    def create(kls, data):
        origin_type = data.get(b'keyDescriptorList')[0].get(b'keyOriginType')
        types = {1: Rectangle, 2: RoundedRectangle, 4: Line, 5: Ellipse}
        return types.get(origin_type, kls)(data)

    def __init__(self, data):
        # Seems currently only one item is present in the list.
        self._data = data.get(b'keyDescriptorList')[0]

    @property
    def origin_type(self):
        """
        Type of the vector shape.

        * 1: rectangle
        * 2: rounded rectangle
        * 4: line
        * 5: ellipse
        """
        return self._data.get(b'keyOriginType')

    @property
    def resolution(self):
        """Resolution.
        """
        return self._data.get(b'keyOriginResolution')

    @property
    def shape_bbox(self):
        """
        Bounding box of the live shape.

        :rtype: :py:class:`~psd_tools2.psd.descriptor.Descriptor`
        """
        return self._data.get(b'keyOriginShapeBBox')

    @property
    def index(self):
        """

        :rtype: int
        """
        return self._data.get(b'keyOriginIndex')

    def __repr__(self):
        bbox = self.shape_bbox
        return '%s(bbox=(%g, %g, %g, %g), resolution=%g)' % (
            self.__class__.__name__,
            bbox.get(b'Top '),
            bbox.get(b'Left'),
            bbox.get(b'Btom'),
            bbox.get(b'Rght'),
            self.resolution
        )


class Rectangle(Origination):
    """Rectangle live shape."""
    pass


class Ellipse(Origination):
    """Ellipse live shape."""
    pass


class RoundedRectangle(Origination):
    """Rounded rectangle live shape."""

    @property
    def radii(self):
        """
        Corner radii of rounded rectangles.
        The order is top-left, top-right, bottom-left, bottom-right.

        :rtype: :py:class:`~psd_tools2.psd.descriptor.Descriptor`
        """
        return self._data.get(b'keyOriginRRectRadii')


class Line(Origination):
    """Line live shape."""

    @property
    def line_end(self):
        """Line end.

        :rtype: :py:class:`~psd_tools2.psd.descriptor.Descriptor`
        """
        return self._data.get(b'keyOriginLineEnd')

    @property
    def line_start(self):
        """Line start.

        :rtype: :py:class:`~psd_tools2.psd.descriptor.Descriptor`
        """
        return self._data.get(b'keyOriginLineStart')

    @property
    def line_weight(self):
        """Line weight

        :rtype: float
        """
        return self._data.get(b'keyOriginLineWeight')

    @property
    def arrow_start(self):
        """Line arrow start.

        :rtype: bool
        """
        return bool(self._data.get(b'keyOriginLineArrowSt'))

    @property
    def arrow_end(self):
        """Line arrow end.

        :rtype: bool"""
        return bool(self._data.get(b'keyOriginLineArrowEnd'))

    @property
    def arrow_width(self):
        """Line arrow width.

        :rtype: float
        """
        return self._data.get(b'keyOriginLineArrWdth')

    @property
    def arrow_length(self):
        """Line arrow length.

        :rtype: float
        """
        return self._data.get(b'keyOriginLineArrLngth')

    @property
    def arrow_conc(self):
        """

        :rtype: int
        """
        return self._data.get(b'keyOriginLineArrConc')
