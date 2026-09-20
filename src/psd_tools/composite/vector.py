"""Vector shapes and path operations for compositing."""

import logging
from typing import TYPE_CHECKING, Generator

import numpy as np
from PIL import Image

from psd_tools.composite import scanline
from psd_tools.composite._compat import require_aggdraw

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
    return _draw_path(
        layer,
        pen={
            "color": 255,
            "width": width,
            # 'linejoin': _JOIN.get(linejoin, 0),
            # 'linecap': _CAP.get(linecap, 0),
            # 'miterlimit': miterlimit,
        },
        viewport=viewport,
    )


def _draw_path(
    layer: "Layer",
    brush: dict[str, int | float] | None = None,
    pen: dict[str, int | float] | None = None,
    viewport: tuple[int, int, int, int] | None = None,
) -> np.ndarray:
    """
    Rasterize a layer's vector mask, filled by ``brush`` and outlined by ``pen``.

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
        plane = _draw_subpath(subpath_list, viewport, doc_size, brush, pen)
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
        outline = _stroke_subpath(drawable, viewport, doc_size, pen)
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
    one at a time. They are a single path, and Photoshop fills it by the
    non-zero rule: a subpath wound against its neighbour cuts a hole in it.
    Drawn separately and unioned, as they were while aggdraw did the filling,
    that hole is filled in (#844).
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
