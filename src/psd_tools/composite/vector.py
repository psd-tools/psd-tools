"""Vector shapes and path operations for compositing."""

import logging
from typing import TYPE_CHECKING, Generator

import numpy as np
from PIL import Image

from psd_tools.api.utils import check_pixel_size
from psd_tools.composite import scanline
from psd_tools.composite._compat import require_aggdraw
from psd_tools.constants import StrokeAlignment

if TYPE_CHECKING:
    from psd_tools.api.layers import Layer

logger = logging.getLogger(__name__)


def draw_vector_mask(
    layer: "Layer", viewport: tuple[int, int, int, int] | None = None
) -> np.ndarray:
    """
    Draw a vector mask.

    ``viewport`` is the region to rasterize onto, defaulting to the document
    canvas. A stroke effect asks for the box it draws on instead, which may
    reach outside the canvas: the path is placed in document coordinates
    either way, so what falls outside the canvas is real coverage rather than
    something to be clipped away (#804).

    The coverage is the area of the path inside each pixel, computed by
    :py:mod:`psd_tools.composite.scanline`. Filling needs no aggdraw.
    """
    return _draw_path(layer, brush={"color": 255}, viewport=viewport)


# The two positions that put the stroke to one side of the path. A stroke that
# names neither -- the third position, something no version of Photoshop wrote,
# or nothing at all -- is drawn centred, the only position not biased in or out.
_SIDED = (StrokeAlignment.INNER, StrokeAlignment.OUTER)
# What separates a pixel the path really does clip from one the fill
# rasterizer only rounded onto; see where it is used, in ``draw_stroke``.
_ROUNDING = 1e-9
# The same, for a pixel the path covers whole: the rasterizer reports one a
# float32 step or two short of 1.0, which an exact test calls outside.
_FULL_ROUNDING = 1e-5
# How far the pen reaches from the path it follows, in half-widths. A right-angle
# corner is mitred out to sqrt(2); a sharper one reaches further and is cut here.
_MITER_REACH = 1.5
# Per padded pixel, what ``_silhouette_distance`` peaks at: two float64 distance
# fields and the one they are merged into, with scipy's own temporaries, over
# the fill and its masks.
_NEAR_SILHOUETTE_BYTES = 48
# Per viewport pixel, the stroke colour the caller still holds (RGBA float32).
_RETAINED_COLOR_BYTES = 16
# Slack on a distance to the silhouette, measured from a pixel-resolution edge.
_BOUNDARY_MARGIN = 1.0


