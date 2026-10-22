"""A stroke's pattern phase and gradient ramp are laid out on the path (#824)."""

import copy

import numpy as np
import pytest

from psd_tools import PSDImage
from psd_tools.composite import paint
from psd_tools.composite.composite import _path_bbox
from psd_tools.constants import ColorMode
from psd_tools.psd.descriptor import Descriptor

from ..utils import full_name

ANCHOR = (10, 20, 70, 50)


def _stroke_content(name: str) -> tuple[PSDImage, Descriptor]:
    psd = PSDImage.open(full_name("stroke.psd"))
    layer = next(x for x in psd if x.name == name)
    assert layer.stroke is not None
    return psd, layer.stroke._data[b"strokeStyleContent"]


def _crop(
    drawn: np.ndarray,
    viewport: tuple[int, int, int, int],
    anchor: tuple[int, int, int, int],
) -> np.ndarray:
    left, top = anchor[0] - viewport[0], anchor[1] - viewport[1]
    return drawn[top : top + anchor[3] - anchor[1], left : left + anchor[2] - anchor[0]]


def test_a_gradient_drawn_past_its_anchor_continues_the_ramp() -> None:
    _, desc = _stroke_content("Shape 1")
    viewport = (3, 5, 95, 71)
    anchored, _ = paint.draw_gradient_fill(viewport, ColorMode.RGB, desc, ANCHOR)
    alone, _ = paint.draw_gradient_fill(ANCHOR, ColorMode.RGB, desc)
    assert anchored is not None and alone is not None
    assert np.allclose(_crop(anchored, viewport, ANCHOR), alone, atol=1e-6)


def test_a_gradient_without_an_anchor_is_drawn_on_the_viewport() -> None:
    _, desc = _stroke_content("Shape 1")
    plain, _ = paint.draw_gradient_fill(ANCHOR, ColorMode.RGB, desc)
    same, _ = paint.draw_gradient_fill(ANCHOR, ColorMode.RGB, desc, ANCHOR)
    assert plain is not None and same is not None
    assert np.array_equal(plain, same)


@pytest.mark.parametrize("offset", [(0, 0), (3, 5), (61, 47), (200, 300)])
def test_a_pattern_drawn_past_its_anchor_continues_the_tiling(
    offset: tuple[int, int],
) -> None:
    psd, desc = _stroke_content("Rounded Rectangle 1")
    size = 80
    # The tiling from the anchor, over a box big enough to hold every viewport.
    reference, _ = paint.draw_pattern_fill(
        (ANCHOR[0], ANCHOR[1], ANCHOR[0] + 400 + size, ANCHOR[1] + 400 + size),
        psd,
        desc,
    )
    viewport = (
        ANCHOR[0] + offset[0],
        ANCHOR[1] + offset[1],
        ANCHOR[0] + offset[0] + size,
        ANCHOR[1] + offset[1] + size,
    )
    drawn, _ = paint.draw_pattern_fill(viewport, psd, desc, ANCHOR)
    assert drawn is not None and reference is not None
    dx, dy = offset
    assert np.array_equal(drawn, reference[dy : dy + size, dx : dx + size])


def test_a_pattern_drawn_before_its_anchor_wraps_the_tiling() -> None:
    psd, desc = _stroke_content("Rounded Rectangle 1")
    before, _ = paint.draw_pattern_fill(
        (ANCHOR[0] - 13, ANCHOR[1] - 9, ANCHOR[2], ANCHOR[3]), psd, desc, ANCHOR
    )
    alone, _ = paint.draw_pattern_fill(ANCHOR, psd, desc)
    assert before is not None and alone is not None
    assert np.array_equal(before[9:, 13:], alone)


def _forged(width: float) -> PSDImage:
    """``Plain`` of ``stroke-composite.psd`` stroked with a gradient of the given width."""
    _donor, desc = _stroke_content("Shape 1")
    psd = PSDImage.open(full_name("effects/stroke-composite.psd"))
    layer = next(x for x in psd.descendants() if x.name == "Plain")
    for other in psd.descendants():
        if other is not layer and not other.is_group():
            other.visible = False
    assert layer.stroke is not None
    stroke = layer.stroke._data
    stroke[b"strokeStyleLineWidth"].value = width
    stroke[b"strokeStyleContent"] = copy.deepcopy(desc)
    stroke[b"strokeStyleContent"][b"Angl"].value = 0.0
    return psd


def test_a_gradient_stroke_is_laid_out_on_the_path_whatever_its_width() -> None:
    renders = {
        width: np.asarray(
            _forged(width).composite(force=True, ignore_preview=True).convert("RGB")
        ).astype(np.int16)
        for width in (10.4, 20.6)
    }
    psd = _forged(10.4)
    layer = next(x for x in psd.descendants() if x.name == "Plain")
    assert layer.bbox != _path_bbox(layer)
    left, top, _right, bottom = layer.bbox
    row = (top + bottom) // 2
    # The columns both widths stroke are painted the same: the ramp does not
    # stretch with the stroke.
    shared = slice(left + 2, left + 9)
    assert np.abs(renders[10.4][row, shared] - renders[20.6][row, shared]).max() <= 1


@pytest.mark.parametrize(
    "anchor", [(10, 10, 10, 10), (10, 10, 10, 50), (10, 10, 50, 10)]
)
def test_a_gradient_anchored_on_a_path_with_no_extent_is_drawn(
    anchor: tuple[int, int, int, int],
) -> None:
    _, desc = _stroke_content("Shape 1")
    color, _ = paint.draw_gradient_fill((0, 0, 60, 40), ColorMode.RGB, desc, anchor)
    assert color is not None and color.shape[:2] == (40, 60)
    assert np.isfinite(color).all()
