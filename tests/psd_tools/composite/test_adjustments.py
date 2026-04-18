import logging

import pytest

from .test_composite import check_composite_quality, check_icc_composite_quality

logger = logging.getLogger(__name__)

LOOSE = 5e-4  # tolerance for approximate adjustment algorithms which can be improved (e.g. brightness/contrast)
ACCURATE = 5e-5  # tolerance for accurate adjustment algorithms (e.g. curves)
STRICT = 5e-6  # tolerance for precise adjustment algorithms (e.g. threshold)

TOLERANCES = {
    "brightnesscontrast": LOOSE,
    "levels": ACCURATE,
    "curves": ACCURATE,
    "exposure": LOOSE,
    "invert": ACCURATE,
    "posterize": ACCURATE,
    "threshold": STRICT,
}


# Brightness & Contrast
brightnesscontrast_tests = ["brightnesscontrast", "brightnesscontrast_legacy"]


@pytest.mark.parametrize("name", brightnesscontrast_tests)
@pytest.mark.parametrize("colormode", ["rgb", "cmyk", "grayscale"])
def test_brightnesscontrast_composite_icc(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}"
    if name.endswith("legacy"):
        pytest.xfail(
            "legacy adjustment layers recognized as PixelLayers with no bounding box"
        )
    check_icc_composite_quality(filename, TOLERANCES["brightnesscontrast"])


@pytest.mark.parametrize("name", brightnesscontrast_tests)
@pytest.mark.parametrize("colormode", ["rgb", "cmyk", "grayscale"])
def test_brightnesscontrast_composite_error(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}.psd"
    if name.endswith("legacy"):
        pytest.xfail(
            "legacy adjustment layers recognized as PixelLayers with no bounding box"
        )
    check_composite_quality(filename, TOLERANCES["brightnesscontrast"], False)


# Levels
levels_tests = ["levels"]


@pytest.mark.parametrize("name", levels_tests)
@pytest.mark.parametrize("colormode", ["rgb", "cmyk", "grayscale"])
def test_levels_composite_icc(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}"
    check_icc_composite_quality(filename, TOLERANCES["levels"])


@pytest.mark.parametrize("name", levels_tests)
@pytest.mark.parametrize("colormode", ["rgb", "cmyk", "grayscale"])
def test_levels_composite_error(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}.psd"
    check_composite_quality(filename, TOLERANCES["levels"], False)


# Curves
curves_tests = ["curves"]


@pytest.mark.parametrize("name", curves_tests)
@pytest.mark.parametrize("colormode", ["rgb", "cmyk", "grayscale"])
def test_curves_composite_icc(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}"
    check_icc_composite_quality(filename, TOLERANCES["curves"])


@pytest.mark.parametrize("name", curves_tests)
@pytest.mark.parametrize("colormode", ["rgb", "cmyk", "grayscale"])
def test_curves_composite_error(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}.psd"
    check_composite_quality(filename, TOLERANCES["curves"], False)


# Exposure
exposure_tests = ["exposure"]


@pytest.mark.parametrize("name", exposure_tests)
@pytest.mark.parametrize("colormode", ["rgb", "grayscale"])
def test_exposure_composite_icc(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}"
    check_icc_composite_quality(filename, TOLERANCES["exposure"])


@pytest.mark.parametrize("name", exposure_tests)
@pytest.mark.parametrize("colormode", ["rgb", "grayscale"])
def test_exposure_composite_error(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}.psd"
    check_composite_quality(filename, TOLERANCES["exposure"], False)


# Invert
invert_tests = ["invert"]


@pytest.mark.parametrize("name", invert_tests)
@pytest.mark.parametrize("colormode", ["rgb", "cmyk", "grayscale"])
def test_invert_composite_icc(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}"
    check_icc_composite_quality(filename, TOLERANCES["invert"])


@pytest.mark.parametrize("name", invert_tests)
@pytest.mark.parametrize("colormode", ["rgb", "cmyk", "grayscale"])
def test_invert_composite_error(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}.psd"
    check_composite_quality(filename, TOLERANCES["invert"], False)


# Posterize
posterize_tests = ["posterize", "posterize_16bits"]


@pytest.mark.parametrize("name", posterize_tests)
@pytest.mark.parametrize("colormode", ["rgb", "cmyk", "grayscale"])
def test_posterize_composite_icc(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}"
    check_icc_composite_quality(filename, TOLERANCES["posterize"])


@pytest.mark.parametrize("name", posterize_tests)
@pytest.mark.parametrize("colormode", ["rgb", "cmyk", "grayscale"])
def test_posterize_composite_error(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}.psd"
    check_composite_quality(filename, TOLERANCES["posterize"], False)


# Threshold
threshold_tests = ["threshold", "threshold_16bits"]


@pytest.mark.parametrize("name", threshold_tests)
@pytest.mark.parametrize("colormode", ["rgb", "grayscale"])  # CMYK not implemented
def test_threshold_composite_icc(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}"
    check_icc_composite_quality(filename, TOLERANCES["threshold"])


@pytest.mark.parametrize("name", threshold_tests)
@pytest.mark.parametrize("colormode", ["rgb", "grayscale"])  # CMYK not implemented
def test_threshold_composite_error(name: str, colormode: str) -> None:
    filename = f"adjustments/{name}_{colormode}.psd"
    check_composite_quality(filename, TOLERANCES["threshold"], False)


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