@require_aggdraw
def draw_stroke(
    layer: "Layer", viewport: tuple[int, int, int, int] | None = None
) -> np.ndarray:
    """
    Draw a stroke.

    ``viewport`` is the region to rasterize onto, defaulting to the document
    canvas. The compositor asks for the box it is compositing on, which need
    not start at the origin and may reach outside the canvas: the path is
    placed in document coordinates either way, so the stroke lands where the
    fill it outlines already is, and the part of it that falls off the canvas
    is real coverage rather than something to be clipped away (#807).

    A stroke sits on the side of the path its ``strokeStyleLineAlignment``
    names. A pen is only ever drawn centred on the line it follows, so an
    inner or an outer stroke is drawn at twice the width and clipped to one
    side -- the same workaround SVG and CSS use, neither being able to state
    an alignment either (#854).

    The pen is one outline filled by the even-odd rule, so where the shape is
    thinner than the doubled width it overlaps itself and cancels. An inner
    stroke is therefore also painted solid wherever the distance to the
    boundary is within the width (#890); an outer stroke is not.

    The pen follows each input path, so it is kept to the neighbourhood of the
    combined shape's boundary, which is where Photoshop strokes (#889).

    Requires aggdraw, which draws the pen. Only a stroke does; a fill is
    rasterized by :py:mod:`psd_tools.composite.scanline`.
    """
    if layer.stroke is None:
        raise ValueError("Layer stroke is required to draw a stroke.")
    desc = layer.stroke._data
    # _CAP = {
    #     'strokeStyleButtCap': 0,
    #     'strokeStyleSquareCap': 1,
    #     'strokeStyleRoundCap': 2,
    # }
    # _JOIN = {
    #     'strokeStyleMiterJoin': 0,
    #     'strokeStyleRoundJoin': 2,
    #     'strokeStyleBevelJoin': 3,
    # }
    width = float(desc.get("strokeStyleLineWidth", 1.0))
    # linejoin = desc.get('strokeStyleLineJoinType', None)
    # linejoin = linejoin.enum if linejoin else 'strokeStyleMiterJoin'
    # linecap = desc.get('strokeStyleLineCapType', None)
    # linecap = linecap.enum if linecap else 'strokeStyleButtCap'
    # miterlimit = desc.get('strokeStyleMiterLimit', 100.0) / 100.
    # aggdraw >= 1.3.12 will support additional params.
    alignment = layer.stroke.line_alignment
    sided = alignment in _SIDED
    pen: dict[str, int | float] = {
        "color": 255,
        "width": 2.0 * width if sided else width,
        # 'linejoin': _JOIN.get(linejoin, 0),
        # 'linecap': _CAP.get(linecap, 0),
        # 'miterlimit': miterlimit,
    }
    inner = alignment is StrokeAlignment.INNER
    radius = float(pen["width"]) / 2.0 * _MITER_REACH
    near = _near_silhouette(layer, radius, viewport)
    outline = _draw_path(layer, pen=pen, viewport=viewport, near=near)
    if not sided:
        return outline

    # Which side of the path a pixel is on, not how much of it the fill
    # covers: the shape's antialiased edge is already in the layer alpha the
    # stroke is composited onto, and multiplying by coverage here would count
    # it a second time. A pixel the path only clips still counts as inside it,
    # and as outside it too -- the band runs up to the boundary from either
    # side, and that pixel is where the boundary is.
    #
    # Sided above the fill rasterizer's own rounding rather than above zero,
    # since it reports a trace of coverage on pixels whole pixels away from
    # the path and an exact comparison would hand one of those the full width
    # of the pen. ``_ROUNDING`` sits in the gap between that trace and the
    # smallest coverage a path really does state.
    fill = draw_vector_mask(layer, viewport)
    inside = fill > _ROUNDING if inner else fill < 1.0 - _FULL_ROUNDING
    if inner:
        outline = _solid_inner_band(layer, outline, width, viewport)
    return outline * inside


def can_bury_arcs(layer: "Layer") -> bool:
    """Whether a stroke of ``layer`` is gated: one closed subpath has no other to bury it."""
    assert layer.vector_mask is not None
    return sum(1 for subpath in layer.vector_mask.paths if subpath.is_closed()) >= 2


def _near_silhouette(
    layer: "Layer", radius: float, viewport: tuple[int, int, int, int] | None
) -> np.ndarray | None:
    """
    Pixels within ``radius`` of the boundary of the shape the paths combine to.

    Keeping the pen to this neighbourhood drops the arcs one path buries inside
    another (#889). ``None`` when there is nothing to bury or no scipy, which
    leaves every arc stroked.
    """
    if not can_bury_arcs(layer):
        return None
    distance = _silhouette_distance(layer, radius, viewport)
    if distance is None:
        return None
    return (distance <= radius + _BOUNDARY_MARGIN).astype(np.float32)[:, :, None]


