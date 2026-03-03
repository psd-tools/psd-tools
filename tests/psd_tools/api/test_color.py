"""Tests for color normalization helpers in psd_tools.api.utils."""

import pytest

from psd_tools.api.utils import denormalize_color, normalize_color


class TestNormalizeColor:
    """Tests for normalize_color."""

    # --- Scalar float ---

    def test_float_identity(self) -> None:
        assert normalize_color(0.5, 8) == 0.5

    def test_float_zero(self) -> None:
        assert normalize_color(0.0, 8) == 0.0

    def test_float_one(self) -> None:
        assert normalize_color(1.0, 8) == 1.0

    def test_float_out_of_range_high(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            normalize_color(1.5, 8)

    def test_float_out_of_range_negative(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            normalize_color(-0.1, 8)

    # --- Scalar int ---

    def test_int_8bit(self) -> None:
        assert normalize_color(128, 8) == 128 / 255

    def test_int_8bit_zero(self) -> None:
        assert normalize_color(0, 8) == 0.0

    def test_int_8bit_max(self) -> None:
        assert normalize_color(255, 8) == 1.0

    def test_int_16bit(self) -> None:
        assert normalize_color(32768, 16) == 32768 / 65535

    def test_int_32bit(self) -> None:
        assert normalize_color(2147483648, 32) == 2147483648 / 4294967295

    def test_int_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            normalize_color(256, 8)

    def test_int_negative(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            normalize_color(-1, 8)

    # --- Sequence of floats ---

    def test_float_tuple(self) -> None:
        assert normalize_color((1.0, 0.5, 0.0), 8) == (1.0, 0.5, 0.0)

    def test_float_list(self) -> None:
        assert normalize_color([1.0, 0.5, 0.0], 8) == (1.0, 0.5, 0.0)

    def test_float_sequence_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="at index 1"):
            normalize_color((1.0, 1.5, 0.0), 8)

    # --- Sequence of ints ---

    def test_int_tuple(self) -> None:
        assert normalize_color((255, 128, 0), 8) == (1.0, 128 / 255, 0.0)

    def test_int_list(self) -> None:
        assert normalize_color([255, 128, 0], 8) == (1.0, 128 / 255, 0.0)

    # --- Mixed int/float sequence ---

    def test_mixed_tuple(self) -> None:
        assert normalize_color((1.0, 128, 0.5), 8) == (1.0, 128 / 255, 0.5)

    def test_mixed_list(self) -> None:
        assert normalize_color([0.0, 255, 0.5], 8) == (0.0, 1.0, 0.5)

    # --- Edge cases ---

    def test_str_rejected(self) -> None:
        with pytest.raises(TypeError, match="String"):
            normalize_color("white", 8)  # type: ignore[arg-type]

    def test_bool_rejected(self) -> None:
        with pytest.raises(TypeError, match="Bool"):
            normalize_color(True, 8)  # type: ignore[arg-type]

    def test_bool_in_sequence_rejected(self) -> None:
        with pytest.raises(TypeError, match="Bool"):
            normalize_color((True, 0.5, 0.0), 8)

    def test_empty_sequence(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            normalize_color((), 8)

    def test_invalid_depth(self) -> None:
        with pytest.raises(ValueError, match="depth"):
            normalize_color(128, 24)

    def test_returns_tuple_for_sequence(self) -> None:
        result = normalize_color([0.5], 8)
        assert isinstance(result, tuple)

    def test_returns_float_for_scalar(self) -> None:
        result = normalize_color(128, 8)
        assert isinstance(result, float)


class TestDenormalizeColor:
    """Tests for denormalize_color."""

    # --- Scalar float ---

    def test_float_to_int_8bit(self) -> None:
        assert denormalize_color(1.0, 8) == 255

    def test_float_zero(self) -> None:
        assert denormalize_color(0.0, 8) == 0

    def test_float_half_8bit(self) -> None:
        assert denormalize_color(0.5, 8) == round(0.5 * 255)

    def test_float_16bit(self) -> None:
        assert denormalize_color(1.0, 16) == 65535

    def test_float_32bit(self) -> None:
        assert denormalize_color(1.0, 32) == 4294967295

    def test_float_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            denormalize_color(2.0, 8)

    # --- Scalar int ---

    def test_int_passthrough(self) -> None:
        assert denormalize_color(128, 8) == 128

    def test_int_max_8bit(self) -> None:
        assert denormalize_color(255, 8) == 255

    def test_int_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="out of range"):
            denormalize_color(256, 8)

    # --- Sequence of floats ---

    def test_float_tuple(self) -> None:
        assert denormalize_color((1.0, 0.0, 0.5), 8) == (255, 0, round(0.5 * 255))

    def test_float_list(self) -> None:
        assert denormalize_color([1.0, 0.0], 8) == (255, 0)

    # --- Sequence of ints ---

    def test_int_tuple_passthrough(self) -> None:
        assert denormalize_color((255, 128, 0), 8) == (255, 128, 0)

    # --- Mixed ---

    def test_mixed_tuple(self) -> None:
        assert denormalize_color((1.0, 128, 0.5), 8) == (255, 128, round(0.5 * 255))

    # --- Edge cases ---

    def test_str_rejected(self) -> None:
        with pytest.raises(TypeError, match="String"):
            denormalize_color("white", 8)  # type: ignore[arg-type]

    def test_bool_rejected(self) -> None:
        with pytest.raises(TypeError, match="Bool"):
            denormalize_color(True, 8)  # type: ignore[arg-type]

    def test_bool_in_sequence_rejected(self) -> None:
        with pytest.raises(TypeError, match="Bool"):
            denormalize_color((True, False, True), 8)

    def test_returns_tuple_for_sequence(self) -> None:
        result = denormalize_color([128], 8)
        assert isinstance(result, tuple)

    def test_returns_int_for_scalar(self) -> None:
        result = denormalize_color(0.5, 8)
        assert isinstance(result, int)


class TestRoundTrip:
    """Verify normalize and denormalize are inverse operations."""

    def test_int_round_trip(self) -> None:
        """denormalize(normalize(int)) == int."""
        assert denormalize_color(normalize_color(128, 8), 8) == 128

    def test_float_round_trip(self) -> None:
        """normalize(denormalize(float)) ≈ float."""
        original = 0.5
        result = normalize_color(denormalize_color(original, 8), 8)
        assert isinstance(result, float)
        assert abs(result - original) < 1 / 255

    def test_sequence_round_trip(self) -> None:
        """denormalize(normalize(ints)) == ints."""
        original = (255, 128, 0)
        assert denormalize_color(normalize_color(original, 8), 8) == original
