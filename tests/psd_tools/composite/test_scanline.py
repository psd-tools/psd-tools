"""Tests for the exact-coverage path rasterizer.

The oracle throughout is the area the path actually covers, which for these
shapes is known in closed form. That is the whole point of #844: aggdraw
answered a quarter pixel more than the area on every side, and nothing local
can tell a quarter pixel of real antialiasing from a quarter pixel of
fabricated antialiasing.
"""

import numpy as np
import pytest

from psd_tools.composite import scanline


def _rectangle(
    left: float, top: float, right: float, bottom: float
) -> list[tuple[float, float]]:
    return [(left, top), (right, top), (right, bottom), (left, bottom)]


def test_a_pixel_aligned_path_has_no_fringe() -> None:
    """#844's own reproduction: integer vertices, so every pixel is 0 or 1.

    aggdraw returned 0.247 in the column either side of this square and 0.247
    in the row above and below it, on a path where no pixel is partly
    covered at all.
    """
    coverage = scanline.fill_coverage([_rectangle(2, 2, 14, 14)], 16, 16)

    assert set(np.unique(coverage)) == {0.0, 1.0}
    assert coverage.sum() == 144.0
    assert np.array_equal(coverage[8], np.array([0, 0] + [1] * 12 + [0, 0], np.float32))
    assert np.array_equal(coverage[:, 8], coverage[8])


@pytest.mark.parametrize(
    ("polylines", "area"),
    [
        # A rectangle 12.4 wide and 12 tall, on neither axis of the grid.
        ([_rectangle(2.3, 2.0, 14.7, 14.0)], 12.4 * 12.0),
        # Half of a 10x10 square.
        ([[(2.0, 2.0), (12.0, 2.0), (2.0, 12.0)]], 50.0),
        # A sliver a tenth of a pixel wide, wholly inside one column.
        ([_rectangle(8.3, 2.0, 8.4, 12.0)], 0.1 * 10.0),
        # Two lobes of a bow tie, which meet at a point and do not overlap.
        ([[(2.0, 2.0), (12.0, 12.0), (12.0, 2.0), (2.0, 12.0)]], 50.0),
    ],
)
def test_coverage_is_the_area_the_path_covers(polylines: list, area: float) -> None:
    coverage = scanline.fill_coverage(polylines, 16, 16)
    assert coverage.sum() == pytest.approx(area, abs=1e-5)


def test_a_curved_path_covers_its_own_area() -> None:
    """A circle, whose area is known and whose every edge pixel is partial."""
    angle = np.linspace(0, 2 * np.pi, 4096, endpoint=False)
    circle = np.stack([8 + 5 * np.cos(angle), 8 + 5 * np.sin(angle)], axis=1)

    coverage = scanline.fill_coverage([circle], 16, 16)

    # The 4096-gon is inscribed, so it is short of the circle by its own
    # chord deficit and no more.
    assert coverage.sum() == pytest.approx(np.pi * 25, abs=1e-3)


def test_a_path_covers_the_same_pixels_wherever_it_sits_on_the_grid() -> None:
    """Moving a path by a whole pixel moves its coverage by a whole pixel.

    A property pin rather than a regression pin: aggdraw satisfies this one
    too for a whole-pixel shift of explicit coordinates, and what
    ``test_vector.py`` compares to a quantization step is the drift that
    creeps in through coordinates scaled by the document size, one layer up.
    What this holds is that nothing in the accumulation itself depends on
    where on the grid the path sits -- the answer is an area, and an area
    does not move.
    """
    here = scanline.fill_coverage([_rectangle(2.37, 3.11, 11.42, 12.88)], 24, 24)
    there = scanline.fill_coverage([_rectangle(3.37, 4.11, 12.42, 13.88)], 24, 24)

    assert here[:-1, :-1] == pytest.approx(there[1:, 1:], abs=1e-6)
    assert here.sum() > 80, "the shape is not on the canvas"


