"""Unit tests for the compositor's primitives.

The rest of the composite suite is end-to-end: render a fixture, compare MSE
against a reference. That is a good acceptance suite and a poor refactoring
suite -- a broken transparency term surfaces as a threshold miss on some
fixture, with no indication of which equation moved.

These tests pin the primitives directly, so a change to the compositing maths
fails with a specific, hand-checkable number. See #715.
"""

from typing import Any, cast

import numpy as np
import pytest

from psd_tools.composite import utils
from psd_tools.composite.composite import (
    _OVERLAY_DRAWS,
    Compositor,
    _blend_backdrop,
    _normalize_backdrop,
    _widen,
    paste,
)
from psd_tools.constants import BlendMode, Knockout

RED = (1.0, 0.0, 0.0)
GREEN = (0.0, 1.0, 0.0)
BLUE = (0.0, 0.0, 1.0)
WHITE = (1.0, 1.0, 1.0)


def gray(value: float, size: tuple[int, int] = (2, 2)) -> np.ndarray:
    """A single-channel array filled with ``value``."""
    return np.full((size[0], size[1], 1), value, dtype=np.float32)


def rgb(
    color: tuple[float, float, float], size: tuple[int, int] = (2, 2)
) -> np.ndarray:
    """A three-channel array filled with ``color``."""
    return np.tile(np.array(color, dtype=np.float32), (size[0], size[1], 1))


# ---------------------------------------------------------------------------
# Overlay effects
# ---------------------------------------------------------------------------


def test_overlays_are_composited_in_a_fixed_order() -> None:
    """Iteration order of the table is compositing order, so it is behaviour.

    The three overlays used to be three calls in ``apply()``; collapsing them
    onto one code path (#713) moved that ordering into a dict, where it is
    easier to disturb by accident.
    """
    assert list(_OVERLAY_DRAWS) == [
        "coloroverlay",
        "patternoverlay",
        "gradientoverlay",
    ]


# ---------------------------------------------------------------------------
# paste()
# ---------------------------------------------------------------------------


def test_paste_identity() -> None:
    values = np.arange(4, dtype=np.float32).reshape(2, 2, 1)
    assert np.array_equal(paste((0, 0, 2, 2), (0, 0, 2, 2), values), values)


def test_paste_inset_places_values_at_the_offset() -> None:
    values = np.arange(4, dtype=np.float32).reshape(2, 2, 1)
    result = paste((0, 0, 4, 4), (1, 1, 3, 3), values)
    assert result.shape == (4, 4, 1)
    assert np.array_equal(result[1:3, 1:3, :], values)
    # Everything outside the bbox is background.
    assert result[0, :, :].sum() == 0.0
    assert result[3, :, :].sum() == 0.0


def test_paste_crops_when_bbox_overhangs_the_viewport() -> None:
    values = np.arange(4, dtype=np.float32).reshape(2, 2, 1)
    result = paste((0, 0, 1, 1), (0, 0, 2, 2), values)
    assert result.shape == (1, 1, 1)
    assert result[0, 0, 0] == values[0, 0, 0]


def test_paste_disjoint_bbox_is_all_background() -> None:
    values = np.ones((2, 2, 1), dtype=np.float32)
    assert np.array_equal(
        paste((0, 0, 2, 2), (5, 5, 7, 7), values, 1.0), np.ones((2, 2, 1), np.float32)
    )
    assert np.array_equal(
        paste((0, 0, 2, 2), (5, 5, 7, 7), values), np.zeros((2, 2, 1), np.float32)
    )


@pytest.mark.parametrize("background", [None, 0.0])
def test_paste_background_none_and_zero_agree(background: float | None) -> None:
    """An explicit 0.0 background and no background at all must agree.

    ``paste`` used to select its fill by truthiness, so 0.0 took the ``np.zeros``
    path -- numerically identical, but it read like a bug. The guard is now
    ``if background is not None`` (#711); this pins that the change stayed a
    no-op.
    """
    values = np.ones((1, 1, 1), dtype=np.float32)
    result = paste((0, 0, 3, 3), (0, 0, 1, 1), values, background)
    assert result[2, 2, 0] == 0.0


def test_paste_background_fills_the_uncovered_region() -> None:
    values = np.zeros((1, 1, 1), dtype=np.float32)
    result = paste((0, 0, 3, 3), (0, 0, 1, 1), values, 1.0)
    assert result[0, 0, 0] == 0.0  # the pasted value survives
    assert result[2, 2, 0] == 1.0  # the rest is background


