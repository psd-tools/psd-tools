"""Vector shapes and path operations for compositing."""

import logging

import numpy as np
from PIL import Image

from psd_tools.composite._compat import require_aggdraw

logger = logging.getLogger(__name__)


@require_aggdraw
def draw_vector_mask(layer):
    """
    Draw a vector mask.

    Requires aggdraw for bezier curve rasterization.
    """
    return _draw_path(layer, brush={"color": 255})


@require_aggdraw
def draw_stroke(layer):
    """
    Draw a stroke.

    Requires aggdraw for bezier curve rasterization.
    """
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
    )


def _draw_path(layer, brush=None, pen=None):
    height, width = layer._psd.height, layer._psd.width
    color = 0
    if layer.vector_mask.initial_fill_rule and len(layer.vector_mask.paths) == 0:
        color = 1
    mask = np.full((height, width, 1), color, dtype=np.float32)

    # Group merged path components.
    paths = []
    for subpath in layer.vector_mask.paths:
        if subpath.operation == -1:
            paths[-1].append(subpath)
        else:
            paths.append([subpath])

    # Apply shape operation.
    first = True
    for subpath_list in paths:
        plane = _draw_subpath(subpath_list, width, height, brush, pen)
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


def _draw_subpath(subpath_list, width, height, brush, pen):
    """
    Rasterize Bezier curves using aggdraw.

    TODO: Replace aggdraw implementation with skimage.draw.

    Note: Callers must be decorated with @needs_aggdraw before calling.
    """
    import aggdraw  # type: ignore[import-not-found]

    mask = Image.new("L", (width, height), 0)
    draw = aggdraw.Draw(mask)
    pen = aggdraw.Pen(**pen) if pen else None
    brush = aggdraw.Brush(**brush) if brush else None
    for subpath in subpath_list:
        if len(subpath) <= 1:
            logger.warning("not enough knots: %d" % len(subpath))
            continue
        path = " ".join(map(str, _generate_symbol(subpath, width, height)))
        symbol = aggdraw.Symbol(path)
        draw.symbol((0, 0), symbol, pen, brush)
    draw.flush()
    del draw
    return np.expand_dims(np.array(mask).astype(np.float32) / 255.0, 2)


def _generate_symbol(path, width, height, command="C"):
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