def test_a_subpath_inside_another_cuts_a_hole_whichever_way_it_winds() -> None:
    """The even-odd rule, which is the one PSD uses.

    A region enclosed twice is outside again, so which way the inner subpath
    turns makes no difference -- that is what separates even-odd from
    non-zero, where winding the inner one the same way as the outer would
    swallow it and fill the square solid.

    Photoshop was asked. Two nested rectangles were forged into one component
    of a real layer, once wound alike and once against, and Photoshop 2026
    rasterized *both* to the same ring: 3000 of the 4200 pixels its outer
    rectangle covers, with the 1200 of the inner one empty. See
    :py:func:`test_vector.test_photoshop_reads_a_combined_path_even_odd`.
    """
    outer = _rectangle(2, 2, 14, 14)
    inner = _rectangle(5, 5, 11, 11)

    for label, second in (("against", list(reversed(inner))), ("alike", inner)):
        coverage = scanline.fill_coverage([outer, second], 16, 16)
        assert coverage.sum() == 144.0 - 36.0, label
        assert coverage[8, 8] == 0.0, label

    # A third ring inside the hole is enclosed three times, so it is inside
    # again -- the alternation the rule is named for.
    deeper = scanline.fill_coverage([outer, inner, _rectangle(7, 7, 9, 9)], 16, 16)
    assert deeper.sum() == 144.0 - 36.0 + 4.0
    assert deeper[8, 8] == 1.0


@pytest.mark.parametrize(
    ("polyline", "area"),
    [
        (_rectangle(-5, -5, 21, 21), 256.0),  # over every edge at once
        (_rectangle(-5, -5, 8, 21), 8 * 16.0),  # off the left
        (_rectangle(8, -5, 21, 21), 8 * 16.0),  # off the right
        (_rectangle(-5, 8, 21, 21), 16 * 8.0),  # off the bottom
        (_rectangle(-1e5, -1e5, 1e5, 1e5), 256.0),  # far enough to be absurd
        (_rectangle(-30, -30, -20, -20), 0.0),  # wholly outside
    ],
)
def test_a_path_off_the_canvas_covers_what_is_on_it(
    polyline: list, area: float
) -> None:
    """Coverage is clipped to the canvas, not the path.

    The far case also pins that the work is bounded: cuts are made only at
    the grid lines the canvas has, so a path a hundred thousand pixels wide
    costs what one the size of the canvas costs.
    """
    assert scanline.fill_coverage([polyline], 16, 16).sum() == pytest.approx(area)


def test_a_contour_carrying_a_coordinate_that_is_not_a_number_is_dropped() -> None:
    """Whole, not segment by segment.

    A contour is closed implicitly, so dropping one segment of it leaves the
    rest open, and an open contour under signed-area accumulation leaks its
    winding across every row it touches rather than closing on itself.
    """
    square = _rectangle(2, 2, 14, 14)
    for bad in (np.nan, np.inf, -np.inf):
        broken = [(bad, 0.0), (3.0, 0.0), (3.0, 3.0)]
        coverage = scanline.fill_coverage([square, broken], 16, 16)
        assert np.isfinite(coverage).all(), bad
        assert coverage.sum() == 144.0, bad


@pytest.mark.parametrize(("width", "height"), [(0, 16), (16, 0), (0, 0), (-1, 16)])
def test_a_viewport_with_no_pixels_rasterizes_to_no_pixels(
    width: int, height: int
) -> None:
    coverage = scanline.fill_coverage([_rectangle(2, 2, 14, 14)], width, height)
    assert coverage.shape == (max(height, 0), max(width, 0))


@pytest.mark.parametrize(
    "polylines", [[], [[(3.0, 3.0)]], [[(2.0, 2.0), (8.0, 2.0), (2.0, 2.0)]]]
)
def test_a_path_with_no_area_draws_nothing(polylines: list) -> None:
    """No contour, a single point, and a contour that doubles back on itself."""
    assert scanline.fill_coverage(polylines, 16, 16).sum() == 0.0


