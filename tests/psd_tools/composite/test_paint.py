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
        (0.0, -128.0, -128.0),
        (100.0, 127.0, 127.0),
        (20.0, -90.0, 60.0),
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
    ],
)
def test_lab_reduces_from_lightness_alone(
    lab: tuple[float, float, float], color_mode: ColorMode
) -> None:
    """A Lab descriptor reduces via L, not by treating a/b as green and blue.

    ``a`` and ``b`` are signed chroma, so folding them into a grayscale or CMYK
    conversion as if they were RGB components gives an arbitrary result that can
    fall outside [0, 1] -- a negative fill component. Only ``L`` carries
    lightness, so the reduction takes it alone, which keeps the result in range
    and monotonic in lightness.
    """
    desc = _color_desc(
        Klass.LabColor.value,
        {Key.Luminance: lab[0], Key.A: lab[1], Key.B: lab[2]},
    )
    result = _get_color(color_mode, desc)
    assert all(0.0 <= c <= 1.0 for c in result), result
    # a and b do not move the result at all.
    swapped = _color_desc(
        Klass.LabColor.value,
        {Key.Luminance: lab[0], Key.A: -lab[1], Key.B: -lab[2]},
    )
    assert _get_color(color_mode, swapped) == result


def test_lab_reduction_is_monotonic_in_lightness() -> None:
    """Darker L stays darker after the reduction.

    The CMYK direction reversed with #747. These arrays count what is *left*
    rather than what is laid down -- 1.0 is no ink -- so a darker colour has the
    *smaller* K entry, and the CMY entries of a K-only build are 1.0 rather than
    0.0. Before #747 the ink-space spelling went into the canvas unchanged, so
    the assertions below read the other way round and a white fill composited
    black.
    """

    def lab_desc(lightness: float) -> Descriptor:
        return _color_desc(
            Klass.LabColor.value,
            {Key.Luminance: lightness, Key.A: 0.0, Key.B: 0.0},
        )

    dark = _get_color(ColorMode.GRAYSCALE, lab_desc(10.0))
    light = _get_color(ColorMode.GRAYSCALE, lab_desc(90.0))
    assert dark[0] < light[0]

    # CMYK is K-only, so more lightness means less key ink -- a larger entry.
    dark_cmyk = _get_color(ColorMode.CMYK, lab_desc(10.0))
    light_cmyk = _get_color(ColorMode.CMYK, lab_desc(90.0))
    assert dark_cmyk[:3] == light_cmyk[:3] == (1.0, 1.0, 1.0)
    assert dark_cmyk[3] < light_cmyk[3]


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
        photoshop = preview[8, (bbox[0] + bbox[2]) // 2] * 255.0
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


@pytest.mark.parametrize("color_mode", [ColorMode.RGB, ColorMode.INDEXED])
@pytest.mark.parametrize("lab", [(50.0, -128.0, -100.0), (25.0, -40.0, 15.0)])
def test_lab_negative_chroma_clamps_on_an_rgb_target(
    color_mode: ColorMode, lab: tuple[float, float, float]
) -> None:
    """Here the wrapping input is in range, not out of it.

    RGB and INDEXED still take the ``/255`` reading pending the second half of
    #743, and that divides *signed* chroma as if it were unsigned. Every
    negative ``a`` or ``b`` -- so every green and every blue -- came out
    negative and wrapped on the cast: Lab(25, -40, 15), an ordinary green, put
    ``a`` on byte 216, near the top of its axis rather than below the middle.
    The reading stays wrong until it is replaced; it should not also wrap.
    """
    desc = _color_desc(
        Klass.LabColor.value,
        {Key.Luminance: lab[0], Key.A: lab[1], Key.B: lab[2]},
    )
    result = _get_color(color_mode, desc)
    assert all(0.0 <= c <= 1.0 for c in result), result
    assert result[1] == 0.0  # negative a, clamped to the end of the axis
    pixels = (255 * np.array(result, dtype=np.float32)).astype(np.uint8)
    assert pixels[1] == 0
