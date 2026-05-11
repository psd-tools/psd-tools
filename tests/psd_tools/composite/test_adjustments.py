import logging

import pytest

from .test_composite import check_composite_quality, check_icc_composite_quality

logger = logging.getLogger(__name__)

# Tolerances used for MSE computation over test images (shape (200, 200, C), values in [0,1])

LOOSE = 5e-4  # tolerance for approximate adjustment algorithms which can be improved (e.g. brightness/contrast)
ACCURATE = 5e-5  # tolerance for accurate adjustment algorithms (e.g. curves)
STRICT = 5e-6  # tolerance for precise adjustment algorithms (e.g. threshold)


# Brightness & Contrast
brightnesscontrast_tests = {
    "brightnesscontrast": LOOSE,
    "brightnesscontrast_legacy": LOOSE,
}
brightnesscontrast_colorspaces = ["rgb", "cmyk", "grayscale"]


@pytest.mark.parametrize("name", brightnesscontrast_tests.keys())
@pytest.mark.parametrize("colormode", brightnesscontrast_colorspaces)
def test_brightnesscontrast_composite_icc(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}"
    if name.endswith("legacy"):
        pytest.xfail(
            "legacy adjustment layers recognized as PixelLayers with no bounding box"
        )
    check_icc_composite_quality(filename, brightnesscontrast_tests[name])


@pytest.mark.parametrize("name", brightnesscontrast_tests.keys())
@pytest.mark.parametrize("colormode", brightnesscontrast_colorspaces)
def test_brightnesscontrast_composite_error(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}.psd"
    if name.endswith("legacy"):
        pytest.xfail(
            "legacy adjustment layers recognized as PixelLayers with no bounding box"
        )
    check_composite_quality(filename, brightnesscontrast_tests[name], False)


# Levels
levels_tests = {
    "levels": ACCURATE,
}
levels_colorspaces = ["rgb", "cmyk", "grayscale"]


@pytest.mark.parametrize("name", levels_tests.keys())
@pytest.mark.parametrize("colormode", levels_colorspaces)
def test_levels_composite_icc(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}"
    check_icc_composite_quality(filename, levels_tests[name])


@pytest.mark.parametrize("name", levels_tests.keys())
@pytest.mark.parametrize("colormode", levels_colorspaces)
def test_levels_composite_error(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}.psd"
    check_composite_quality(filename, levels_tests[name], False)


# Curves
curves_tests = {
    "curves": ACCURATE,
}
curves_colorspaces = ["rgb", "cmyk", "grayscale"]


@pytest.mark.parametrize("name", curves_tests.keys())
@pytest.mark.parametrize("colormode", curves_colorspaces)
def test_curves_composite_icc(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}"
    check_icc_composite_quality(filename, curves_tests[name])


@pytest.mark.parametrize("name", curves_tests.keys())
@pytest.mark.parametrize("colormode", curves_colorspaces)
def test_curves_composite_error(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}.psd"
    check_composite_quality(filename, curves_tests[name], False)


# Exposure
exposure_tests = {
    "exposure": ACCURATE,
}
exposure_colorspaces = ["rgb", "grayscale"]


@pytest.mark.parametrize("name", exposure_tests.keys())
@pytest.mark.parametrize("colormode", exposure_colorspaces)
def test_exposure_composite_icc(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}"
    check_icc_composite_quality(filename, exposure_tests[name])


@pytest.mark.parametrize("name", exposure_tests.keys())
@pytest.mark.parametrize("colormode", exposure_colorspaces)
def test_exposure_composite_error(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}.psd"
    check_composite_quality(filename, exposure_tests[name], False)


# Hue/Saturation
huesaturation_tests = {
    "huesaturation": LOOSE,  # lower accuracy is due to how _apply_saturation works
    "huesaturation_saturation": ACCURATE,  # test saturation in isolation
    "huesaturation_lightness": ACCURATE,  # test lightness in isolation
    "huesaturation_colorize": ACCURATE,
}
huesaturation_colorspaces = ["rgb"]  # CMYK not implemented


@pytest.mark.parametrize("name", huesaturation_tests.keys())
@pytest.mark.parametrize("colormode", huesaturation_colorspaces)
def test_huesaturation_composite_icc(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}"
    check_icc_composite_quality(filename, huesaturation_tests[name])


@pytest.mark.parametrize("name", huesaturation_tests.keys())
@pytest.mark.parametrize("colormode", huesaturation_colorspaces)
def test_huesaturation_composite_error(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}.psd"
    check_composite_quality(filename, huesaturation_tests[name], False)


# Invert
invert_tests = {
    "invert": ACCURATE,
}
invert_colorspaces = ["rgb", "cmyk", "grayscale"]


@pytest.mark.parametrize("name", invert_tests.keys())
@pytest.mark.parametrize("colormode", invert_colorspaces)
def test_invert_composite_icc(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}"
    check_icc_composite_quality(filename, invert_tests[name])


@pytest.mark.parametrize("name", invert_tests.keys())
@pytest.mark.parametrize("colormode", invert_colorspaces)
def test_invert_composite_error(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}.psd"
    check_composite_quality(filename, invert_tests[name], False)


# Posterize
posterize_tests = {
    "posterize": ACCURATE,
    "posterize_16bits": ACCURATE,
}
posterize_colorspaces = ["rgb", "cmyk", "grayscale"]


@pytest.mark.parametrize("name", posterize_tests.keys())
@pytest.mark.parametrize("colormode", posterize_colorspaces)
def test_posterize_composite_icc(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}"
    check_icc_composite_quality(filename, posterize_tests[name])


@pytest.mark.parametrize("name", posterize_tests.keys())
@pytest.mark.parametrize("colormode", posterize_colorspaces)
def test_posterize_composite_error(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}.psd"
    check_composite_quality(filename, posterize_tests[name], False)


# Threshold
threshold_tests = {
    "threshold": STRICT,
    "threshold_16bits": STRICT,
}
threshold_colorspaces = ["rgb", "grayscale"]  # CMYK not implemented


@pytest.mark.parametrize("name", threshold_tests.keys())
@pytest.mark.parametrize("colormode", threshold_colorspaces)
def test_threshold_composite_icc(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}"
    check_icc_composite_quality(filename, threshold_tests[name])


@pytest.mark.parametrize("name", threshold_tests.keys())
@pytest.mark.parametrize("colormode", threshold_colorspaces)
def test_threshold_composite_error(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}.psd"
    check_composite_quality(filename, threshold_tests[name], False)


# Nested composition
@pytest.mark.parametrize("number", ["1", "2", "3", "4", "5"])
def test_adjustment_nested_composition(number) -> None:
    filename = f"adjustments/adjustment_nested_composition_{number}"
    check_icc_composite_quality(filename, 0.0005)
    check_composite_quality(f"{filename}.psd", 0.0005, False)


# Clipping
def test_adjustment_clipping() -> None:
    filename = "adjustments/adjustment_clipping"
    check_icc_composite_quality(filename, 0.0005)
    check_composite_quality(f"{filename}.psd", 0.0005, False)