def test_the_bands_the_canvas_is_summed_in_do_not_show() -> None:
    """Rows are split and accumulated a band at a time, to bound peak memory.

    A band boundary is a seam in the implementation and must not be one in
    the answer, so the same path is rasterized whole and one row at a time.
    """
    angle = np.linspace(0, 2 * np.pi, 512, endpoint=False)
    circle = np.stack([32 + 28 * np.cos(angle), 32 + 28 * np.sin(angle)], axis=1)
    diagonal = [(-10.0, -10.0), (70.0, 5.0), (5.0, 70.0)]

    whole = scanline.fill_coverage([circle, diagonal], 64, 64)

    for cells, pieces in ((67 * 1, 1), (67 * 7, 1 << 20), (1 << 22, 3)):
        banded = scanline.fill_coverage.__globals__  # noqa: SLF001
        saved = (banded["_BAND_CELLS"], banded["_BAND_PIECES"])
        banded["_BAND_CELLS"], banded["_BAND_PIECES"] = cells, pieces
        try:
            assert scanline.fill_coverage([circle, diagonal], 64, 64) == pytest.approx(
                whole, abs=1e-6
            ), f"a seam at {cells} cells / {pieces} pieces"
        finally:
            banded["_BAND_CELLS"], banded["_BAND_PIECES"] = saved


def test_a_straight_edge_is_not_subdivided() -> None:
    """PSD stores a straight edge as a cubic with both handles on the anchors.

    The second-difference bound alone reads that as maximally curved -- it is
    a degenerate parametrization, not a bend -- and would spend hundreds of
    points on a line. Most of the corpus is straight edges.
    """
    start = np.array([[0.0, 0.0]])
    end = np.array([[512.0, 0.0]])

    assert len(scanline.flatten_cubics(start, start, end, end)) == 1
    # A handle far enough off the chord to matter is still subdivided.
    bent = np.array([[256.0, 40.0]])
    assert len(scanline.flatten_cubics(start, bent, bent, end)) > 50


def test_a_handle_past_the_end_point_is_not_a_straight_line() -> None:
    """Flatness is distance from the *chord*, not from the line through it.

    Both handles here sit on that line, so every distance measures zero, but
    they reach a hundred pixels past the end point and the curve runs out
    along the line and back. Taken as one chord it strays 74 pixels, against
    a promised 0.002.
    """
    start, end = np.array([[0.0, 1.0]]), np.array([[1.0, 1.0]])
    far = np.array([[100.0, 1.0]])

    assert len(scanline.flatten_cubics(start, far, far, end)) > 50
    # Nudged off the line, where the excursion no longer cancels in signed
    # area, the shortcut used to lose the coverage outright.
    polyline = scanline.flatten_cubics(
        start, np.array([[100.0, 1.002]]), np.array([[100.0, 0.998]]), end
    )
    assert scanline.fill_coverage([polyline], 110, 4).sum() > 0.05

    # A straight edge as PSD stores one -- handles on the anchors -- is still
    # taken in a single step, however long it is.
    assert len(scanline.flatten_cubics(start, start, end, end)) == 1


def test_a_curve_that_returns_to_its_own_start_is_not_a_straight_line() -> None:
    """The chord of a loop has no length, and a length is what the bound is.

    Both handles measure zero against a chord of zero length however far off
    they reach, so the collinearity short-circuit read this teardrop as
    straight and flattened it to the single point it starts and ends on --
    28.8 square pixels of coverage gone.
    """
    start = np.array([[5.0, 5.0]])
    polyline = scanline.flatten_cubics(
        start, np.array([[17.0, 13.0]]), np.array([[-7.0, 13.0]]), start
    )

    assert len(polyline) > 50
    assert scanline.fill_coverage([polyline], 24, 24).sum() == pytest.approx(
        28.8, abs=0.05
    )


def test_a_flattened_curve_stays_within_the_flatness_bound() -> None:
    """The polyline never strays further from its curve than it promises."""
    rng = np.random.default_rng(844)
    for _ in range(60):
        knots = rng.uniform(-60, 60, (4, 1, 2))
        polyline = scanline.flatten_cubics(*knots)
        t = np.linspace(0, 1, 2001)[:, None]
        s = 1 - t
        curve = (
            s**3 * knots[0]
            + 3 * s**2 * t * knots[1]
            + 3 * s * t**2 * knots[2]
            + t**3 * knots[3]
        )
        polyline = np.concatenate([polyline, knots[3]])
        nearest = np.full(len(curve), np.inf)
        for a, b in zip(polyline[:-1], polyline[1:]):
            along = b - a
            length = max(float(along @ along), 1e-300)
            where = np.clip(((curve - a) @ along) / length, 0, 1)[:, None]
            nearest = np.minimum(
                nearest, np.linalg.norm(curve - (a + where * along), axis=1)
            )
        assert nearest.max() <= scanline._FLATNESS