def test_paste_preserves_channel_count() -> None:
    assert paste((0, 0, 4, 4), (1, 1, 3, 3), rgb(BLUE)).shape == (4, 4, 3)


# ---------------------------------------------------------------------------
# utils
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b"), [(0.0, 0.0), (0.0, 1.0), (0.25, 0.5), (0.5, 0.5), (1.0, 1.0)]
)
def test_union_matches_its_definition_and_commutes(a: float, b: float) -> None:
    assert utils.union(a, b) == pytest.approx(a + b - a * b)
    assert utils.union(a, b) == pytest.approx(utils.union(b, a))


@pytest.mark.parametrize("x", [0.0, 0.25, 1.0])
def test_union_identities(x: float) -> None:
    assert utils.union(x, 0.0) == pytest.approx(x)
    assert utils.union(x, 1.0) == pytest.approx(1.0)


def test_divide_defaults_to_one_where_the_divisor_is_zero() -> None:
    """Without a ``fill``, a zero divisor yields 1.0.

    That is white in normalised colour space and fully opaque read as an
    alpha; the callers that do not pass ``fill`` rely on one or the other.
    """
    assert np.array_equal(utils.divide(gray(1.0), gray(0.0)), gray(1.0))
    assert np.array_equal(utils.divide(gray(0.0), gray(0.0)), gray(1.0))


def test_divide_substitutes_the_callers_fill() -> None:
    assert np.array_equal(utils.divide(gray(1.0), gray(0.0), fill=0.25), gray(0.25))


def test_divide_fill_may_be_a_canvas() -> None:
    """A per-pixel fill, as ``_apply_passthrough_source`` passes."""
    divisor = np.array([[[0.0], [2.0]]], dtype=np.float32)
    result = utils.divide(rgb(WHITE, (1, 2)), divisor, fill=rgb(BLUE, (1, 2)))
    assert np.allclose(result[0, 0], BLUE)  # divisor 0 -> the fill
    assert np.allclose(result[0, 1], (0.5, 0.5, 0.5))  # divisor 2 -> the quotient


def test_divide_fill_broadcasts_against_a_wider_numerator() -> None:
    """A three-channel numerator over a single-channel divisor."""
    result = utils.divide(rgb(RED), gray(0.0), fill=gray(0.5))
    assert result.shape == (2, 2, 3)
    assert np.allclose(result, 0.5)


def test_divide_is_ordinary_where_the_divisor_is_non_zero() -> None:
    assert np.allclose(utils.divide(gray(1.0), gray(4.0)), gray(0.25))
    assert np.allclose(utils.divide(gray(1.0), gray(4.0), fill=0.0), gray(0.25))


def test_divide_keeps_the_numerator_dtype() -> None:
    """float32 canvases must not be promoted to float64 by a scalar divisor."""
    assert utils.divide(gray(1.0), np.float32(2.0)).dtype == np.float32


def test_clip_bounds() -> None:
    values = np.array([[-1.0, 0.0, 0.5, 1.0, 2.0]], dtype=np.float32)
    assert np.array_equal(utils.clip(values), np.array([[0.0, 0.0, 0.5, 1.0, 1.0]]))


def test_intersect() -> None:
    assert utils.intersect((0, 0, 4, 4), (1, 1, 3, 3)) == (1, 1, 3, 3)
    assert utils.intersect((0, 0, 2, 2), (1, 1, 4, 4)) == (1, 1, 2, 2)
    # Disjoint and merely-touching boxes both collapse to the empty box.
    assert utils.intersect((0, 0, 2, 2), (5, 5, 7, 7)) == (0, 0, 0, 0)
    assert utils.intersect((0, 0, 2, 2), (2, 2, 4, 4)) == (0, 0, 0, 0)


# ---------------------------------------------------------------------------
# _blend_backdrop()
# ---------------------------------------------------------------------------


def test_blend_backdrop_over_opaque_backdrop() -> None:
    color, alpha = _blend_backdrop(rgb(BLUE), gray(0.5), rgb(RED), gray(1.0))
    # 50% blue over opaque red.
    assert np.allclose(color[0, 0], (0.5, 0.0, 0.5))
    assert np.allclose(alpha, 1.0)


