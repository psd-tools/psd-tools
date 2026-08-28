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
from PIL import Image

from psd_tools import PSDImage
from psd_tools.api.pil_io import post_process
from psd_tools.api.utils import EXPECTED_CHANNELS
from psd_tools.composite import composite
from psd_tools.composite.paint import (
    _get_color,
    draw_solid_color_fill,
)
from psd_tools.constants import ColorMode, Tag
from psd_tools.psd.descriptor import Descriptor, Double
from psd_tools.terminology import Key, Klass

from ..utils import full_name


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
        # pre-#730 outputs, with one deliberate exception: the Lab row moved in
        # #743, which is what that issue is. Its pre-#730 value was
        # (50/255, 10/255, 20/255) -- a divisor that suited none of the three.
        (ColorMode.RGB, RGB_DESC, (128 / 255, 64 / 255, 32 / 255)),
        (ColorMode.GRAYSCALE, RGB_DESC, None),  # single channel, value below
        (ColorMode.CMYK, CMYK_DESC, (0.9, 0.8, 0.7, 0.6)),
        (ColorMode.LAB, LAB_DESC, (50 / 100, (10 + 128) / 255, (20 + 128) / 255)),
        (ColorMode.INDEXED, RGB_DESC, (128 / 255, 64 / 255, 32 / 255)),
        (ColorMode.GRAYSCALE, GRAY_DESC, (0.6,)),
        (ColorMode.BITMAP, GRAY_DESC, (0.6,)),
    ],
)
def test_previously_working_pairs_are_unchanged(
    color_mode: ColorMode, desc: Descriptor, expected: tuple[float, ...] | None
) -> None:
    """No pair that rendered before #730 changed value, bar the Lab one.

    Lab is the exception on purpose: #743 is the finding that its value was
    wrong all along, so pinning the old number here would pin the bug. Every
    other row is unmoved.
    """
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


@pytest.mark.parametrize(
    "lab",
    [
        (50.0, 10.0, 20.0),
        (20.0, -90.0, 60.0),
        (65.49, 13.0, 69.0),
        (45.0, 40.0, -50.0),
    ],
)
@pytest.mark.parametrize(
    "color_mode",
    [
        ColorMode.BITMAP,
        ColorMode.GRAYSCALE,
        ColorMode.DUOTONE,
        ColorMode.MULTICHANNEL,
        ColorMode.CMYK,
        ColorMode.RGB,
        ColorMode.INDEXED,
        ColorMode.LAB,
    ],
)
def test_lab_chroma_reaches_every_target(
    lab: tuple[float, float, float], color_mode: ColorMode
) -> None:
    """``a`` and ``b`` move the result on every document mode.

    This is the inverse of the test it replaces. #742 deliberately reduced a Lab
    colour from ``L`` alone for the narrow modes and read the raw ``/255``
    triple for the wide ones, and `test_lab_reduces_from_lightness_alone`
    pinned that by asserting negating a/b changed nothing. It is now a real
    conversion, so negating the chroma has to move the answer -- otherwise the
    colour is being thrown away again.

    The parameters are chosen so that negating a/b changes the luminance too;
    for a narrow mode the two can otherwise coincide by accident, which would
    make this pass without carrying any chroma.
    """
    desc = _color_desc(
        Klass.LabColor.value,
        {Key.Luminance: lab[0], Key.A: lab[1], Key.B: lab[2]},
    )
    flipped = _color_desc(
        Klass.LabColor.value,
        {Key.Luminance: lab[0], Key.A: -lab[1], Key.B: -lab[2]},
    )
    result = _get_color(color_mode, desc)
    assert all(0.0 <= c <= 1.0 for c in result), result
    assert result != _get_color(color_mode, flipped)


