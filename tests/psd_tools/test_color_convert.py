"""Unit tests for psd_tools.color_convert."""

import pytest

import doctest

import psd_tools.color_convert
from psd_tools.color_convert import (
    cmyk_to_rgb,
    gray_to_cmyk,
    gray_to_rgb,
    hsb_to_rgb,
    lab_to_rgb,
    rgb_to_cmyk,
    rgb_to_grayscale,
    rgb_to_lab,
)


class TestRgbToGrayscale:
    def test_white(self):
        assert rgb_to_grayscale(1.0, 1.0, 1.0) == pytest.approx(1.0)

    def test_black(self):
        assert rgb_to_grayscale(0.0, 0.0, 0.0) == pytest.approx(0.0)

    def test_pure_red(self):
        assert rgb_to_grayscale(1.0, 0.0, 0.0) == pytest.approx(0.299)

    def test_pure_green(self):
        assert rgb_to_grayscale(0.0, 1.0, 0.0) == pytest.approx(0.587)

    def test_pure_blue(self):
        assert rgb_to_grayscale(0.0, 0.0, 1.0) == pytest.approx(0.114)

    def test_coefficients_sum_to_one(self):
        assert rgb_to_grayscale(1.0, 1.0, 1.0) == pytest.approx(0.299 + 0.587 + 0.114)


class TestRgbToCmyk:
    def test_black_special_case(self):
        assert rgb_to_cmyk(0.0, 0.0, 0.0) == (0.0, 0.0, 0.0, 1.0)

    def test_white(self):
        c, m, y, k = rgb_to_cmyk(1.0, 1.0, 1.0)
        assert (c, m, y, k) == pytest.approx((0.0, 0.0, 0.0, 0.0))

    def test_pure_red(self):
        c, m, y, k = rgb_to_cmyk(1.0, 0.0, 0.0)
        assert (c, m, y, k) == pytest.approx((0.0, 1.0, 1.0, 0.0))

    def test_pure_green(self):
        c, m, y, k = rgb_to_cmyk(0.0, 1.0, 0.0)
        assert (c, m, y, k) == pytest.approx((1.0, 0.0, 1.0, 0.0))

    def test_pure_blue(self):
        c, m, y, k = rgb_to_cmyk(0.0, 0.0, 1.0)
        assert (c, m, y, k) == pytest.approx((1.0, 1.0, 0.0, 0.0))

    def test_round_trip(self):
        """cmyk_to_rgb(rgb_to_cmyk(r, g, b)) ≈ (r, g, b) for non-black colors."""
        for r, g, b in [(1.0, 0.5, 0.25), (0.8, 0.2, 0.6), (0.5, 0.5, 0.5)]:
            result = cmyk_to_rgb(*rgb_to_cmyk(r, g, b))
            assert result == pytest.approx((r, g, b), abs=1e-6)


class TestCmykToRgb:
    def test_white(self):
        assert cmyk_to_rgb(0.0, 0.0, 0.0, 0.0) == pytest.approx((1.0, 1.0, 1.0))

    def test_black(self):
        assert cmyk_to_rgb(0.0, 0.0, 0.0, 1.0) == pytest.approx((0.0, 0.0, 0.0))

    def test_pure_cyan(self):
        assert cmyk_to_rgb(1.0, 0.0, 0.0, 0.0) == pytest.approx((0.0, 1.0, 1.0))

    def test_mid_gray(self):
        assert cmyk_to_rgb(0.0, 0.0, 0.0, 0.5) == pytest.approx((0.5, 0.5, 0.5))


