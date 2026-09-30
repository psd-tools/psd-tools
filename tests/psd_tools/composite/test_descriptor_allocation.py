"""Allocations a descriptor's size grows are checked before they are made."""

import logging

import numpy as np
import pytest

from psd_tools.api import numpy_io
from psd_tools.api.layers import Layer
from psd_tools.api.psd_image import PSDImage
from psd_tools.composite import effects, paint
from psd_tools.composite.composite import _GRADIENT_FILL_BYTES, _stroke_reach
from psd_tools.composite.paint import draw_pattern_fill
from psd_tools.constants import Tag
from psd_tools.psd.descriptor import Descriptor, Double, UnitFloat
from psd_tools.terminology import Key

from ..utils import full_name

# Far past the per-axis limit however the value is spent.
HUGE = 1e9


def _pattern() -> tuple[PSDImage, Descriptor, tuple[int, ...]]:
    psd = PSDImage.open(full_name("layers-minimal/pattern-fill.psd"))
    desc = psd[0].tagged_blocks.get_data(Tag.PATTERN_FILL_SETTING)
    pattern = psd._get_pattern(desc[b"Ptrn"][Key.ID].value.rstrip("\x00"))
    assert pattern is not None
    return psd, desc, numpy_io.get_pattern(pattern).shape


@pytest.mark.parametrize(
    ("scale", "message"), [(HUGE, "per axis"), (float("inf"), "not finite")]
)
def test_a_forged_pattern_scale_is_rejected_without_a_budget(
    scale: float, message: str
) -> None:
    """The per-axis limit bounds it, and a non-finite scale is a ValueError."""
    psd, desc, _ = _pattern()
    desc[b"Scl "] = Double(scale)
    with pytest.raises(ValueError, match=message):
        draw_pattern_fill(psd.viewbox, psd, desc)


def test_the_scaled_pattern_panel_is_checked_at_its_resize_size() -> None:
    psd, desc, shape = _pattern()
    percent = 400.0
    rows, cols = int(shape[0] * percent / 100), int(shape[1] * percent / 100)
    desc[b"Scl "] = Double(percent)
    resized = rows * cols * shape[2] * 4 * paint._RESIZE_COPIES

    psd._max_alloc_bytes = resized
    draw_pattern_fill(psd.viewbox, psd, desc)
    psd._max_alloc_bytes = resized - 1
    with pytest.raises(ValueError, match="over the configured budget"):
        draw_pattern_fill(psd.viewbox, psd, desc)


def test_the_tiled_pattern_is_checked_at_the_viewport() -> None:
    """A panel scaled down to a pixel is tiled up to the viewport's size."""
    psd, desc, shape = _pattern()
    desc[b"Scl "] = Double(0.0)
    viewport = (0, 0, 2000, 2000)
    tiled = 2000 * 2000 * shape[2] * 4

    psd._max_alloc_bytes = tiled
    draw_pattern_fill(viewport, psd, desc)
    psd._max_alloc_bytes = tiled - 1
    with pytest.raises(ValueError, match="over the configured budget"):
        draw_pattern_fill(viewport, psd, desc)


def test_an_empty_pattern_viewport_is_not_rejected() -> None:
    psd, desc, _ = _pattern()
    psd._max_alloc_bytes = 1
    color, _ = draw_pattern_fill((0, 0, 0, 0), psd, desc)
    assert color is not None and color.size == 0


def _stroke_desc(size: float) -> tuple[PSDImage, Layer, Descriptor]:
    psd = PSDImage.open(full_name("effects/outside-stroke.psd"))
    layer = psd[0]
    (effect,) = layer.effects.find("stroke")
    effect.descriptor[Key.SizeKey] = Double(size)
    return psd, layer, effect.descriptor


@pytest.mark.parametrize("size", [1e5, HUGE, 1e300])
def test_a_forged_stroke_size_is_rejected_without_a_budget(size: float) -> None:
    _, layer, desc = _stroke_desc(size)
    with pytest.raises(ValueError, match="per axis"):
        effects.stroke_bbox(layer.bbox, desc)


def test_the_stroke_box_is_checked_at_its_peak_per_pixel() -> None:
    _, layer, desc = _stroke_desc(50.0)
    grown = effects.stroke_bbox(layer.bbox, desc)
    peak = (grown[2] - grown[0]) * (grown[3] - grown[1]) * effects._STROKE_BYTES

    assert effects.stroke_bbox(layer.bbox, desc, peak) == grown
    with pytest.raises(ValueError, match="over the configured budget"):
        effects.stroke_bbox(layer.bbox, desc, peak - 1)