def test_blend_backdrop_transparent_backdrop_keeps_source_colour() -> None:
    """A transparent backdrop must not bleed its colour into the result."""
    color, alpha = _blend_backdrop(rgb(BLUE), gray(1.0), rgb(WHITE), gray(0.0))
    assert np.allclose(color[0, 0], BLUE)
    assert np.allclose(alpha, 1.0)


# ---------------------------------------------------------------------------
# _normalize_backdrop()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "color",
    [
        1,
        1.0,
        np.float32(1.0),
        np.int64(1),
        WHITE,
        list(WHITE),
        np.array(WHITE, dtype=np.float32),
        np.array(WHITE, dtype=np.float64),
    ],
    ids=repr,
)
def test_normalize_backdrop_accepts_every_scalar_and_sequence_spelling(
    color: object,
) -> None:
    """Equivalent backdrops expressed any of these ways must agree (#709).

    ``composite()`` accepts a scalar, a per-channel sequence or an ndarray;
    this is where all of them become the one array the compositor works with.
    """
    result, _ = _normalize_backdrop(color, 0.0, 2, 3, 3)  # type: ignore[arg-type]
    assert result.dtype == np.float32
    assert np.array_equal(result, rgb(WHITE, size=(2, 3)))


@pytest.mark.parametrize("alpha", [1, 1.0, np.float32(1.0)], ids=repr)
def test_normalize_backdrop_accepts_every_alpha_spelling(alpha: object) -> None:
    _, result = _normalize_backdrop(1.0, alpha, 2, 3, 3)  # type: ignore[arg-type]
    assert result.dtype == np.float32
    assert np.array_equal(result, gray(1.0, size=(2, 3)))


def test_normalize_backdrop_passes_a_per_pixel_array_through() -> None:
    """A full canvas of the right width is taken as given."""
    canvas = np.linspace(0.0, 1.0, 12, dtype=np.float32).reshape(2, 2, 3)
    result, _ = _normalize_backdrop(canvas, 0.0, 2, 2, 3)
    assert np.array_equal(result, canvas)


def test_normalize_backdrop_widens_a_single_channel_canvas() -> None:
    """One channel against a three-channel document is replicated (#710).

    The compositor used to widen this lazily at the first source, which left
    ``_color_0``'s width only eventually correct. Normalization settles it, so
    the canvas width is fixed for the compositor's whole lifetime.
    """
    result, _ = _normalize_backdrop(gray(0.25), 0.0, 2, 2, 3)
    assert result.shape == (2, 2, 3)
    assert np.array_equal(result, rgb((0.25, 0.25, 0.25)))
    # A grayscale document leaves it alone.
    result, _ = _normalize_backdrop(gray(0.25), 0.0, 2, 2, 1)
    assert result.shape == (2, 2, 1)


def test_normalize_backdrop_infers_channels_when_none_is_given() -> None:
    """The defensive fallback for when no document names a color mode.

    ``composite()`` mirrors the ``_psd is not None`` hedge it already makes for
    ``check_pixel_size``; every current caller supplies a channel count.
    """
    assert _normalize_backdrop(1.0, 0.0, 2, 2, None)[0].shape == (2, 2, 1)
    assert _normalize_backdrop(WHITE, 0.0, 2, 2, None)[0].shape == (2, 2, 3)


def test_normalize_backdrop_rejects_an_unresolvable_channel_count() -> None:
    """One channel replicates; any other width has no reading (#710)."""
    with pytest.raises(ValueError, match="has 3 channels, expected 1 or 4"):
        _normalize_backdrop(np.ones((2, 2, 3), dtype=np.float32), 0.0, 2, 2, 4)


def test_normalize_backdrop_rejects_a_mismatched_backdrop() -> None:
    with pytest.raises(ValueError, match="cannot be expanded"):
        _normalize_backdrop((1.0, 0.0), 0.0, 2, 2, 3)
    with pytest.raises(ValueError, match="match the viewport"):
        _normalize_backdrop(np.zeros((4, 4, 3), dtype=np.float32), 0.0, 2, 2, 3)


def test_normalize_backdrop_requires_single_channel_alpha() -> None:
    """Color may be narrower than the document; alpha may not be wider than 1.

    A narrow color is widened to the document's channel count, because
    replicating a single channel across three is what compositing a grayscale
    backdrop in RGB means. A multi-channel alpha has no such reading, so it is
    rejected rather than reinterpreted (PR #721 review).
    """
    assert _normalize_backdrop(gray(0.5), 0.0, 2, 2, 3)[0].shape == (2, 2, 3)
    with pytest.raises(ValueError, match=r"alpha has shape"):
        _normalize_backdrop(1.0, np.ones((2, 2, 3), dtype=np.float32), 2, 2, 3)