# Photoshop's HSB (degrees, percent, percent) -> the RGB 0..255 it reports for
# it, read from ``SolidColor.hsb = ...; .rgb`` over the scripting bridge. The
# hues walk the whole circle: each of the six sector boundaries, one hue inside
# every sector, and both ends of the wrap (359 and 360). Two degenerate rows
# guard the short circuits -- zero saturation, where hue must not matter at
# all, and zero brightness.
#
# Unlike the Lab tables above these need no decoding: HSB to RGB is arithmetic
# inside one RGB space rather than a colorimetric transform, so no working
# space or rendering intent stands between the two columns.
_HSB_TO_RGB = [
    ((0.0, 100.0, 100.0), (255.0, 0.00778, 0.00778)),
    ((30.0, 100.0, 100.0), (255.0, 127.51556, 0.00778)),
    ((60.0, 100.0, 100.0), (255.0, 254.98444, 0.00778)),
    ((90.0, 60.0, 90.0), (160.65125, 229.49844, 91.80405)),
    ((120.0, 50.0, 80.0), (101.99844, 203.99689, 102.00623)),
    ((150.0, 100.0, 100.0), (0.00778, 255.0, 127.49222)),
    ((180.0, 40.0, 90.0), (137.70218, 229.49844, 229.49844)),
    ((210.0, 100.0, 100.0), (0.00778, 127.50778, 255.0)),
    ((240.0, 100.0, 100.0), (0.00778, 0.04669, 255.0)),
    ((270.0, 80.0, 70.0), (107.08786, 35.70374, 178.50311)),
    ((300.0, 75.0, 60.0), (152.99377, 38.25623, 153.00156)),
    ((330.0, 100.0, 100.0), (255.0, 0.00778, 127.53891)),
    ((359.0, 100.0, 100.0), (255.0, 0.00778, 4.28009)),
    ((360.0, 100.0, 100.0), (255.0, 0.00778, 0.03113)),
    ((200.0, 0.0, 60.0), (153.00156, 153.00156, 153.00156)),
    ((45.0, 100.0, 0.0), (0.0, 0.0, 0.0)),
    ((15.0, 33.0, 77.0), (196.34720, 147.74872, 131.55441)),
    ((345.0, 90.0, 45.0), (114.75311, 11.47842, 37.29904)),
]