def test_lab_conversion_is_monotonic_in_lightness() -> None:
    """Darker L stays darker after the conversion.

    The CMYK direction reversed with #747. These arrays count what is *left*
    rather than what is laid down -- 1.0 is no ink -- so a darker colour has the
    *smaller* K entry. What is gone since #743 is the claim that the build is
    K-only: a neutral Lab colour converts through sRGB, and ``rgb_to_cmyk``
    puts a genuine neutral on K alone, but the moment there is any chroma the
    CMY entries carry it.
    """

    def lab_desc(lightness: float, a: float = 0.0, b: float = 0.0) -> Descriptor:
        return _color_desc(
            Klass.LabColor.value,
            {Key.Luminance: lightness, Key.A: a, Key.B: b},
        )

    dark = _get_color(ColorMode.GRAYSCALE, lab_desc(10.0))
    light = _get_color(ColorMode.GRAYSCALE, lab_desc(90.0))
    assert dark[0] < light[0]

    dark_cmyk = _get_color(ColorMode.CMYK, lab_desc(10.0))
    light_cmyk = _get_color(ColorMode.CMYK, lab_desc(90.0))
    assert dark_cmyk[3] < light_cmyk[3]
    # A neutral still builds on K alone. Approximate, not exact: the three rows
    # of the sRGB matrix do not sum identically, so a neutral comes back out of
    # lab_to_rgb with ~1e-8 between its channels, and rgb_to_cmyk divides that
    # by (1 - K) to get the CMY entries. The residue lands around 5e-8 -- a
    # hundred-thousandth of a code value, and not worth snapping for.
    assert dark_cmyk[:3] == pytest.approx((1.0, 1.0, 1.0), abs=1e-6)
    assert light_cmyk[:3] == pytest.approx((1.0, 1.0, 1.0), abs=1e-6)
    # ...and a chromatic one does not, which is the part #743 changed.
    assert _get_color(ColorMode.CMYK, lab_desc(50.0, 60.0, -40.0))[:3] != (
        1.0,
        1.0,
        1.0,
    )


@pytest.mark.parametrize(
    ("klass", "fields", "label"),
    [
        (Klass.Grayscale.value, {Key.Gray: 0.0}, "gray white"),
        (
            Klass.RGBColor.value,
            {Key.Red: 255, Key.Green: 255, Key.Blue: 255},
            "rgb white",
        ),
        (
            Klass.HSBColor.value,
            {Key.Hue: 0.0, Key.Saturation: 0.0, Key.Brightness: 100.0},
            "hsb white",
        ),
        (
            Klass.LabColor.value,
            {Key.Luminance: 255.0, Key.A: 0.0, Key.B: 0.0},
            "lab white",
        ),
    ],
)
def test_white_fill_is_white_on_a_cmyk_document(
    klass: bytes, fields: dict, label: str
) -> None:
    """A white fill composited black on every CMYK document (#747).

    ``color_convert``'s CMYK helpers are ink-space by contract -- white is
    ``(0, 0, 0, 0)``, no ink -- and the three conversions into CMYK handed that
    to a canvas that means the opposite by it. Rendered, the fill came out
    ``(0, 0, 0)``: solid black where Photoshop shows white.

    Pinned through the real PIL exit rather than on the tuple, because the
    inversion is only wrong relative to what ``post_process()`` does with it.
    """
    fill, _ = draw_solid_color_fill(
        (0, 0, 4, 4), ColorMode.CMYK, _color_desc(klass, fields)
    )
    assert fill is not None
    image = Image.fromarray((255 * fill).astype(np.uint8), "CMYK")
    rendered = post_process(image, None, None).convert("RGB")
    assert rendered.getpixel((0, 0)) == (255, 255, 255)