# ---------------------------------------------------------------------------
# The fixed channel count (#710)
# ---------------------------------------------------------------------------


def test_widen_replicates_a_single_channel() -> None:
    assert np.array_equal(_widen(gray(0.25), 3), rgb((0.25, 0.25, 0.25)))
    # Already wide enough, or the document is single-channel: unchanged.
    canvas = rgb(RED)
    assert _widen(canvas, 3) is canvas
    narrow = gray(0.25)
    assert _widen(narrow, 1) is narrow


@pytest.mark.parametrize("channels", [1, 3])
def test_a_narrow_source_leaves_the_canvas_width_alone(channels: int) -> None:
    """The blend arithmetic broadcasts a single-channel source (#710).

    Applying one is therefore not a reason to reallocate. Consistency check:
    this held before the fixups were deleted too.
    """
    backdrop = rgb(WHITE) if channels == 3 else gray(1.0)
    compositor = Compositor((0, 0, 2, 2), backdrop, gray(0.0))
    assert compositor.channels == channels

    compositor._apply_source(gray(0.5), gray(1.0), gray(1.0), BlendMode.NORMAL)
    assert compositor.channels == channels
    assert compositor.result_over_backdrop().shape == (2, 2, channels)
    assert compositor._color_0.shape == (2, 2, channels)
    assert compositor.finish()[0].shape == (2, 2, channels)


@pytest.mark.skipif(
    not __debug__, reason="the invariant checks are asserts, stripped under -O"
)
def test_a_source_wider_than_the_canvas_is_rejected() -> None:
    """The invariant is enforced in code, not just documented (#710).

    This is the case the deleted ``np.repeat`` fixups existed for: they widened
    ``_color_0`` in place. Without them the blend would silently widen
    ``_color`` and leave ``channels`` stale, so building a compositor narrower
    than the sources it will be given is now a caught bug rather than a quiet
    one.
    """
    compositor = Compositor((0, 0, 2, 2), gray(1.0), gray(0.0))
    assert compositor.channels == 1
    with pytest.raises(AssertionError, match="source has 3 channels"):
        compositor._apply_source(rgb(BLUE), gray(1.0), gray(1.0), BlendMode.NORMAL)


class _ClipStub:
    """The only attribute ``_apply_clip_layers`` reads off its layer."""

    clip_layers: list = []


def test_clip_layers_sub_compositor_uses_the_document_width() -> None:
    """A grayscale layer in an RGB document seeds a clip sub-compositor.

    Its own color is one channel wide, so it has to be widened before it
    becomes another compositor's fixed-width canvas (#710).
    """
    compositor = Compositor((0, 0, 2, 2), rgb(WHITE), gray(0.0))
    stub = cast(Any, _ClipStub())
    result = compositor._apply_clip_layers(stub, gray(0.5), gray(1.0))
    assert result.shape == (2, 2, 3)
    assert np.array_equal(result, rgb((0.5, 0.5, 0.5)))


def test_document_backdrop_is_widened_to_the_canvas() -> None:
    """The Background layer can be narrower than the document it sits in.

    Deep knockout hands its color straight to the blend, so it is widened once
    at resolution rather than at every knockout (#710).
    """
    compositor = Compositor(
        (0, 0, 2, 2),
        rgb(WHITE),
        gray(0.0),
        document_backdrop=lambda: (gray(0.25), gray(1.0)),
    )
    color_b, alpha_b = compositor._knockout_backdrop(Knockout.DEEP)
    assert color_b.shape == (2, 2, 3)
    assert np.array_equal(color_b, rgb((0.25, 0.25, 0.25)))
    assert alpha_b.shape == (2, 2, 1)


def test_narrow_source_matches_a_pre_widened_one() -> None:
    """Broadcasting a narrow source is the same as replicating it first."""

    def run(source: np.ndarray) -> np.ndarray:
        compositor = Compositor((0, 0, 2, 2), rgb(RED), gray(1.0))
        compositor._apply_source(source, gray(0.5), gray(0.5), BlendMode.MULTIPLY)
        return compositor.finish()[0]

    assert np.allclose(run(gray(0.5)), run(rgb((0.5, 0.5, 0.5))))