class TestHsbToRgb:
    def test_achromatic_zero_saturation(self):
        assert hsb_to_rgb(0.0, 0.0, 0.5) == pytest.approx((0.5, 0.5, 0.5))

    def test_achromatic_any_hue(self):
        assert hsb_to_rgb(0.33, 0.0, 0.7) == pytest.approx((0.7, 0.7, 0.7))

    @pytest.mark.parametrize(
        ("h", "equivalent"),
        [
            (1.0, 0.0),
            (2.0, 0.0),
            (-1.0, 0.0),
            (-1e-17, 0.0),
            (1.5, 0.5),
            (-0.25, 0.75),
            (7.5, 0.5),
        ],
    )
    def test_hue_is_cyclic(self, h, equivalent):
        """A hue outside [0, 1) is the same colour one or more turns away.

        Only ``h == 1.0`` used to be handled, by a bare special case. Anything
        at or past a full turn missed the six-sector table and fell back to the
        achromatic ``(v, v, v)``, which is how a hue of 360 degrees arriving
        through ``paint._get_hsb`` rendered white where Photoshop renders red
        (#754). Small negative hues did reach a sector, just the wrong one:
        truncation towards zero put all of ``(-1/6, 0)`` in sector 0.

        ``-1e-17`` is the one row here that is not a #754 regression pin -- the
        old code truncated it into sector 0 and got the right answer by
        accident. It guards the new code instead: ``-1e-17 % 1.0`` is exactly
        ``1.0`` in floating point, which puts ``int(h * 6.0)`` at 6, one past
        the last sector, and is an ``IndexError`` if the wrap is applied to the
        hue alone rather than to the sector index as well.
        """
        assert hsb_to_rgb(h, 1.0, 1.0) == pytest.approx(
            hsb_to_rgb(equivalent, 1.0, 1.0)
        )

    def test_sector_0_red(self):
        r, g, b = hsb_to_rgb(0.0, 1.0, 1.0)
        assert r == pytest.approx(1.0)
        assert g == pytest.approx(0.0, abs=1e-6)
        assert b == pytest.approx(0.0, abs=1e-6)

    def test_sector_2_green(self):
        r, g, b = hsb_to_rgb(1.0 / 3.0, 1.0, 1.0)
        assert r == pytest.approx(0.0, abs=1e-6)
        assert g == pytest.approx(1.0)
        assert b == pytest.approx(0.0, abs=1e-6)

    def test_sector_4_blue(self):
        r, g, b = hsb_to_rgb(2.0 / 3.0, 1.0, 1.0)
        assert r == pytest.approx(0.0, abs=1e-6)
        assert g == pytest.approx(0.0, abs=1e-6)
        assert b == pytest.approx(1.0)

    @pytest.mark.parametrize("sector", range(6))
    def test_all_six_sectors_return_tuple(self, sector):
        h = (sector + 0.5) / 6.0
        result = hsb_to_rgb(h, 1.0, 1.0)
        assert len(result) == 3
        assert all(0.0 <= v <= 1.0 for v in result)

    @pytest.mark.parametrize(("hsb", "expected"), _HSB_TO_RGB)
    def test_matches_photoshop(self, hsb, expected):
        """Photoshop's own HSB to RGB, over the whole hue circle.

        This pins the conversion, not the reading of the descriptor: the
        divisor #754 got wrong lives in ``paint._get_hsb`` and is pinned
        against this same fixture data in
        ``tests/psd_tools/composite/test_paint.py``. What it does establish is
        that a hue expressed as a fraction of a turn -- which is what a
        corrected ``/360`` produces -- lands where Photoshop puts it, at every
        sector boundary and inside every sector.

        The tolerance is 0.1 of a code value because Photoshop's bridge reports
        RGB out of its own 15-bit store, which puts a true 0 at
        ``255 / 32768 = 0.0078`` and costs at most 0.05 anywhere in the table.
        """
        got = [
            255.0 * c
            for c in hsb_to_rgb(hsb[0] / 360.0, hsb[1] / 100.0, hsb[2] / 100.0)
        ]
        for channel, (value, want) in enumerate(zip(got, expected)):
            assert abs(value - want) <= 0.1, (hsb, channel, value, want)

    @pytest.mark.parametrize("h", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_hue_degrades_instead_of_raising(self, h):
        """A hue that names no angle has no turn to wrap onto.

        ``int(float("nan") * 6.0)`` raises, and this function is reached from
        an unvalidated descriptor, so the achromatic answer stands in -- the
        same policy ``lab_to_rgb`` applies to its own absurd inputs.
        """
        assert hsb_to_rgb(h, 1.0, 0.5) == (0.5, 0.5, 0.5)

    @pytest.mark.parametrize(
        ("s", "v", "expected"),
        [
            (1.2, 1.5, (1.0, 0.0, 0.0)),  # the pair measured in #757
            (1.2, 1.0, (1.0, 0.0, 0.0)),
            (-0.5, 0.5, (0.5, 0.5, 0.5)),  # negative saturation is achromatic
            (1.0, 2.0, (1.0, 0.0, 0.0)),
            (1.0, -1.0, (0.0, 0.0, 0.0)),
            (float("nan"), 0.5, (0.5, 0.5, 0.5)),
            (float("inf"), 0.5, (0.5, 0.0, 0.0)),
            (1.0, float("nan"), (0.0, 0.0, 0.0)),
            (1.0, float("inf"), (1.0, 0.0, 0.0)),
        ],
    )
    def test_out_of_range_saturation_and_brightness_saturate(self, s, v, expected):
        """The ``Returns:`` contract has to hold for every float, not just for
        in-range ones.

        Saturation and brightness are not angles, so unlike hue they clamp
        rather than wrap. Before #757 this function was total only in
        appearance: #754's non-finite-hue guard made it look as complete as
        ``lab_to_rgb``, while ``s = 1.2, v = 1.5`` still returned
        ``(1.5, -0.3, -0.3)`` and a NaN saturation propagated straight out. The
        harm is downstream -- ``composite_pil()`` casts with
        ``(255 * color).astype(np.uint8)``, which *wraps*, so 1.5 became byte
        126 and a fully saturated red rendered grey-teal.
        """
        result = hsb_to_rgb(0.0, s, v)
        assert all(0.0 <= c <= 1.0 for c in result), result
        assert result == pytest.approx(expected)


class TestGrayToRgb:
    def test_mid_gray(self):
        assert gray_to_rgb(0.5) == (0.5, 0.5, 0.5)

    def test_black(self):
        assert gray_to_rgb(0.0) == (0.0, 0.0, 0.0)

    def test_white(self):
        assert gray_to_rgb(1.0) == (1.0, 1.0, 1.0)


class TestGrayToCmyk:
    def test_white(self):
        assert gray_to_cmyk(1.0) == (0.0, 0.0, 0.0, 0.0)

    def test_black(self):
        assert gray_to_cmyk(0.0) == (0.0, 0.0, 0.0, 1.0)

    def test_mid_gray(self):
        assert gray_to_cmyk(0.5) == pytest.approx((0.0, 0.0, 0.0, 0.5))


# ---------------------------------------------------------------------------
# CIE L*a*b* (#743, #752)
#
# Ground truth is Photoshop 2026's own colour engine, read over the ExtendScript
# bridge as ``SolidColor.lab = ...; .rgb`` and the reverse. Its RGB working
# space is sRGB (confirmed from the profile it embeds), so the two are directly
# comparable.
#
# One correction has to be applied first. Photoshop's scripting property does
# not report ``a``/``b`` in native units -- it reports them through the signed
# 8-bit encoding it stores them in:
#
#     a_reported = a_true * (255 / 256) - 0.5
#
# which is why every neutral colour comes back as ``a = b = -0.5`` rather than
# 0. This is not a fitted correction: both constants come from the encoding, and
# undoing it takes the disagreement across 33 measured colours from ~0.87 Lab
# units to 0.014 -- so the tolerances below are chosen from the model, not from
# whatever this implementation happens to produce.
# ---------------------------------------------------------------------------


def _native(reported: float) -> float:
    """Undo Photoshop's signed 8-bit reporting encoding for ``a``/``b``."""
    return (reported + 0.5) * 256.0 / 255.0


# Lab (native) -> Photoshop's RGB, 0..255. Chroma is as Photoshop *reported* it.
_LAB_TO_RGB = [
    ((0.0, 0.0, 0.0), (1.268, 0.0, 0.031)),
    ((100.0, 0.0, 0.0), (255.0, 254.658, 254.051)),
    ((50.0, 0.0, 0.0), (120.084, 118.613, 118.084)),
    ((45.88, 1.0, 2.0), (112.590, 107.695, 104.504)),
    ((65.49, 13.0, 69.0), (202.690, 148.651, 0.0)),
    ((19.07, 52.29, -85.08), (16.957, 0.0, 177.748)),
    ((54.29, 80.8, 69.89), (255.0, 0.0, 0.0)),
    ((96.84, -14.39, 92.87), (255.0, 251.755, 0.0)),
    ((53.24, 80.09, 67.2), (251.498, 0.0, 4.303)),
    ((87.73, -86.18, 83.18), (0.0, 255.0, 0.0)),
    ((32.3, 79.19, -107.86), (92.823, 0.0, 255.0)),
    ((75.0, 25.0, -30.0), (211.468, 168.986, 239.887)),
    ((25.0, -40.0, 15.0), (0.0, 72.513, 33.509)),
    ((90.0, 5.0, -5.0), (234.175, 223.039, 235.179)),
    ((10.0, 60.0, 60.0), (91.804, 0.0, 0.934)),
]

# Photoshop clips these two somewhere we do not, so they get a named exemption
# rather than a loosened global tolerance:
#   Lab(10, 60, 60)  is outside sRGB -- Photoshop desaturates where we clip per
#                    channel, which is a gamut-mapping policy rather than a
#                    transform difference.
#   Lab(0, 0, 0)     comes back as (1.27, 0, 0.03) rather than black, which is
#                    black point compensation.
_LAB_TO_RGB_GAMUT_LIMITED = {(10.0, 60.0, 60.0): 5.0, (0.0, 0.0, 0.0): 1.0}

# Photoshop's RGB 0..255 -> the Lab it reports for it.
_RGB_TO_LAB = [
    ((0, 0, 0), (0.0, -0.5, -0.5)),
    ((255, 255, 255), (100.0, -0.5, -0.5)),
    ((128, 128, 128), (53.5828, -0.5, -0.5)),
    ((255, 0, 0), (54.2908, 79.9968, 69.1176)),
    ((0, 255, 0), (87.8204, -79.4638, 80.1758)),
    ((0, 0, 255), (29.5654, 67.5223, -112.0936)),
    ((255, 255, 0), (97.6074, -16.1885, 92.5258)),
    ((0, 255, 255), (90.6677, -50.9662, -15.4025)),
    ((255, 0, 255), (60.1685, 92.6815, -60.7637)),
    ((202, 149, 1), (65.5060, 12.5582, 68.3083)),
    ((64, 32, 192), (27.7649, 48.1452, -78.9813)),
    ((10, 120, 60), (43.9514, -40.5772, 23.9354)),
    ((230, 180, 150), (77.3834, 15.1807, 22.0677)),
    ((35, 35, 40), (13.8702, 0.4650, -3.8307)),
    ((120, 200, 255), (77.0691, -14.5231, -35.5812)),
    ((200, 60, 90), (47.8912, 56.5108, 15.6787)),
    ((90, 90, 10), (37.1552, -7.6049, 40.1998)),
    ((250, 250, 200), (97.3480, -6.3443, 23.5230)),
]


class TestLabToRgb:
    @pytest.mark.parametrize(("lab", "expected"), _LAB_TO_RGB)
    def test_matches_photoshop(self, lab, expected):
        lightness, a, b = lab
        got = [v * 255.0 for v in lab_to_rgb(lightness, _native(a), _native(b))]
        tolerance = _LAB_TO_RGB_GAMUT_LIMITED.get(lab, 0.5)
        for channel, (g, want) in enumerate(zip(got, expected)):
            assert abs(g - want) <= tolerance, (lab, channel, g, want)

    def test_white_is_exactly_white(self):
        """The white point has to be the one the matrices carry.

        Pairing the ICC PCS D50 with Lindbloom's Bradford matrices leaves the
        transform without a fixed point -- white returns 0.99981 in blue, and a
        neutral grey picks up a b of -0.025, which the compositor's truncating
        cast turns into byte 127 where Photoshop writes 128.
        """
        assert lab_to_rgb(100.0, 0.0, 0.0) == pytest.approx((1.0, 1.0, 1.0), abs=1e-7)
        assert lab_to_rgb(0.0, 0.0, 0.0) == (0.0, 0.0, 0.0)

    def test_clamps_out_of_gamut(self):
        for component in lab_to_rgb(60.0, 120.0, -120.0):
            assert 0.0 <= component <= 1.0

    @pytest.mark.parametrize(
        "value",
        [1e308, -1e308, 1e300, float("inf"), float("-inf"), float("nan")],
    )
    @pytest.mark.parametrize("axis", [0, 1, 2])
    def test_absurd_input_degrades_instead_of_raising(self, value, axis):
        """A descriptor carries unvalidated file data.

        Cubing the transfer function overflows on a large float, so writing it
        as ``f ** 3`` turns a malformed fill into an ``OverflowError`` on the
        path whose whole purpose is tolerating writers other than Photoshop.
        ``f * f * f`` saturates to infinity instead and the clamps take it from
        there; NaN degrades through ``_clamp``'s argument order.
        """
        lab = [50.0, 0.0, 0.0]
        lab[axis] = value
        result = lab_to_rgb(*lab)
        assert all(0.0 <= c <= 1.0 for c in result), result

    def test_nan_degrades_to_black_not_white(self):
        """Pins ``_clamp``'s argument order, which nothing else does.

        ``max(low, nan)`` returns ``low`` because the comparison is false;
        writing the clamp the other way round would send a NaN to *white*
        instead, and every other assertion here -- membership in [0, 1] --
        holds equally well either way.
        """
        assert lab_to_rgb(float("nan"), 0.0, 0.0) == (0.0, 0.0, 0.0)
        assert lab_to_rgb(50.0, float("nan"), float("nan")) == (0.0, 0.0, 0.0)


class TestRgbToLab:
    @pytest.mark.parametrize(("rgb", "expected"), _RGB_TO_LAB)
    def test_matches_photoshop(self, rgb, expected):
        got = rgb_to_lab(*[v / 255.0 for v in rgb])
        want = (expected[0], _native(expected[1]), _native(expected[2]))
        assert got == pytest.approx(want, abs=0.05)

    @pytest.mark.parametrize("grey", [0.0, 0.25, 0.5, 0.75, 1.0])
    def test_a_grey_is_exactly_neutral(self, grey):
        """Neutral must be 0.0, not merely near it.

        ``LAB_NEUTRAL_CHROMA`` is ``128/255``, and the compositor truncates on
        the way out, so a chroma of -0.025 -- which is what the ICC PCS white
        point gives here -- emits byte 127 instead of 128.
        """
        _, a, b = rgb_to_lab(grey, grey, grey)
        assert (a, b) == pytest.approx((0.0, 0.0), abs=1e-9)
        # The bound that actually matters: what the compositor's truncating
        # cast makes of it. The ICC PCS white point gives -0.025 here, which
        # is small but lands a byte low.
        for chroma in (a, b):
            assert int(255.0 * ((chroma + 128.0) / 255.0)) == 128

    def test_round_trips_through_lab_to_rgb(self):
        """Sanity check only.

        Both directions divide by the same white point, so this cannot detect a
        wrong one -- a D65 pairing round trips just as cleanly. The white point
        is pinned by the Photoshop tables and by the two exactness tests above.
        """
        worst = 0.0
        for r in range(0, 256, 51):
            for g in range(0, 256, 51):
                for b in range(0, 256, 51):
                    source = (r / 255.0, g / 255.0, b / 255.0)
                    back = lab_to_rgb(*rgb_to_lab(*source))
                    worst = max(worst, max(abs(x - y) for x, y in zip(back, source)))
        assert worst * 255.0 < 0.01


def test_module_doctests_run_and_pass():
    """The module's doctests are otherwise dead documentation.

    ``addopts`` carries no ``--doctest-modules`` and there is no Sphinx doctest
    build in CI, so nothing collected these until now -- which is how
    ``rgb_to_grayscale``'s example came to claim 1.0 for a call that returns
    0.9999999999999999.
    """
    result = doctest.testmod(psd_tools.color_convert, verbose=False)
    assert result.attempted > 0
    assert result.failed == 0