def test_cmyk_fill_lightness_survives_the_round_trip() -> None:
    """The canvas and the PIL exit must agree on which way the axis runs.

    A monotonic check on its own would pass with the polarity reversed -- it
    did, before #747 -- so this pins the rendered greys themselves.
    """
    seen = []
    for gray in (0.0, 50.0, 100.0):
        fill, _ = draw_solid_color_fill(
            (0, 0, 4, 4),
            ColorMode.CMYK,
            _color_desc(Klass.Grayscale.value, {Key.Gray: gray}),
        )
        image = Image.fromarray((255 * fill).astype(np.uint8), "CMYK")
        pixel = post_process(image, None, None).convert("RGB").getpixel((0, 0))
        assert isinstance(pixel, tuple)
        seen.append(pixel[0])
    assert seen[0] == 255 and seen[2] == 0
    assert seen[0] > seen[1] > seen[2]


# ---------------------------------------------------------------------------
# Lab normalization (#743)
#
# The fixture is a LAB document authored in Photoshop 2026, one solid-colour
# fill layer per band, each carrying an ``LbCl`` descriptor at a known L/a/b and
# masked to its own 16x16 square. Its merged preview is therefore Photoshop's
# own answer to "what bytes does this descriptor mean", for fourteen colours
# that span both ends of each chroma axis.
# ---------------------------------------------------------------------------


def _lab_swatches(
    psd: PSDImage,
) -> list[tuple[tuple[float, float, float], tuple[int, int, int, int]]]:
    """Each band's ``LbCl`` descriptor paired with the bounds it covers."""
    swatches = []
    for layer in psd.descendants():
        desc = layer.tagged_blocks.get_data(Tag.SOLID_COLOR_SHEET_SETTING, None)
        if desc is None:
            continue  # the white Background pixel layer
        color = desc[Key.Color]
        lab = (
            float(color[Key.Luminance]),
            float(color[Key.A]),
            float(color[Key.B]),
        )
        swatches.append((lab, layer.bbox))
    assert len(swatches) == 14
    return swatches