# ---------------------------------------------------------------------------
# Compositor._apply_source() -- the PDF 1.4 union / knockout equations
# ---------------------------------------------------------------------------


def apply_one(
    backdrop_color: tuple[float, float, float],
    backdrop_alpha: float,
    source_color: tuple[float, float, float],
    shape: float,
    alpha: float,
    blend_mode: BlendMode = BlendMode.NORMAL,
    knockout: Knockout = Knockout.NONE,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Composite a single uniform source and return ``finish()``."""
    compositor = Compositor((0, 0, 2, 2), rgb(backdrop_color), gray(backdrop_alpha))
    compositor._apply_source(
        rgb(source_color), gray(shape), gray(alpha), blend_mode, knockout
    )
    return compositor.finish()


def test_apply_source_opaque_source_replaces_the_backdrop() -> None:
    color, shape, alpha = apply_one(WHITE, 1.0, BLUE, 1.0, 1.0)
    assert np.allclose(color[0, 0], BLUE)
    assert np.allclose(shape, 1.0)
    assert np.allclose(alpha, 1.0)


def test_apply_source_fully_transparent_source_leaves_the_backdrop() -> None:
    color, shape, alpha = apply_one(RED, 1.0, BLUE, 0.0, 0.0)
    assert np.allclose(color[0, 0], RED)
    assert np.allclose(shape, 0.0)
    assert np.allclose(alpha, 0.0)


def test_apply_source_returns_the_isolated_source_not_the_blend() -> None:
    """Over an *opaque* backdrop, the returned colour is the isolated source.

    ``finish()`` returns ``Compositor.result_isolated()``, which removes the initial
    backdrop's contribution. Compositing this result back over that backdrop is
    what reproduces the visible pixel -- here 50% blue over opaque red gives
    (0.5, 0, 0.5), which ``test_color_correction_removes_an_opaque_backdrop``
    checks explicitly.
    """
    color, _, alpha = apply_one(RED, 1.0, BLUE, 0.5, 0.5)
    assert np.allclose(color[0, 0], BLUE)
    assert np.allclose(alpha, 0.5)


def test_apply_source_over_transparent_backdrop_is_not_contaminated_toward_white() -> (
    None
):
    """Regression guard for ``utils.divide``'s 0/0 -> white fallback."""
    color, _, alpha = apply_one(WHITE, 0.0, BLUE, 0.5, 0.5)
    assert np.allclose(color[0, 0], BLUE)
    assert np.allclose(alpha, 0.5)


def test_passthrough_over_nothing_keeps_the_group_colour() -> None:
    """A pass-through group over a transparent backdrop is not whitened.

    With nothing composited anywhere, ``color_t / self._alpha`` is 0 / 0 at
    every pixel, and the group's own colour is what belongs there instead of
    ``divide()``'s default white.
    """
    compositor = Compositor((0, 0, 2, 2), rgb(WHITE), gray(0.0))
    compositor._apply_passthrough_source(rgb(BLUE), gray(0.0), gray(0.0), 1.0)
    assert np.allclose(compositor.result_over_backdrop(), rgb(BLUE))


@pytest.mark.parametrize("source_alpha", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_apply_source_matches_the_textbook_over_operator(source_alpha: float) -> None:
    """Cross-check against straight-alpha "over" computed independently.

    With a transparent initial backdrop the compositor's group equations must
    reduce to plain source-over-backdrop compositing.
    """
    backdrop_alpha = 0.75
    compositor = Compositor((0, 0, 2, 2), rgb(WHITE), gray(0.0))
    compositor._apply_source(
        rgb(RED), gray(backdrop_alpha), gray(backdrop_alpha), BlendMode.NORMAL
    )
    compositor._apply_source(
        rgb(BLUE), gray(source_alpha), gray(source_alpha), BlendMode.NORMAL
    )
    color, _, alpha = compositor.finish()

    expected_alpha = source_alpha + backdrop_alpha * (1.0 - source_alpha)
    src = np.array(BLUE) * source_alpha
    bkd = np.array(RED) * backdrop_alpha * (1.0 - source_alpha)
    expected_color = (src + bkd) / expected_alpha if expected_alpha else np.zeros(3)

    assert np.allclose(alpha, expected_alpha, atol=1e-6)
    assert np.allclose(color[0, 0], expected_color, atol=1e-6)


def test_apply_source_blend_mode_is_applied_against_the_backdrop() -> None:
    """MULTIPLY must see the running backdrop, unlike NORMAL which ignores it."""
    half_gray = (0.5, 0.5, 0.5)
    color, _, _ = apply_one(half_gray, 1.0, half_gray, 1.0, 1.0, BlendMode.MULTIPLY)
    assert np.allclose(color[0, 0], (0.25, 0.25, 0.25))


# ---------------------------------------------------------------------------
# Knockout
# ---------------------------------------------------------------------------


def build_two_layer(knockout: Knockout) -> tuple[np.ndarray, np.ndarray]:
    """Transparent backdrop, an opaque red layer, then blue at 50% alpha.

    With knockout the blue punches through the red to the initial backdrop;
    without it, blue composites over red.
    """
    compositor = Compositor((0, 0, 2, 2), rgb(WHITE), gray(0.0))
    compositor._apply_source(rgb(RED), gray(1.0), gray(1.0), BlendMode.NORMAL)
    compositor._apply_source(
        rgb(BLUE), gray(1.0), gray(0.5), BlendMode.NORMAL, knockout
    )
    color, _, alpha = compositor.finish()
    return color, alpha


def test_knockout_punches_through_to_the_initial_backdrop() -> None:
    color, alpha = build_two_layer(Knockout.SHALLOW)
    # Red is gone: the result is blue at the source's own alpha.
    assert np.allclose(color[0, 0], BLUE)
    assert np.allclose(alpha, 0.5)


def test_without_knockout_the_source_composites_over_the_running_backdrop() -> None:
    color, alpha = build_two_layer(Knockout.NONE)
    # Red is retained, so the result is opaque and half red / half blue.
    assert np.allclose(color[0, 0], (0.5, 0.0, 0.5))
    assert np.allclose(alpha, 1.0)


def test_deep_knockout_without_a_document_backdrop_matches_shallow() -> None:
    """DEEP degrades to SHALLOW when no document backdrop has been supplied."""
    assert np.allclose(
        build_two_layer(Knockout.DEEP)[0], build_two_layer(Knockout.SHALLOW)[0]
    )


def test_deep_knockout_uses_the_document_backdrop_when_present() -> None:
    compositor = Compositor(
        (0, 0, 2, 2),
        rgb(WHITE),
        gray(0.0),
        document_backdrop=lambda: (rgb(GREEN), gray(1.0)),
    )
    compositor._apply_source(rgb(RED), gray(1.0), gray(1.0), BlendMode.NORMAL)
    compositor._apply_source(
        rgb(BLUE), gray(1.0), gray(0.5), BlendMode.NORMAL, Knockout.DEEP
    )
    color, _, alpha = compositor.finish()
    # Knocked through red down to the green document backdrop, which is opaque.
    assert np.allclose(color[0, 0], (0.0, 0.5, 0.5))
    assert np.allclose(alpha, 1.0)


# ---------------------------------------------------------------------------
# Compositor.result_isolated() -- the backdrop-removal correction
# ---------------------------------------------------------------------------


def test_color_correction_is_a_no_op_for_a_transparent_backdrop() -> None:
    compositor = Compositor((0, 0, 2, 2), rgb(WHITE), gray(0.0))
    compositor._apply_source(rgb(BLUE), gray(0.5), gray(0.5), BlendMode.NORMAL)
    assert np.allclose(compositor.result_isolated(), compositor.result_over_backdrop())


def test_color_correction_removes_an_opaque_backdrop() -> None:
    """Over an opaque backdrop the raw and corrected results differ."""
    compositor = Compositor((0, 0, 2, 2), rgb(RED), gray(1.0))
    compositor._apply_source(rgb(BLUE), gray(0.5), gray(0.5), BlendMode.NORMAL)
    # Over the backdrop: what the pixel looks like, blue at 50% over red.
    over_backdrop = compositor.result_over_backdrop()
    assert np.allclose(over_backdrop[0, 0], (0.5, 0.0, 0.5))
    # Isolated: the source on its own, which re-composites to the value above.
    isolated = compositor.result_isolated()
    assert np.allclose(isolated[0, 0], BLUE)
    recomposited = isolated[0, 0] * 0.5 + np.array(RED) * 0.5
    assert np.allclose(recomposited, over_backdrop[0, 0])
