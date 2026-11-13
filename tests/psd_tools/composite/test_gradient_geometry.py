"""Independent Photoshop controls for aligned vertical overlay geometry."""

# Gradient fixtures: Copyright (c) 2026 PSD fixture contributors, MIT License.
import sys
from unittest.mock import Mock

import numpy as np
import pytest

from psd_tools import PSDImage
from psd_tools.api.layers import Layer
from psd_tools.composite import paint
from psd_tools.constants import ColorMode
from psd_tools.psd.descriptor import Bool, Descriptor, Double, Enumerated

from ..utils import full_name

pytest.importorskip("scipy")
CASES = [
    "pixel-90-base",
    "pixel-90-odd",
    "pixel-90-shift",
    "pixel-90-fractional-offset-integer-endpoints",
    "shape--90-scale150-shift",
    "shape--90-odd",
    "pixel-90-alpha-color",
    "shape-90-alpha-color",
    "pixel-90-multistop",
]


def _render(
    doc: PSDImage,
    force: bool,
    viewport: tuple[int, int, int, int] | None = None,
) -> np.ndarray:
    image = doc.composite(
        color=0.0, viewport=viewport, force=force, ignore_preview=True, apply_icc=False
    )
    return np.asarray(image.convert("RGBA"))


def _visible(image: np.ndarray, background: int) -> np.ndarray:
    alpha = image[..., 3:4].astype(float) / 255
    return image[..., :3] * alpha + background * (1 - alpha)