def _solid_inner_band(
    layer: "Layer",
    outline: np.ndarray,
    width: float,
    viewport: tuple[int, int, int, int] | None,
) -> np.ndarray:
    """
    ``outline`` with every pixel wholly within ``width`` of the boundary solid.

    The doubled pen cancels itself where the shape is thinner than it (#890);
    the pen keeps the band's own edge. Nothing outside the layer's box is
    inside the shape, so only that part of the viewport is measured. The fill
    closes an open subpath that the pen leaves open, so its boundary would grow
    a stroke along the missing edge; such a layer keeps the pen alone.
    """
    assert layer.vector_mask is not None
    if any(len(path) > 1 and not path.is_closed() for path in layer.vector_mask.paths):
        return outline
    if viewport is None:
        viewport = layer._psd.viewbox
    left, top, right, bottom = layer.bbox
    box = (
        max(viewport[0], left),
        max(viewport[1], top),
        min(viewport[2], right),
        min(viewport[3], bottom),
    )
    if box[2] <= box[0] or box[3] <= box[1]:
        return outline
    distance = _silhouette_distance(layer, width, box)
    if distance is None:
        return outline
    solid = (distance <= width - 1.0)[:, :, None]
    rows = slice(box[1] - viewport[1], box[3] - viewport[1])
    cols = slice(box[0] - viewport[0], box[2] - viewport[0])
    outline = outline.copy()
    outline[rows, cols] = np.maximum(outline[rows, cols], solid)
    return outline


def _silhouette_distance(
    layer: "Layer",
    radius: float,
    viewport: tuple[int, int, int, int] | None,
) -> np.ndarray | None:
    """
    Distance from each viewport pixel to the boundary of the combined shape.

    Photoshop strokes that silhouette, but a pen follows each input path, so an
    arc one path buries inside another would be stroked too (#889). Only
    distances within ``radius`` are reliable. ``None`` when the shape is empty
    or there is no scipy; ``inf`` throughout when the shape covers the viewport.

    A pixel is inside at any coverage, so a component thinner than a pixel still
    has a boundary; the margin on ``radius`` absorbs the fringe it adds.
    """
    try:
        from scipy.ndimage import distance_transform_edt  # type: ignore[import-untyped]  # noqa: PLC0415
    except ImportError:
        return None

    if viewport is None:
        viewport = layer._psd.viewbox
    # A boundary just outside the viewport still bounds the band inside it, but
    # none lies beyond the layer's own box, so a wide stroke need not look further.
    reach = int(np.ceil(radius + _BOUNDARY_MARGIN))
    left, top, right, bottom = layer.bbox
    padded = (
        max(viewport[0] - reach, min(viewport[0], left - 1)),
        max(viewport[1] - reach, min(viewport[1], top - 1)),
        min(viewport[2] + reach, max(viewport[2], right + 1)),
        min(viewport[3] + reach, max(viewport[3], bottom + 1)),
    )
    width, height = padded[2] - padded[0], padded[3] - padded[1]
    check_pixel_size(
        width,
        height,
        1,
        layer._psd._max_alloc_bytes,
        estimated_bytes=width * height * _NEAR_SILHOUETTE_BYTES
        + (viewport[2] - viewport[0])
        * (viewport[3] - viewport[1])
        * _RETAINED_COLOR_BYTES,
        warn=False,
    )
    inside = draw_vector_mask(layer, padded)[:, :, 0] > _FULL_ROUNDING
    # ``distance_transform_edt`` measures to a phantom feature off the array
    # corner when there is no zero to measure to. An empty mask states no boundary
    # to follow; one that is covered throughout has none in reach.
    if not inside.any():
        return None
    if inside.all():
        return np.full((viewport[3] - viewport[1], viewport[2] - viewport[0]), np.inf)
    distance = np.where(
        inside, distance_transform_edt(inside), distance_transform_edt(~inside)
    )
    return distance[
        viewport[1] - padded[1] : distance.shape[0] - (padded[3] - viewport[3]),
        viewport[0] - padded[0] : distance.shape[1] - (padded[2] - viewport[2]),
    ]


