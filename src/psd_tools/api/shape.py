"""
Shape module.

In PSD/PSB, shapes are all represented as :py:class:`VectorMask` in each
layer, and optionally there might be :py:class:`Origination` object to control
live shape properties and :py:class:`Stroke` to specify how outline is
stylized.
"""

from __future__ import annotations

import logging
from typing import Literal

try:
    from typing import Self
except ImportError:
    from typing_extensions import Self

from psd_tools.psd.descriptor import Descriptor, DescriptorBlock2
from psd_tools.psd.vector import (
    ClipboardRecord,
    InitialFillRule,
    Subpath,
    VectorMaskSetting,
    VectorStrokeContentSetting,
)
from psd_tools.terminology import Event

logger = logging.getLogger(__name__)


class VectorMask(object):
    """
    Vector mask data.

    Vector mask is a resolution-independent mask that consists of one or more
    Path objects. In Photoshop, all the path objects are represented as
    Bezier curves. Check :py:attr:`~psd_tools.api.shape.VectorMask.paths`
    property for how to deal with path objects.
    """

    def __init__(self, data: VectorMaskSetting):
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
    def inverted(self) -> bool:
        """Invert the mask."""
        return self._data.invert

    @property
    def not_linked(self) -> bool:
        """If the knots are not linked."""
        return self._data.not_link

    @property
    def disabled(self) -> bool:
        """If the mask is disabled."""
        return self._data.disable

    @property
    def paths(self) -> list[Subpath]:
        """
        List of :py:class:`~psd_tools.psd.vector.Subpath`. Subpath is a
        list-like structure that contains one or more
        :py:class:`~psd_tools.psd.vector.Knot` items. Knot contains
        relative coordinates of control points for a Bezier curve.
        :py:attr:`~psd_tools.psd.vector.Subpath.index` indicates which
        origination item the subpath belongs, and
        :py:class:`~psd_tools.psd.vector.Subpath.operation` indicates how
        to combine multiple shape paths.

        In PSD, path fill rule is even-odd.

        Example::

            for subpath in layer.vector_mask.paths:
                anchors = [(
                    int(knot.anchor[1] * psd.width),
                    int(knot.anchor[0] * psd.height),
                ) for knot in subpath]

        :return: List of Subpath.
        """
        return self._paths

    @property
    def initial_fill_rule(self) -> int:
        """
        Initial fill rule.

        When 0, fill inside of the path. When 1, fill outside of the shape.

        :return: `int`
        """
        return self._initial_fill_rule.value

    @initial_fill_rule.setter
    def initial_fill_rule(self, value: Literal[0, 1]) -> None:
        assert value in (0, 1)
        self._initial_fill_rule.value = value

    @property
    def clipboard_record(self) -> ClipboardRecord | None:
        """
        Clipboard record containing bounding box information.

        Depending on the Photoshop version, this field can be `None`.
        """
        return self._clipboard_record

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """
        Bounding box tuple (left, top, right, bottom) in relative coordinates,
        where top-left corner is (0., 0.) and bottom-right corner is (1., 1.).

        :return: `tuple`
        """
        from itertools import chain

        knots = [
            (knot.anchor[1], knot.anchor[0]) for knot in chain.from_iterable(self.paths)
        ]
        if len(knots) == 0:
            return (0.0, 0.0, 1.0, 1.0)
        x, y = zip(*knots)
        return (min(x), min(y), max(x), max(y))

    def __repr__(self) -> str:
        bbox = self.bbox
        return "%s(bbox=(%g, %g, %g, %g) paths=%d%s)" % (
            self.__class__.__name__,
            bbox[0],
            bbox[1],
            bbox[2],
            bbox[3],
            len(self.paths),
            " disabled" if self.disabled else "",
        )


class Stroke(object):
    """
    Stroke contains decorative information for strokes.

    This is a thin wrapper around
    :py:class:`~psd_tools.psd.descriptor.Descriptor` structure.
    Check `_data` attribute to get the raw data.
    """

    STROKE_STYLE_LINE_CAP_TYPES = {
        b"strokeStyleButtCap": "butt",
        b"strokeStyleRoundCap": "round",
        b"strokeStyleSquareCap": "square",
    }

    STROKE_STYLE_LINE_JOIN_TYPES = {
        b"strokeStyleMiterJoin": "miter",
        b"strokeStyleRoundJoin": "round",
        b"strokeStyleBevelJoin": "bevel",
    }

    STROKE_STYLE_LINE_ALIGNMENTS = {
        b"strokeStyleAlignInside": "inner",
        b"strokeStyleAlignOutside": "outer",
        b"strokeStyleAlignCenter": "center",
    }

    def __init__(self, data: VectorStrokeContentSetting):
        self._data = data
        if self._data.classID not in (b"strokeStyle", Event.Stroke):
            logger.warning("Unknown class ID found: {!r}".format(self._data.classID))

    @property
    def enabled(self) -> bool:
        """If the stroke is enabled."""
        return bool(self._data.get(b"strokeEnabled"))

    @property
    def fill_enabled(self) -> bool:
        """If the stroke fill is enabled."""
        return bool(self._data.get(b"fillEnabled"))

    @property
    def line_width(self) -> float:
        """Stroke width in float."""
        return float(self._data.get(b"strokeStyleLineWidth"))

    @property
    def line_dash_set(self) -> list:
        """
        Line dash set in list of
        :py:class:`~psd_tools.decoder.actions.UnitFloat`.

        :return: list
        """
        return self._data.get(b"strokeStyleLineDashSet")

    @property
    def line_dash_offset(self) -> float:
        """
        Line dash offset in float.

        :return: float
        """
        return self._data.get(b"strokeStyleLineDashOffset")

    @property
    def miter_limit(self):
        """Miter limit in float."""
        return self._data.get(b"strokeStyleMiterLimit")

    @property
    def line_cap_type(self) -> str:
        """Cap type, one of `butt`, `round`, `square`."""
        key = self._data.get(b"strokeStyleLineCapType").enum
        return self.STROKE_STYLE_LINE_CAP_TYPES.get(key, str(key))

    @property
    def line_join_type(self) -> str:
        """Join type, one of `miter`, `round`, `bevel`."""
        key = self._data.get(b"strokeStyleLineJoinType").enum
        return self.STROKE_STYLE_LINE_JOIN_TYPES.get(key, str(key))

    @property
    def line_alignment(self) -> str:
        """Alignment, one of `inner`, `outer`, `center`."""
        key = self._data.get(b"strokeStyleLineAlignment").enum
        return self.STROKE_STYLE_LINE_ALIGNMENTS.get(key, str(key))

    @property
    def scale_lock(self):
        return self._data.get(b"strokeStyleScaleLock")

    @property
    def stroke_adjust(self):
        """Stroke adjust"""
        return self._data.get(b"strokeStyleStrokeAdjust")

    @property
    def blend_mode(self):
        """Blend mode."""
        return self._data.get(b"strokeStyleBlendMode").enum

    @property
    def opacity(self):
        """Opacity value."""
        return self._data.get(b"strokeStyleOpacity")

    @property
    def content(self):
        """
        Fill effect.
        """
        return self._data.get(b"strokeStyleContent")

    def __repr__(self) -> str:
        return "%s(width=%g)" % (self.__class__.__name__, self.line_width)