@pytest.mark.parametrize("name", CASES)
@pytest.mark.parametrize("force", [False, True])
def test_vertical_overlay_matches_photoshop(
    name: str, force: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = PSDImage.open(full_name(f"gradient-geometry/{name}.psd"))
    preview = doc.topil(apply_icc=False)
    assert preview is not None
    reference = np.asarray(preview.convert("RGBA"))
    desc = next(iter(doc[0].effects)).descriptor
    encoded = desc.tobytes()
    actual = _render(doc, force)
    visible = (actual[..., 3] > 0) | (reference[..., 3] > 0)
    for background in (0, 255):
        error = abs(_visible(actual, background) - _visible(reference, background))[
            visible
        ]
        assert error.mean() <= 0.6
        # Integer shape bounds can retain a one-level rasterized alpha difference.
        assert error.max() <= 2.00001

    monkeypatch.setitem(
        sys.modules["psd_tools.composite.composite"]._OVERLAY_DRAWS,
        "gradientoverlay",
        lambda layer, descriptor, channels: paint.draw_gradient_fill(
            layer.bbox, layer._psd.color_mode, descriptor
        ),
    )
    np.testing.assert_array_equal(_render(doc, force)[..., 3], actual[..., 3])
    assert desc.tobytes() == encoded


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("name", ["pixel-90-shift", "shape--90-scale150-shift"])
def test_viewport_keeps_layer_gradient_anchor(name: str, force: bool) -> None:
    doc = PSDImage.open(full_name(f"gradient-geometry/{name}.psd"))
    full = _render(doc, force)
    crop = (50, 55, 100, 72)
    np.testing.assert_array_equal(
        _render(doc, force, crop), full[crop[1] : crop[3], crop[0] : crop[2]]
    )
    expanded = _render(doc, force, (-5, -7, doc.width + 5, doc.height + 7))
    np.testing.assert_array_equal(expanded[7 : 7 + doc.height, 5 : 5 + doc.width], full)


@pytest.mark.parametrize("angle", [90, -90])
@pytest.mark.parametrize("reverse", [False, True])
def test_vertical_overlay_uses_pixel_coordinates(angle: int, reverse: bool) -> None:
    doc = PSDImage.open(full_name("gradient-geometry/pixel-90-shift.psd"))
    layer = doc[0]
    desc = next(iter(layer.effects)).descriptor
    desc[b"Angl"] = Double(angle)
    desc[b"Rvrs"] = Bool(reverse)
    color, _ = paint.draw_gradient_overlay(layer, desc)
    assert color is not None
    height = layer.height
    start = layer.top - height / 4
    expected = np.clip((np.arange(layer.top, layer.bottom) - start) / height, 0, 1)
    if (angle == 90) != reverse:
        expected = 1 - expected
    np.testing.assert_allclose(color[:, layer.width // 2, 0], expected, atol=1e-6)


@pytest.mark.parametrize(
    "path,value",
    [
        ((b"Angl",), Double(0)),
        ((b"Angl",), Double(30)),
        ((b"Angl",), Double(89.999)),
        ((b"Angl",), Double(float("nan"))),
        ((b"Angl",), Double(float("inf"))),
        ((b"gs99",), Enumerated(enum=b"Smoo")),
        ((b"gs99",), Enumerated(enum=b"Perc")),
        ((b"gs99",), None),
        ((b"Grad", b"Intr"), Double(4096)),
        ((b"Grad", b"Clrs", 0, b"Mdpn"), Double(25)),
        ((b"Grad", b"Trns", 0, b"Mdpn"), Double(25)),
        ((b"Dthr",), Bool(True)),
        ((b"Algn",), Bool(False)),
        ((b"Scl ",), Double(33)),
        ((b"Scl ",), Double(-100)),
        ((b"Scl ",), Double(float("nan"))),
        ((b"Scl ",), Double(float("inf"))),
        ((b"Ofst", b"Vrtc"), Double(3.3)),
        ((b"Ofst", b"Vrtc"), Double(float("inf"))),
        ((b"Ofst", b"Hrzn"), Double(float("inf"))),
        ((b"Type",), Enumerated(enum=b"Rdl ")),
    ],
)
def test_unsupported_overlays_keep_existing_paint(
    path: tuple[bytes | int, ...], value: Bool | Double | Enumerated | None
) -> None:
    doc = PSDImage.open(full_name("gradient-geometry/pixel-90-base.psd"))
    layer = doc[0]
    desc = next(iter(layer.effects)).descriptor
    target = desc
    for key in path[:-1]:
        target = target[key]
    if value is None:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    assert paint._vertical_overlay_geometry(layer, desc) is None
    before = paint.draw_gradient_fill(layer.bbox, doc.color_mode, desc)
    after = paint.draw_gradient_overlay(layer, desc)
    for a, b in zip(before, after, strict=True):
        np.testing.assert_array_equal(a, b)


@pytest.mark.parametrize("excluded", ["noise", "depth", "mode", "zero-scale"])
def test_unsupported_overlays_delegate(
    excluded: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = PSDImage.open(full_name("gradient-geometry/pixel-90-base.psd"))
    layer = doc[0]
    desc = next(iter(layer.effects)).descriptor
    if excluded == "noise":
        desc[b"Grad"][b"GrdF"] = Enumerated(enum=b"ClNs")
    elif excluded == "depth":
        doc._record.header.depth = 16
    elif excluded == "mode":
        doc._record.header.color_mode = ColorMode.GRAYSCALE
    else:
        desc[b"Scl "] = Double(0)
    assert paint._vertical_overlay_geometry(layer, desc) is None
    draw = Mock(return_value=(None, None))
    monkeypatch.setattr(paint, "draw_gradient_fill", draw)
    assert paint.draw_gradient_overlay(layer, desc) == (None, None)
    draw.assert_called_once_with(layer.bbox, doc.color_mode, desc)


@pytest.mark.parametrize(
    "name",
    ["gradient-fill.psd", "effect-stroke-gradient.psd", "layers/gradient-fill.psd"],
)
@pytest.mark.parametrize("force", [False, True])
def test_fill_and_stroke_do_not_use_overlay_geometry(
    name: str, force: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("aggdraw")
    doc = PSDImage.open(full_name(name))
    before = _render(doc, force)

    def reject(layer: Layer, desc: Descriptor) -> tuple[float, float, bool] | None:
        raise AssertionError("Fill and stroke must not enter overlay geometry")

    monkeypatch.setattr(paint, "_vertical_overlay_geometry", reject)
    np.testing.assert_array_equal(before, _render(doc, force))


def _shape_overlay() -> tuple[PSDImage, Layer, Descriptor]:
    doc = PSDImage.open(full_name("gradient-geometry/shape--90-odd.psd"))
    layer = doc[0]
    return doc, layer, next(iter(layer.effects)).descriptor


def _set_path_rows(layer: Layer, rows: tuple[float, float], height: int) -> None:
    """Rewrite the path's y coordinates as 8.24 fractions of `height` rows."""
    top, bottom = (np.floor(row / height * 2**24) / 2**24 for row in rows)
    mask = layer.vector_mask
    assert mask is not None
    assert mask._data.path is not None
    knots = mask._data.path[2]
    for knot, y in zip(knots, (top, top, bottom, bottom), strict=False):
        knot.anchor = (y, knot.anchor[1])
        knot.preceding = (y, knot.preceding[1])
        knot.leaving = (y, knot.leaving[1])


def test_disabled_vector_mask_keeps_layer_bbox() -> None:
    doc, layer, desc = _shape_overlay()
    enabled = paint._vertical_overlay_geometry(layer, desc)
    assert enabled is not None
    assert layer.bbox == (30, 20, 95, 39)
    assert layer.vector_mask is not None
    layer.vector_mask._data.flags |= 4
    _set_path_rows(layer, (60, 100), doc.height)
    assert enabled != (20, 19, False)
    assert paint._vertical_overlay_geometry(layer, desc) == (20, 19, False)


def test_pixel_layer_vector_mask_keeps_layer_bbox() -> None:
    _, shape, _ = _shape_overlay()
    doc = PSDImage.open(full_name("gradient-geometry/pixel-90-base.psd"))
    layer = doc[0]
    desc = next(iter(layer.effects)).descriptor
    expected = paint._vertical_overlay_geometry(layer, desc)
    assert expected is not None
    layer._vector_mask = shape.vector_mask
    assert paint._vertical_overlay_geometry(layer, desc) == expected


def test_integer_shape_bounds_on_large_document() -> None:
    doc, layer, desc = _shape_overlay()
    doc._record.header.height = 10000
    _set_path_rows(layer, (48, 80), 10000)
    geometry = paint._vertical_overlay_geometry(layer, desc)
    assert geometry is not None
    assert geometry[:2] == (48, 32)


def test_fractional_shape_bounds_on_large_document_are_excluded() -> None:
    doc, layer, desc = _shape_overlay()
    doc._record.header.height = 10000
    _set_path_rows(layer, (48.5, 80), 10000)
    assert paint._vertical_overlay_geometry(layer, desc) is None


@pytest.mark.parametrize(
    "path,value",
    [
        ((b"Ofst",), Double(0)),
        ((b"Grad", b"Intr"), Enumerated(enum=b"Smoo")),
        ((b"Grad", b"Clrs", 0, b"Mdpn"), Enumerated(enum=b"Smoo")),
    ],
)
def test_malformed_overlay_descriptor_falls_back(
    path: tuple[bytes | int, ...], value: Double | Enumerated
) -> None:
    doc = PSDImage.open(full_name("gradient-geometry/pixel-90-base.psd"))
    layer = doc[0]
    desc = next(iter(layer.effects)).descriptor
    target = desc
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises((AttributeError, KeyError, TypeError, ValueError)):
        paint._vertical_overlay_geometry(layer, desc)
    before = paint.draw_gradient_fill(layer.bbox, doc.color_mode, desc)
    after = paint.draw_gradient_overlay(layer, desc)
    for a, b in zip(before, after, strict=True):
        np.testing.assert_array_equal(a, b)