def test_an_empty_stroke_box_is_returned_untouched() -> None:
    _, _, desc = _stroke_desc(HUGE)
    assert effects.stroke_bbox((5, 5, 5, 9), desc, 1) == (5, 5, 5, 9)


def test_a_stroke_over_budget_is_dropped_from_the_reach_and_the_render(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Both callers read the failed box as an unreadable stroke."""
    psd, layer, _ = _stroke_desc(HUGE)
    with caplog.at_level(logging.DEBUG, logger="psd_tools.composite.composite"):
        assert _stroke_reach(layer) == layer.bbox
        forged = np.asarray(psd.composite(ignore_preview=True).convert("RGBA"))
    assert any("Cannot measure a stroke effect" in r.message for r in caplog.records)

    off = PSDImage.open(full_name("effects/outside-stroke.psd"))
    for effect in off[0].effects.find("stroke"):
        effect.descriptor[Key.Enabled] = False
    plain = np.asarray(off.composite(ignore_preview=True).convert("RGBA"))
    assert np.array_equal(forged, plain)


def _vector_stroke() -> tuple[PSDImage, Layer, Descriptor]:
    psd = PSDImage.open(full_name("effects/stroke-composite.psd"))
    layer = [x for x in psd.descendants() if x.name == "Plain"][0]
    assert layer.stroke is not None and layer.has_vector_mask()
    return psd, layer, layer.stroke._data


@pytest.mark.parametrize(
    ("width", "message"), [(HUGE, "per axis"), (float("inf"), "not finite")]
)
def test_a_forged_vector_stroke_width_is_rejected_without_a_budget(
    width: float, message: str
) -> None:
    psd, _, desc = _vector_stroke()
    unit = desc[b"strokeStyleLineWidth"].unit
    desc[b"strokeStyleLineWidth"] = UnitFloat(value=width, unit=unit)
    with pytest.raises(ValueError, match=message):
        psd.composite(force=True, ignore_preview=True)


def test_the_vector_stroke_fill_is_checked_at_the_grown_box() -> None:
    psd, layer, desc = _vector_stroke()
    unit = desc[b"strokeStyleLineWidth"].unit
    width = 200
    desc[b"strokeStyleLineWidth"] = UnitFloat(value=float(width), unit=unit)
    left, top, right, bottom = layer.bbox
    fill = (right - left + 2 * width) * (bottom - top + 2 * width) * 3 * 4

    psd._max_alloc_bytes = fill
    psd.composite(force=True, ignore_preview=True)
    psd._max_alloc_bytes = fill - 1
    with pytest.raises(ValueError, match="over the configured budget"):
        psd.composite(force=True, ignore_preview=True)


def test_a_denormal_stroke_size_still_grows_the_box_by_a_pixel_and_its_edge() -> None:
    _, layer, desc = _stroke_desc(5e-324)
    left, top, right, bottom = layer.bbox
    assert effects.stroke_bbox(layer.bbox, desc) == (
        left - 2,
        top - 2,
        right + 2,
        bottom + 2,
    )


def test_tile_rounding_past_the_axis_limit_is_not_rejected() -> None:
    """The limit is on the viewport, not on the tile that covers it."""
    psd, desc, shape = _pattern()
    desc[b"Scl "] = Double(100.0)
    width = 29999
    assert -(-width // shape[1]) * shape[1] > 30000
    color, _ = draw_pattern_fill((0, 0, width, 1), psd, desc)
    assert color is not None and color.shape[:2] == (1, width)


def test_a_gradient_vector_stroke_fill_is_checked_at_its_own_peak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    psd, layer, desc = _vector_stroke()
    monkeypatch.setattr(desc[b"strokeStyleContent"], "classID", b"gradientLayer")
    monkeypatch.setattr(
        paint,
        "create_fill_desc",
        lambda layer, desc, viewport: (
            np.zeros((viewport[3] - viewport[1], viewport[2] - viewport[0], 3)),
            None,
        ),
    )
    left, top, right, bottom = layer.bbox
    grow = 2 * int(desc[b"strokeStyleLineWidth"].value)
    peak = (right - left + grow) * (bottom - top + grow) * _GRADIENT_FILL_BYTES

    psd._max_alloc_bytes = peak
    psd.composite(force=True, ignore_preview=True)
    psd._max_alloc_bytes = peak - 1
    with pytest.raises(ValueError, match="over the configured budget"):
        psd.composite(force=True, ignore_preview=True)
