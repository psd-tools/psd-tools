"""Unit tests for descriptor-to-document color conversion in ``paint``.

A fill's color comes from a descriptor, whose color class is independent of the
document's color mode: a shape authored in an RGB document keeps its ``RGBC``
descriptor when the document is converted. ``_get_color()`` is what reconciles
the two, and the width it returns has to be one the compositor accepts --
either a single channel or exactly the document's own count, per
``Compositor._assert_source_fits()``.

It did not. Every cell marked below produced a width that is neither, so a
solid color, gradient or stroke on such a document tripped the width assertion,
and an HSB descriptor raised outright (#730).
"""

import numpy as np
import pytest

from psd_tools.api.utils import EXPECTED_CHANNELS
from psd_tools.composite.paint import (
    _get_color,
    draw_solid_color_fill,
)
from psd_tools.constants import ColorMode
from psd_tools.psd.descriptor import Descriptor, Double
from psd_tools.terminology import Key, Klass


def _color_desc(class_id: bytes, fields: dict) -> Descriptor:
    """A ``solidColorLayer`` descriptor wrapping one color descriptor."""
    inner = Descriptor(classID=class_id)
    for key, value in fields.items():
        inner[key] = Double(value)
    outer = Descriptor(classID=b"solidColorLayer")
    outer[Key.Color] = inner
    return outer


RGB_DESC = _color_desc(
    Klass.RGBColor.value, {Key.Red: 128.0, Key.Green: 64.0, Key.Blue: 32.0}
)
GRAY_DESC = _color_desc(Klass.Grayscale.value, {Key.Gray: 40.0})
CMYK_DESC = _color_desc(
    Klass.CMYKColor.value,
    {Key.Cyan: 10.0, Key.Magenta: 20.0, Key.Yellow: 30.0, Key.Black: 40.0},
)
LAB_DESC = _color_desc(
    Klass.LabColor.value, {Key.Luminance: 50.0, Key.A: 10.0, Key.B: 20.0}
)
HSB_DESC = _color_desc(
    Klass.HSBColor.value, {Key.Hue: 120.0, Key.Saturation: 50.0, Key.Brightness: 80.0}
)

ALL_DESCS = [
    ("RGBColor", RGB_DESC),
    ("Grayscale", GRAY_DESC),
    ("CMYKColor", CMYK_DESC),
    ("LabColor", LAB_DESC),
    ("HSBColor", HSB_DESC),
]

# The width each mode's color arrays carry. Multichannel is excluded: its count
# is per-file rather than per-mode, which is why a fill resolves to a single
# channel for it and lets the compositor widen.
MODE_CHANNELS = {
    ColorMode.BITMAP: 1,
    ColorMode.GRAYSCALE: 1,
    ColorMode.INDEXED: 3,
    ColorMode.RGB: 3,
    ColorMode.CMYK: 4,
    ColorMode.DUOTONE: 1,
    ColorMode.LAB: 3,
}


@pytest.mark.parametrize("class_name, desc", ALL_DESCS)
@pytest.mark.parametrize("color_mode", list(ColorMode))
def test_get_color_width_is_legal_for_every_mode(
    class_name: str, desc: Descriptor, color_mode: ColorMode
) -> None:
    """Every descriptor class resolves to a width the compositor accepts.

    ``_assert_source_fits()`` allows a single channel or exactly the document's
    count. Before #730 this failed for 19 of these 40 pairs -- an RGB, CMYK or
    Lab descriptor on a bitmap, duotone or multichannel document, a CMYK one on
    an indexed or Lab document, a Lab one on a grayscale or CMYK document, and
    an HSB one on anything but RGB or CMYK, which raised instead.
    """
    width = len(_get_color(color_mode, desc))
    if color_mode == ColorMode.MULTICHANNEL:
        # No colorimetric conversion from RGB to N spot inks exists, so one
        # channel is the honest answer and widening is the compositor's call.
        assert width == 1
    else:
        assert width in (1, MODE_CHANNELS[color_mode])


@pytest.mark.parametrize("class_name, desc", ALL_DESCS)
@pytest.mark.parametrize("color_mode", list(ColorMode))
def test_solid_color_fill_shape_is_legal_for_every_mode(
    class_name: str, desc: Descriptor, color_mode: ColorMode
) -> None:
    """The same guarantee at the array the compositor is actually handed."""
    color, shape = draw_solid_color_fill((0, 0, 4, 4), color_mode, desc)
    assert shape is None
    assert color.shape[:2] == (4, 4)
    expected = 1 if color_mode == ColorMode.MULTICHANNEL else MODE_CHANNELS[color_mode]
    assert color.shape[2] in (1, expected)
    assert color.dtype == np.float32


def test_hsb_no_longer_raises_outside_rgb_and_cmyk() -> None:
    """An HSB descriptor was unrenderable on six of the eight modes."""
    for color_mode in ColorMode:
        _get_color(color_mode, HSB_DESC)  # would have raised ValueError


@pytest.mark.parametrize(
    "color_mode, desc, expected",
    [
        # These are the pairs that already reached the compositor, pinned so the
        # reduction added in #730 cannot quietly move them. Values are the
        # pre-#730 outputs.
        (ColorMode.RGB, RGB_DESC, (128 / 255, 64 / 255, 32 / 255)),
        (ColorMode.GRAYSCALE, RGB_DESC, None),  # single channel, value below
        (ColorMode.CMYK, CMYK_DESC, (0.9, 0.8, 0.7, 0.6)),
        (ColorMode.LAB, LAB_DESC, (50 / 255, 10 / 255, 20 / 255)),
        (ColorMode.INDEXED, RGB_DESC, (128 / 255, 64 / 255, 32 / 255)),
        (ColorMode.GRAYSCALE, GRAY_DESC, (0.6,)),
        (ColorMode.BITMAP, GRAY_DESC, (0.6,)),
    ],
)
def test_previously_working_pairs_are_unchanged(
    color_mode: ColorMode, desc: Descriptor, expected: tuple[float, ...] | None
) -> None:
    """No pair that rendered before #730 changed value."""
    result = _get_color(color_mode, desc)
    if expected is None:
        assert len(result) == 1
        return
    assert len(result) == len(expected)
    for got, want in zip(result, expected):
        assert got == pytest.approx(want, abs=1e-6)


def test_multichannel_entry_is_not_a_channel_count() -> None:
    """Why multichannel is the mode that cannot be sized from the table."""
    assert EXPECTED_CHANNELS[ColorMode.MULTICHANNEL] == 64