def _draw_path(
    layer: "Layer",
    brush: dict[str, int | float] | None = None,
    pen: dict[str, int | float] | None = None,
    viewport: tuple[int, int, int, int] | None = None,
    near: np.ndarray | None = None,
) -> np.ndarray:
    """
    Rasterize a layer's vector mask, filled by ``brush`` and outlined by ``pen``.

    ``near`` limits the outline of a closed subpath to where it is nonzero; see
    :py:func:`_near_silhouette`.

    A mask with an initial fill rule and no path of its own reveals all, so
    the plane starts out covered -- but only for a brush. The seed describes a
    *fill*, and a pen over zero paths has no outline to draw, so seeding it
    would cover the whole viewport with a stroke that has no shape (#823). The
    ``first and brush`` fill-rule inversions below are gated for the same
    reason.

    A brush is filled by :py:mod:`psd_tools.composite.scanline` and needs no
    aggdraw; only a pen does.
    """
    if layer.vector_mask is None:
        raise ValueError("Layer does not have a vector mask.")
    if viewport is None:
        viewport = layer._psd.viewbox
    width, height = viewport[2] - viewport[0], viewport[3] - viewport[1]
    doc_size = (layer._psd.width, layer._psd.height)
    color = 0
    if (
        brush
        and layer.vector_mask.initial_fill_rule
        and len(layer.vector_mask.paths) == 0
    ):
        color = 1
    mask = np.full((height, width, 1), color, dtype=np.float32)

    # Group merged path components.
    paths: list[list] = []
    for subpath in layer.vector_mask.paths:
        if subpath.operation == -1:
            paths[-1].append(subpath)
        else:
            paths.append([subpath])

    # Apply shape operation.
    first = True
    for subpath_list in paths:
        plane = _draw_subpath(subpath_list, viewport, doc_size, brush, pen, near)
        assert mask.shape == (height, width, 1)
        assert plane.shape == mask.shape

        op = subpath_list[0].operation
        if op == 0:  # Exclude = Union - Intersect.
            mask = mask + plane - 2 * mask * plane
        elif op == 1:  # Union (Combine).
            mask = mask + plane - mask * plane
        elif op == 2:  # Subtract.
            if first and brush:
                mask = 1 - mask
            mask = np.maximum(0, mask - plane)
        elif op == 3:  # Intersect.
            if first and brush:
                mask = 1 - mask
            mask = mask * plane
        first = False

    return np.minimum(1, np.maximum(0, mask))


def _draw_subpath(
    subpath_list: list,
    viewport: tuple[int, int, int, int],
    doc_size: tuple[int, int],
    brush: dict[str, int | float] | None,
    pen: dict[str, int | float] | None,
    near: np.ndarray | None = None,
) -> np.ndarray:
    """
    Rasterize one merged path component, filled by ``brush``, outlined by ``pen``.

    The two are drawn by different machinery and composited the way aggdraw
    composited them when it drew both: an outline paints over the fill it
    already laid down.
    """
    width, height = viewport[2] - viewport[0], viewport[3] - viewport[1]
    # Counted once here rather than in each of the two below, which would
    # report the same empty subpath twice over when both are asked for.
    drawable = []
    for subpath in subpath_list:
        if len(subpath) <= 1:
            logger.warning("not enough knots: %d", len(subpath))
        else:
            drawable.append(subpath)

    plane = np.zeros((height, width, 1), dtype=np.float32)
    if brush:
        plane = _fill_subpath(drawable, viewport, doc_size)
    if pen:
        closed = [subpath for subpath in drawable if subpath.is_closed()]
        outline = plane * 0
        if closed:
            outline = _stroke_subpath(closed, viewport, doc_size, pen)
            if near is not None:
                outline = outline * near
        # An open subpath bounds no area, so it has no silhouette to follow.
        opened = [subpath for subpath in drawable if not subpath.is_closed()]
        if opened:
            outline = np.maximum(
                outline, _stroke_subpath(opened, viewport, doc_size, pen)
            )
        plane = plane + outline - plane * outline
    return plane