class Origination(object):
    """
    Vector origination.

    Vector origination keeps live shape properties for some of the primitive
    shapes.
    """

    @classmethod
    def create(
        kls, data: DescriptorBlock2
    ) -> Invalidated | Rectangle | RoundedRectangle | Line | Ellipse:
        if data.get(b"keyShapeInvalidated"):
            return Invalidated(data)
        origin_type = data.get(b"keyOriginType")
        types = {1: Rectangle, 2: RoundedRectangle, 4: Line, 5: Ellipse}
        return types.get(origin_type, kls)(data)  # type: ignore

    def __init__(self, data):
        self._data = data

    @property
    def origin_type(self) -> int:
        """
        Type of the vector shape.

        * 1: :py:class:`~psd_tools.api.shape.Rectangle`
        * 2: :py:class:`~psd_tools.api.shape.RoundedRectangle`
        * 4: :py:class:`~psd_tools.api.shape.Line`
        * 5: :py:class:`~psd_tools.api.shape.Ellipse`

        :return: `int`
        """
        return int(self._data.get(b"keyOriginType"))

    @property
    def resolution(self) -> float:
        """Resolution.

        :return: `float`
        """
        return float(self._data.get(b"keyOriginResolution"))

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """
        Bounding box of the live shape.

        :return: :py:class:`~psd_tools.psd.descriptor.Descriptor`
        """
        bbox = self._data.get(b"keyOriginShapeBBox")
        if bbox:
            return (
                float(bbox.get(b"Left").value),
                float(bbox.get(b"Top ").value),
                float(bbox.get(b"Rght").value),
                float(bbox.get(b"Btom").value),
            )
        return (0.0, 0.0, 0.0, 0.0)

    @property
    def index(self) -> int:
        """
        Origination item index.

        :return: `int`
        """
        return self._data.get(b"keyOriginIndex")

    @property
    def invalidated(self) -> bool:
        """
        :return: `bool`
        """
        return False

    def __repr__(self) -> str:
        bbox = self.bbox
        return "%s(bbox=(%g, %g, %g, %g))" % (
            self.__class__.__name__,
            bbox[0],
            bbox[1],
            bbox[2],
            bbox[3],
        )


class Invalidated(Origination):
    """
    Invalidated live shape.

    This equals to a primitive shape that does not provide Live shape
    properties. Use :py:class:`~psd_tools.api.shape.VectorMask` to access
    shape information instead of this origination object.
    """

    @property
    def invalidated(self) -> bool:
        return True

    def __repr__(self) -> str:
        return "%s()" % (self.__class__.__name__)


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

        :return: :py:class:`~psd_tools.psd.descriptor.Descriptor`
        """
        return self._data.get(b"keyOriginRRectRadii")


class Line(Origination):
    """Line live shape."""

    @property
    def line_end(self) -> Descriptor:
        """
        Line end.

        :return: :py:class:`~psd_tools.psd.descriptor.Descriptor`
        """
        return self._data.get(b"keyOriginLineEnd")

    @property
    def line_start(self) -> Descriptor:
        """
        Line start.

        :return: :py:class:`~psd_tools.psd.descriptor.Descriptor`
        """
        return self._data.get(b"keyOriginLineStart")

    @property
    def line_weight(self) -> float:
        """
        Line weight

        :return: `float`
        """
        return float(self._data.get(b"keyOriginLineWeight"))

    @property
    def arrow_start(self) -> bool:
        """Line arrow start.

        :return: `bool`
        """
        return bool(self._data.get(b"keyOriginLineArrowSt"))

    @property
    def arrow_end(self) -> bool:
        """
        Line arrow end.

        :return: `bool`
        """
        return bool(self._data.get(b"keyOriginLineArrowEnd"))

    @property
    def arrow_width(self) -> float:
        """Line arrow width.

        :return: `float`
        """
        return float(self._data.get(b"keyOriginLineArrWdth"))

    @property
    def arrow_length(self) -> float:
        """Line arrow length.

        :return: `float`
        """
        return float(self._data.get(b"keyOriginLineArrLngth"))

    @property
    def arrow_conc(self) -> int:
        """

        :return: `int`
        """
        return int(self._data.get(b"keyOriginLineArrConc"))
