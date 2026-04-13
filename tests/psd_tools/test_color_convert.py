"""Unit tests for psd_tools.color_convert."""

import pytest

from psd_tools.color_convert import (
    cmyk_to_rgb,
    gray_to_cmyk,
    gray_to_rgb,
    hsb_to_rgb,
    rgb_to_cmyk,
    rgb_to_grayscale,
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


class TestHsbToRgb:
    def test_achromatic_zero_saturation(self):
        assert hsb_to_rgb(0.0, 0.0, 0.5) == pytest.approx((0.5, 0.5, 0.5))

    def test_achromatic_any_hue(self):
        assert hsb_to_rgb(0.33, 0.0, 0.7) == pytest.approx((0.7, 0.7, 0.7))

    def test_h_one_wraps_to_zero(self):
        """h=1.0 should give the same result as h=0.0."""
        assert hsb_to_rgb(1.0, 1.0, 1.0) == pytest.approx(hsb_to_rgb(0.0, 1.0, 1.0))

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