def test_lab_descriptor_matches_photoshops_own_bytes() -> None:
    """``_get_color`` reproduces the plane Photoshop wrote for the descriptor.

    Dividing L, a and b all by 255 was a correct normalization of none of them:
    L runs 0..100, and a/b are signed and stored offset by 128, so a neutral
    ``a = 0`` was landing on byte 0 -- the extreme end of the axis -- rather
    than on 128. Measured against this fixture the old reading was out by up to
    155/255; the mapping below reproduces every one of the fourteen swatches to
    within 1/255.

    That residue is Photoshop's, not ours: its own slope is 254/255, putting
    ``a = 127`` on byte 254 where the offset encoding PIL mode "LAB" documents
    puts it on 255. Copying that would buy under half a code value here and
    cost the same against any ImageCms decode, so the tolerance carries it
    instead.
    """
    psd = PSDImage.open(full_name("descriptors/lab-color-swatches.psd"))
    assert psd.color_mode == ColorMode.LAB
    # Untagged -- the document carries ICC_UNTAGGED_PROFILE and no ICC_PROFILE --
    # so the preview is Photoshop's raw Lab planes, with no colour management
    # standing between the descriptor and the bytes compared here.
    preview = psd.numpy()
    for lab, bbox in _lab_swatches(psd):
        left, top, right, bottom = bbox
        photoshop = preview[(top + bottom) // 2, (left + right) // 2] * 255.0
        ours = (
            np.array(
                _get_color(
                    ColorMode.LAB,
                    _color_desc(
                        Klass.LabColor.value,
                        {Key.Luminance: lab[0], Key.A: lab[1], Key.B: lab[2]},
                    ),
                )
            )
            * 255.0
        )
        assert np.abs(photoshop - ours).max() <= 1.0 + 1e-6, (lab, photoshop, ours)


def test_lab_fills_composite_to_photoshops_preview() -> None:
    """End to end, through the fills the descriptors drive.

    The unit assertion above pins the tuple; this pins what actually gets
    painted, so a correct conversion that never reaches the canvas cannot pass.
    Reverting the normalization takes the worst pixel from 1/255 to 155/255.
    """
    psd = PSDImage.open(full_name("descriptors/lab-color-swatches.psd"))
    reference = psd.numpy()
    rendered = composite(psd, force=True)[0]
    assert rendered.shape == reference.shape
    assert np.abs(reference - rendered).max() * 255.0 <= 2.0


@pytest.mark.parametrize(
    ("field", "value"), [(Key.Luminance, 140.0), (Key.A, 200.0), (Key.B, -200.0)]
)
def test_lab_out_of_range_clamps_rather_than_wrapping(field: Key, value: float) -> None:
    """A Lab target must not turn an out-of-range component into another colour.

    Lab's range is a convention rather than something the descriptor enforces,
    and it is the only colour class whose normalization can leave [0, 1]:
    ``a = 200`` gives 1.29. ``composite_pil()`` casts with
    ``(255 * color).astype(np.uint8)``, and numpy *wraps* out-of-range floats
    rather than saturating, so 1.29 arrives as byte 71 -- not a clipped chroma
    but a different colour entirely. The pre-#743 ``/255`` reading could not
    reach this on a Lab document, so the clamp arrives with the normalization
    that can.
    """
    axes = [Key.Luminance, Key.A, Key.B]
    fields: dict[Key, float] = {Key.Luminance: 50.0, Key.A: 0.0, Key.B: 0.0}
    fields[field] = value
    result = _get_color(ColorMode.LAB, _color_desc(Klass.LabColor.value, fields))
    assert all(0.0 <= c <= 1.0 for c in result), result
    assert result[axes.index(field)] == (1.0 if value > 0 else 0.0)
    pixels = (255 * np.array(result, dtype=np.float32)).astype(np.uint8)
    assert pixels[axes.index(field)] == (255 if value > 0 else 0)


# ---------------------------------------------------------------------------
# Cross-mode Lab conversion (#743 second half, #752)
#
# Photoshop rewrites a fill descriptor into the document's own colour class on
# save, so neither direction below is authorable from Photoshop and no fixture
# can carry them -- a scan of every file under tests/psd_files finds no LAB
# document with a non-Lab descriptor and no non-LAB document with a Lab one.
# The ground truth is therefore Photoshop's own colour engine over the
# scripting bridge, with the chroma reporting encoding undone; see
# tests/psd_tools/test_color_convert.py for the model.
# ---------------------------------------------------------------------------


def _native(reported: float) -> float:
    return (reported + 0.5) * 256.0 / 255.0


@pytest.mark.parametrize("color_mode", [ColorMode.RGB, ColorMode.INDEXED])
@pytest.mark.parametrize(
    ("lab", "photoshop_rgb"),
    [
        ((65.49, 13.0, 69.0), (202.690, 148.651, 0.0)),
        ((75.0, 25.0, -30.0), (211.468, 168.986, 239.887)),
        ((25.0, -40.0, 15.0), (0.0, 72.513, 33.509)),
        ((90.0, 5.0, -5.0), (234.175, 223.039, 235.179)),
        ((50.0, 0.0, 0.0), (120.084, 118.613, 118.084)),
    ],
)
def test_lab_fill_on_an_rgb_document_matches_photoshop(
    color_mode: ColorMode,
    lab: tuple[float, float, float],
    photoshop_rgb: tuple[float, float, float],
) -> None:
    """#743's second half: a Lab descriptor on an RGB or indexed document.

    This used to be ``(L/255, a/255, b/255)`` -- signed chroma read as unsigned,
    and ``L = 100`` arriving at 0.39. A Lab green came out an unrelated colour.
    Indexed goes the same way: its arrays are three wide, so it fell through the
    same branch.
    """
    desc = _color_desc(
        Klass.LabColor.value,
        {
            Key.Luminance: lab[0],
            Key.A: _native(lab[1]),
            Key.B: _native(lab[2]),
        },
    )
    got = [255.0 * v for v in _get_color(color_mode, desc)]
    assert len(got) == 3
    for channel, (value, want) in enumerate(zip(got, photoshop_rgb)):
        assert abs(value - want) <= 1.0, (lab, channel, value, want)


@pytest.mark.parametrize(
    ("rgb", "photoshop_lab"),
    [
        ((255, 0, 0), (54.2908, 79.9968, 69.1176)),
        ((0, 255, 0), (87.8204, -79.4638, 80.1758)),
        ((202, 149, 1), (65.5060, 12.5582, 68.3083)),
        ((120, 200, 255), (77.0691, -14.5231, -35.5812)),
        ((128, 128, 128), (53.5828, -0.5, -0.5)),
    ],
)
def test_rgb_fill_on_a_lab_document_matches_photoshop(
    rgb: tuple[int, int, int], photoshop_lab: tuple[float, float, float]
) -> None:
    """#752: an RGB descriptor on a Lab document.

    ``_from_rgb()`` had no Lab branch, so the triple fell through unconverted.
    Three channels is a legal width for a Lab document, so nothing complained --
    red simply arrived as ``(1.0, 0.0, 0.0)``, which those arrays read as white
    at the extreme green-blue corner.

    Compared in canvas encoding rather than native units, because that is what
    the compositor consumes; 1/255 here is one code value of the rendered
    pixel.
    """
    desc = _color_desc(
        Klass.RGBColor.value,
        {Key.Red: float(rgb[0]), Key.Green: float(rgb[1]), Key.Blue: float(rgb[2])},
    )
    got = _get_color(ColorMode.LAB, desc)
    want = (
        photoshop_lab[0] / 100.0,
        (_native(photoshop_lab[1]) + 128.0) / 255.0,
        (_native(photoshop_lab[2]) + 128.0) / 255.0,
    )
    assert len(got) == 3
    for channel, (value, expected) in enumerate(zip(got, want)):
        assert abs(value - expected) * 255.0 <= 1.0, (rgb, channel, value, expected)


@pytest.mark.parametrize(
    ("klass", "fields", "expected"),
    [
        # A grey, so a and b must land exactly on the neutral axis and L on the
        # grey's L* rather than on the grey itself. 0.6 -> 0.632 is the number
        # widen._lab()'s docstring quotes for the divergence it keeps.
        (
            Klass.Grayscale.value,
            {Key.Gray: 40.0},
            (0.632226, 128 / 255, 128 / 255),
        ),
        (
            Klass.CMYKColor.value,
            {Key.Cyan: 10.0, Key.Magenta: 20.0, Key.Yellow: 30.0, Key.Black: 40.0},
            (0.060154, 0.495916, 0.468762),
        ),
    ],
)
def test_other_classes_on_a_lab_document_go_through_the_conversion(
    klass: bytes, fields: dict, expected: tuple[float, float, float]
) -> None:
    """The grayscale and CMYK classes reach the Lab branch too (#752).

    Pinned as values rather than as agreement with the equivalent RGB
    descriptor. That equivalence is how the code is built -- both spellings end
    in ``_from_rgb(LAB, ...)`` -- so asserting it cannot fail, and an earlier
    draft of this test proved it: deleting either branch left the equivalence
    assertion passing.

    Not compared against Photoshop's own Lab for these two, either. Its
    grayscale working space is Dot Gain 20% and its CMYK separation is
    profile-driven, neither of which is what ``gray_to_rgb`` and ``cmyk_to_rgb``
    do, so a disagreement would be Photoshop's colour management rather than
    this conversion. The RGB class carries the Photoshop-anchored assertion,
    above.

    Grayscale is the one that needed a branch of its own: one channel is a legal
    width, so a grey fill used to reach the canvas as a bare lightness and get
    widened with a neutral a/b. Right axis, wrong height.
    """
    got = _get_color(ColorMode.LAB, _color_desc(klass, fields))
    assert got == pytest.approx(expected, abs=1e-6)
