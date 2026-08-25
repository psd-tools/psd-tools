"""Unit tests for the compositor's primitives.

The rest of the composite suite is end-to-end: render a fixture, compare MSE
against a reference. That is a good acceptance suite and a poor refactoring
suite -- a broken transparency term surfaces as a threshold miss on some
fixture, with no indication of which equation moved.

These tests pin the primitives directly, so a change to the compositing maths
fails with a specific, hand-checkable number. See #715.
"""

import numpy as np
import pytest

from psd_tools.composite import utils
from psd_tools.composite.composite import Compositor, _blend_backdrop, paste
from psd_tools.constants import BlendMode, ColorMode, Knockout

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
    """``paste`` selects its fill by truthiness, so 0.0 takes the zeros path.

    The two are numerically identical today. Pinned so that a change to the
    guard (``if background`` -> ``if background is not None``) stays a no-op
    rather than silently altering output. See the checklist in #711.
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


def test_divide_falls_back_to_one_on_non_finite() -> None:
    """Division by zero yields 1.0, i.e. white in normalised colour space.

    This is a deliberate policy rather than an accident, and callers depend on
    it -- see the ``np.where`` guard in ``_apply_passthrough_source``. #714
    proposes making the fallback caller-specified; this test is what that
    change has to consciously update.
    """
    assert np.array_equal(utils.divide(gray(1.0), gray(0.0)), gray(1.0))
    assert np.array_equal(utils.divide(gray(0.0), gray(0.0)), gray(1.0))


def test_divide_is_ordinary_where_the_divisor_is_non_zero() -> None:
    assert np.allclose(utils.divide(gray(1.0), gray(4.0)), gray(0.25))


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
    color, alpha = _blend_backdrop(rgb(BLUE), gray(0.5), RED, 1.0, ColorMode.RGB)
    # 50% blue over opaque red.
    assert np.allclose(color[0, 0], (0.5, 0.0, 0.5))
    assert np.allclose(alpha, 1.0)


def test_blend_backdrop_accepts_scalar_tuple_and_array_backdrops() -> None:
    """Equivalent backdrops expressed three ways must agree.

    ``composite()`` accepts a scalar, a per-channel tuple or an ndarray; #708
    proposes normalising all three at the API boundary. This pins that the
    three spellings are interchangeable so that refactor stays a no-op.
    """
    expected, _ = _blend_backdrop(rgb(BLUE), gray(0.5), WHITE, 1.0, ColorMode.RGB)
    from_scalar, _ = _blend_backdrop(rgb(BLUE), gray(0.5), 1.0, 1.0, ColorMode.RGB)
    from_array, _ = _blend_backdrop(
        rgb(BLUE), gray(0.5), rgb(WHITE), 1.0, ColorMode.RGB
    )
    assert np.allclose(expected, from_scalar)
    assert np.allclose(expected, from_array)


def test_blend_backdrop_transparent_backdrop_keeps_source_colour() -> None:
    """A transparent backdrop must not bleed its colour into the result."""
    color, alpha = _blend_backdrop(rgb(BLUE), gray(1.0), WHITE, 0.0, ColorMode.RGB)
    assert np.allclose(color[0, 0], BLUE)
    assert np.allclose(alpha, 1.0)


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
    compositor = Compositor((0, 0, 2, 2), backdrop_color, backdrop_alpha)
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

    ``finish()`` returns ``Compositor.color``, which removes the initial
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


@pytest.mark.parametrize("source_alpha", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_apply_source_matches_the_textbook_over_operator(source_alpha: float) -> None:
    """Cross-check against straight-alpha "over" computed independently.

    With a transparent initial backdrop the compositor's group equations must
    reduce to plain source-over-backdrop compositing.
    """
    backdrop_alpha = 0.75
    compositor = Compositor((0, 0, 2, 2), WHITE, 0.0)
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
    compositor = Compositor((0, 0, 2, 2), WHITE, 0.0)
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
        WHITE,
        0.0,
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
# Compositor.color -- the backdrop-removal correction
# ---------------------------------------------------------------------------


def test_color_correction_is_a_no_op_for_a_transparent_backdrop() -> None:
    compositor = Compositor((0, 0, 2, 2), WHITE, 0.0)
    compositor._apply_source(rgb(BLUE), gray(0.5), gray(0.5), BlendMode.NORMAL)
    assert np.allclose(compositor.color, compositor._color)


def test_color_correction_removes_an_opaque_backdrop() -> None:
    """Over an opaque backdrop the raw and corrected results differ."""
    compositor = Compositor((0, 0, 2, 2), RED, 1.0)
    compositor._apply_source(rgb(BLUE), gray(0.5), gray(0.5), BlendMode.NORMAL)
    # Raw: what the pixel looks like, blue at 50% over red.
    assert np.allclose(compositor._color[0, 0], (0.5, 0.0, 0.5))
    # Corrected: the isolated source, which re-composites to the raw value.
    assert np.allclose(compositor.color[0, 0], BLUE)
    recomposited = compositor.color[0, 0] * 0.5 + np.array(RED) * 0.5
    assert np.allclose(recomposited, compositor._color[0, 0])
