import logging

import pytest

from .test_composite import check_composite_quality, check_icc_composite_quality

logger = logging.getLogger(__name__)


# these tests fail because legacy adjustment layers are recognized as PixelLayers with no bounding box
@pytest.mark.parametrize(
    "adjustment, colormode", 
    [
        ("brightnesscontrast_legacy", "rgb"),
        ("brightnesscontrast_legacy", "cmyk"),
        ("brightnesscontrast_legacy", "grayscale"),
    ]
)
@pytest.mark.xfail
def test_legacy_brightnesscontrast(adjustment: str, colormode: str) -> None:
    filename = f"adjustments/{adjustment}_{colormode}"
    check_icc_composite_quality(filename, threshold=0.0005)


adjustment_test_list = [
    ("brightnesscontrast", "rgb"),
    ("brightnesscontrast", "cmyk"),
    ("brightnesscontrast", "grayscale"),
    ("levels", "rgb"),
    ("levels", "cmyk"),
    ("levels", "grayscale"),
    ("curves", "rgb"),
    ("curves", "cmyk"),
    ("curves", "grayscale"),
    ("exposure", "rgb"),
    ("exposure", "grayscale"),
    ("invert", "rgb"),
    ("invert", "cmyk"),
    ("invert", "grayscale"),
    ("posterize", "rgb"),
    ("posterize", "cmyk"),
    ("posterize", "grayscale"),
    # TODO: implement threshold on CMYK
    ("threshold", "rgb"),
    ("threshold", "grayscale"),
    ("threshold_16bits", "rgb"),
    ("threshold_16bits", "grayscale"),
]


@pytest.mark.parametrize("adjustment, colormode", adjustment_test_list,)
def test_adjustment_composite_icc(adjustment: str, colormode: str) -> None:
    filename = f"adjustments/{adjustment}_{colormode}"
    check_icc_composite_quality(filename, threshold=0.0005)


@pytest.mark.parametrize("adjustment, colormode", adjustment_test_list,)
def test_adjustment_composite_error(adjustment: str, colormode: str) -> None:
    filename = f"adjustments/{adjustment}_{colormode}.psd"
    check_composite_quality(filename, 0.0005, False)


@pytest.mark.parametrize(
    "number", 
    [
        ("1"),
        ("2"),
        ("3"),
        ("4"),
        ("5"),
    ]
)
def test_adjustment_nested_composition(number) -> None:
    filename = f"adjustments/adjustment_nested_composition_{number}"
    check_icc_composite_quality(filename, threshold=0.0005)
    check_composite_quality(f"{filename}.psd", 0.0005, False)


def test_adjustment_clipping() -> None:
    filename = f"adjustments/adjustment_clipping"
    check_icc_composite_quality(filename, threshold=0.0005)
    check_composite_quality(f"{filename}.psd", 0.0005, False)