def _fill_subpath(
    subpath_list: list,
    viewport: tuple[int, int, int, int],
    doc_size: tuple[int, int],
) -> np.ndarray:
    """
    Area of the path inside each pixel of ``viewport``.

    The subpaths of one merged component are rasterized together rather than
    one at a time. They are a single path, filled by the even-odd rule -- the
    one PSD uses -- so a subpath inside another cuts a hole in it whichever
    way it winds. Drawn separately and unioned, as they were while aggdraw
    did the filling, that hole is filled in (#844).
    """
    origin = np.array([viewport[0], viewport[1]], dtype=np.float64)
    polylines = [
        _flatten_subpath(subpath, *doc_size) - origin for subpath in subpath_list
    ]
    coverage = scanline.fill_coverage(
        polylines, viewport[2] - viewport[0], viewport[3] - viewport[1]
    )
    return np.expand_dims(coverage, 2)


def _flatten_subpath(subpath, width: int, height: int) -> np.ndarray:
    """
    Polyline through one subpath, in document coordinates, x first.

    Knot coordinates are fractions of the document, so they are always scaled
    by the document size; the caller shifts the result onto its viewport.

    An open subpath keeps its last anchor, which no curve of its own ends on.
    A closed one does not: its last curve returns to the first anchor, which
    the contour already starts from.
    """
    knots = list(subpath)
    closed = subpath.is_closed()
    pairs = list(zip(knots, knots[1:] + knots[:1] if closed else knots[1:]))

    def scaled(points) -> np.ndarray:
        return np.array(
            [(p[1] * width, p[0] * height) for p in points], dtype=np.float64
        )

    polyline = scanline.flatten_cubics(
        scaled([a.anchor for a, _ in pairs]),
        scaled([a.leaving for a, _ in pairs]),
        scaled([b.preceding for _, b in pairs]),
        scaled([b.anchor for _, b in pairs]),
    )
    if closed:
        return polyline
    return np.concatenate([polyline, scaled([knots[-1].anchor])])


@require_aggdraw
def _stroke_subpath(
    subpath_list: list,
    viewport: tuple[int, int, int, int],
    doc_size: tuple[int, int],
    pen: dict[str, int | float],
) -> np.ndarray:
    """
    Rasterize the outline of a path with aggdraw.

    A pen is exact -- a line of width w covers exactly w -- so the quarter
    pixel aggdraw adds to a *fill* (#844) is not a reason to leave it, and its
    joins and caps are work of their own.

    Knot coordinates are fractions of the document, so the symbol is always
    built against the document size and then translated by minus the viewport
    origin -- a viewport that starts outside the canvas shifts the path
    *into* the plane, which is what keeps the part of it that lies off the
    canvas from being drawn past the edge.
    """
    import aggdraw  # type: ignore[import-not-found]  # noqa: PLC0415

    width, height = viewport[2] - viewport[0], viewport[3] - viewport[1]
    mask = Image.new("L", (width, height), 0)
    draw = aggdraw.Draw(mask)
    stroke = aggdraw.Pen(**pen)
    for subpath in subpath_list:
        path = " ".join(map(str, _generate_symbol(subpath, *doc_size)))
        symbol = aggdraw.Symbol(path)
        draw.symbol((-viewport[0], -viewport[1]), symbol, stroke, None)
    draw.flush()
    del draw
    return np.expand_dims(np.array(mask).astype(np.float32) / 255.0, 2)


def _generate_symbol(
    path,
    width: int,
    height: int,
    command: str = "C",
) -> Generator[str | float, None, None]:
    """Sequence generator for SVG path."""
    if len(path) == 0:
        return

    # Initial point.
    yield "M"
    yield path[0].anchor[1] * width
    yield path[0].anchor[0] * height
    yield command

    # Closed path or open path
    points = (
        zip(path, path[1:] + path[0:1]) if path.is_closed() else zip(path, path[1:])
    )

    # Rest of the points.
    for p1, p2 in points:
        yield p1.leaving[1] * width
        yield p1.leaving[0] * height
        yield p2.preceding[1] * width
        yield p2.preceding[0] * height
        yield p2.anchor[1] * width
        yield p2.anchor[0] * height

    if path.is_closed():
        yield "Z"
