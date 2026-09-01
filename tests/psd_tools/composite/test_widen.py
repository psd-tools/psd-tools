"""Widening a single-channel canvas to a document's channel count (#722).

``_widen()`` replicated the value across every channel. That is right for RGB
and wrong for CMYK, where a grey is a profile-dependent CMY build rather than
``(g, g, g, g)``, and wrong for Lab, where a lightness copied into a/b is not
neutral.

The last section covers *sources* rather than backdrops (#749): a source may
arrive one channel wide, and being broadcast by the blend arithmetic was the
same replication reached by a different door.

``cmyk-gray-ramp.psd`` is the ground truth these tests are pinned against. It
was authored by scripting Photoshop 2026: a grayscale document filled with nine
8-bit grey patches, converted to CMYK with ``changeMode()`` and saved with its
profile embedded. Its pixels are therefore Photoshop's own answer to the
question this module exists to answer, and its embedded profile -- U.S. Web
Coated (SWOP) v2, Photoshop's default -- is what the transform is built from.

The file is 568 KB, almost all of it that profile. A compact Generic CMYK
profile would fit the 500 KB pre-commit limit but has coarser tables, and
littlecms and Photoshop diverge to 10/255 on it against 3.6/255 here -- so the
press profile is shipped and the hook skipped for it, in a repository whose
CMYK fixtures already run to 2.3 MB.
"""

import sys

import numpy as np
import pytest
from PIL import Image

from psd_tools.api.layers import Layer
from psd_tools.api.pil_io import post_process
from psd_tools.api.psd_image import PSDImage
from psd_tools.color_convert import LAB_NEUTRAL_CHROMA
from psd_tools.composite import composite
from psd_tools.composite.composite import Compositor, _widen
from psd_tools.composite import widen as widen_module
from psd_tools.composite.widen import make_widen
from psd_tools.constants import BlendMode, ColorMode, Resource, Tag
from psd_tools.psd.descriptor import Bool, Descriptor, String
from psd_tools.psd.patterns import (
    Pattern,
    Patterns,
    VirtualMemoryArray,
    VirtualMemoryArrayList,
)
from psd_tools.terminology import Enum, Key

from ..utils import full_name

# cmyk-gray-ramp.psd is nine 16x16 patches in a row, one per grey level.
GRAY_LEVELS = [0, 32, 64, 96, 128, 160, 192, 224, 255]
PATCH = 16


def _photoshop_ramp() -> tuple[PSDImage, np.ndarray]:
    psd = PSDImage.open(full_name("cmyk-gray-ramp.psd"))
    return psd, psd.numpy()


def _grey(value: float) -> np.ndarray:
    return np.full((1, 1, 1), value, dtype=np.float32)


def test_cmyk_widening_matches_photoshop() -> None:
    """The converted grey must be Photoshop's, not a formula's.

    Photoshop puts a mid grey at a heavy CMY build carrying almost no black --
    ``C.516 M.432 Y.432 K.075`` in ink at ``g = 0.5`` -- so neither replication
    nor the K-only formula the issue suggested is close. Replication is checked
    alongside so the tolerance below cannot be read as "everything passes": it
    is out by two orders of magnitude more.
    """
    psd, expected = _photoshop_ramp()
    widen = make_widen(psd)

    icc_error = 0.0
    replication_error = 0.0
    for index, level in enumerate(GRAY_LEVELS):
        # Photoshop dithers the mode conversion, so a patch varies by 1/255
        # within itself. Average it rather than trusting one pixel.
        patch = expected[:, index * PATCH : (index + 1) * PATCH]
        target = patch.reshape(-1, 4).mean(axis=0)
        grey = _grey(level / 255.0)
        icc_error = max(icc_error, float(np.abs(widen(grey, 4)[0, 0] - target).max()))
        replicated = np.repeat(grey, 4, axis=2)[0, 0]
        replication_error = max(
            replication_error, float(np.abs(replicated - target).max())
        )

    # Locally the worst patch mean is 3.6/255; 6 leaves room for littlecms
    # version differences across CI platforms. Replication's 107/255 is what
    # keeps that from reading as "anything passes" -- the tolerance sits an
    # order of magnitude below the error it exists to reject.
    assert icc_error * 255 < 6.0
    assert replication_error * 255 > 100.0


def test_cmyk_widening_follows_the_document_profile() -> None:
    """A different CMYK space must give a different answer.

    Pins that the profile is actually read rather than a fixed table being
    applied: the ramp fixture embeds U.S. Web Coated (SWOP) v2 and
    ``4x4_8bit_cmyk.psd`` embeds Japan Color 2001 Coated.
    """
    swop = make_widen(PSDImage.open(full_name("cmyk-gray-ramp.psd")))
    japan = make_widen(PSDImage.open(full_name("colormodes/4x4_8bit_cmyk.psd")))

    grey = _grey(0.75)
    a, b = swop(grey, 4)[0, 0], japan(grey, 4)[0, 0]
    assert not np.allclose(a, b, atol=1 / 255)
    # Both are still recognisably a light grey rather than arbitrary values.
    assert (a > 0.6).all() and (b > 0.6).all()


@pytest.mark.parametrize(
    "filename", ["blend-modes/cmyk-blend-modes.psd", "cmyk-spot.psd"]
)
def test_cmyk_widening_falls_back_without_a_profile(filename: str) -> None:
    """No embedded profile leaves nothing to transform through.

    The fallback is the K-only formula, in canvas space -- the same conversion
    ``paint._get_gray()`` applies to a grey *fill* on the same document (#747).
    Agreeing with the fill path matters more here than being closer to
    Photoshop, which without a profile is not on offer either way.
    """
    psd = PSDImage.open(full_name(filename))
    assert psd.color_mode == ColorMode.CMYK
    widened = make_widen(psd)(_grey(0.25), 4)[0, 0]
    assert np.allclose(widened, (1.0, 1.0, 1.0, 0.25))


def test_lab_widening_is_neutral() -> None:
    """A grey sits on Lab's neutral axis; a and b are offset-encoded.

    Replicating the lightness put a and b at the extreme end of their axes.
    Photoshop reports ``a = b = 0`` for every grey, which the arrays store
    offset by 128 -- so neutral is ``128 / 255``, not the 0.5 this said before
    #743. The half-step matters because ``composite_pil()`` truncates: 0.5
    leaves byte 127 where Photoshop writes 128.
    """
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_lab.psd"))
    assert psd.color_mode == ColorMode.LAB
    widened = make_widen(psd)(_grey(0.75), 3)[0, 0]
    assert np.allclose(widened, (0.75, 128 / 255, 128 / 255))
    assert np.uint8(255 * widened[1]) == 128


@pytest.mark.parametrize(
    ("filename", "channels"),
    [
        ("colormodes/4x4_8bit_rgb.psd", 3),
        ("colormodes/4x4_16bit_multichannel.psd", 3),
    ],
)
def test_widening_still_replicates_where_that_is_right(
    filename: str, channels: int
) -> None:
    """RGB is correct by replication and must not move.

    Multichannel replicates too, for a different reason: its planes are spot
    inks with no colorimetric reading to convert into, so replication is the
    only monotonic option rather than a correct one.
    """
    psd = PSDImage.open(full_name(filename))
    widened = make_widen(psd)(_grey(0.75), channels)[0, 0]
    assert np.allclose(widened, np.full(channels, 0.75))


def test_widening_without_a_document_replicates() -> None:
    """A detached layer has no document to ask, so the old behaviour stands."""
    assert np.allclose(make_widen(None)(_grey(0.75), 4)[0, 0], np.full(4, 0.75))


def test_single_channel_backdrop_reaches_the_conversion() -> None:
    """The end-to-end path the issue reproduces.

    A one-channel backdrop handed to a CMYK document used to come back
    ``[0.75, 0.75, 0.75, 0.75]`` -- the replication, an over-inked colour that
    is not the grey it came from.
    """
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_cmyk.psd"))
    backdrop = np.full((psd.height, psd.width, 1), 0.75, dtype=np.float32)
    color, _, _ = composite(
        psd, color=backdrop, alpha=1.0, layer_filter=lambda layer: False
    )
    assert not np.allclose(color[0, 0], np.full(4, 0.75), atol=2 / 255)
    assert np.allclose(color[0, 0], make_widen(psd)(_grey(0.75), 4)[0, 0])


def test_widened_grey_survives_the_icc_round_trip() -> None:
    """Entering through the profile the exit leaves through is the point.

    ``pil_io._apply_icc()`` converts the composite to sRGB through the same
    embedded profile, so a grey widened this way comes back out as the grey it
    started as. Neither replication nor a formula has that property -- it is the
    strongest argument for doing this through ICC at all.
    """
    psd = PSDImage.open(full_name("cmyk-gray-ramp.psd"))
    widen = make_widen(psd)
    icc = psd.image_resources.get_data(Resource.ICC_PROFILE)
    for level in (64, 128, 192):
        canvas = np.tile(widen(_grey(level / 255.0), 4), (2, 2, 1))
        image = Image.fromarray((255 * canvas).round().astype(np.uint8), "CMYK")
        rendered = post_process(image, None, icc).convert("RGB").getpixel((0, 0))
        assert isinstance(rendered, tuple)
        # Out of gamut at the black end only; these three are well inside it.
        assert max(abs(c - level) for c in rendered) <= 3


# Every function that constructs a ``Compositor``, and so has to pass the
# document's facts on. Named rather than counted so that the fixtures below are
# checked to still reach each one: a guard that renders a document which no
# longer builds, say, a stroke sub-compositor keeps passing while covering
# nothing.
_WIDEN_CALLERS = frozenset(
    {"composite", "_get_group", "_get_object", "_apply_clip_layers"}
)

# Between them these reach all four. Neither does alone: the clipping fixture
# has no stroked shape, and the stroke fixture has no group.
_WIDEN_FIXTURES = ["clipping-mask.psd", "effects/stroke-composite.psd"]


def test_every_sub_compositor_inherits_the_document_facts(monkeypatch) -> None:
    """A sub-compositor that forgets ``widen`` reverts its subtree to replication.

    ``_get_group()`` did exactly that, and because the group compositor is the
    parent of the clip and stroke ones, losing it there took the whole subtree
    with it -- the sites that did pass it on were only right at the document's
    top level. No fixture caught it: no CMYK or Lab fixture has groups, so the
    corpus renders identically either way. Nor would one: in RGB replication
    *is* the conversion, so a lost ``widen`` is invisible in every document the
    corpus actually contains.

    Which makes what the spy is pointed at the whole substance of the test, and
    ``clipping-mask.psd`` alone was pointing it away from one site. It builds a
    top-level, two group and one clip compositor, and no stroke one -- so the
    ``Compositor(...)`` in ``_get_object()`` that seeds a stroke was covered by
    nothing, though losing ``widen`` there reverts every stroked shape in a CMYK
    or Lab document (#749, #776). ``effects/stroke-composite.psd`` builds eight
    of them.

    ``color_mode`` is checked in the same pass, being the second fact carried
    down the same tree for the same reason: a compositor that does not know its
    document's colour mode blends the non-separable modes by the width of the
    array alone, which is what read a multichannel document's fourth spot plate
    as black generation (#746). One spy rather than two, so that the two facts
    cannot drift apart -- the failure mode here is a *new* construction site
    passing one argument and forgetting the other.

    Pinned on the identity of the callable rather than on any rendered value,
    so a new ``Compositor(...)`` that omits the argument fails here regardless
    of which document it is exercised with -- and on the caller's name, so a
    site that stops being reached fails here too rather than going quiet.
    """
    seen: list[tuple[str, bool, bool]] = []
    original = Compositor.__init__

    def spy(self, *args, **kwargs):
        original(self, *args, **kwargs)
        # Frame 1 is whatever called ``Compositor(...)``: the constructor is
        # reached through ``type.__call__``, which adds no Python frame.
        seen.append(
            (
                sys._getframe(1).f_code.co_name,
                self._widen is _widen,
                self._color_mode is None,
            )
        )

    monkeypatch.setattr(Compositor, "__init__", spy)

    for filename in _WIDEN_FIXTURES:
        composite(PSDImage.open(full_name(filename)), force=True)

    fell_back = [caller for caller, is_default, _ in seen if is_default]
    assert not fell_back, (
        "%d of %d compositors fell back to the mode-blind "
        "_widen, from %s" % (len(fell_back), len(seen), sorted(set(fell_back)))
    )

    modeless = [caller for caller, _, no_mode in seen if no_mode]
    assert not modeless, "%d of %d compositors were given no colour mode, from %s" % (
        len(modeless),
        len(seen),
        sorted(set(modeless)),
    )

    missing = _WIDEN_CALLERS - {caller for caller, _, _ in seen}
    assert not missing, (
        "%s built no compositor for these fixtures, so nothing checks that it "
        "passes the document's facts on" % sorted(missing)
    )


def test_the_conversion_is_resolved_once_per_composite(monkeypatch) -> None:
    """Resolving the document is threaded, not repeated per compositor.

    ``make_widen()`` digests the document's ICC profile -- ~180 us for a press
    profile -- so resolving it per sub-compositor or per effect would pay that
    again each time. Three comments assert this in prose; nothing else asserts
    it in code.

    ``test_every_sub_compositor_inherits_the_document_facts`` above does not cover
    it: that spy compares each compositor's ``_widen`` against the mode-blind
    fallback, so a site building a fresh ``make_widen(psd)`` of its own would
    satisfy it. The compositor count is asserted here for the same reason --
    "resolved once" says nothing on a document that builds one compositor.

    This was the surviving half of ``test_pattern_overlay_reuses_the_threaded_
    conversion``, whose other half -- that the pattern overlay takes the
    threaded callable rather than building its own -- went away with the
    widening it guarded (#777).
    """
    resolved: list[int] = []
    original_make_widen = widen_module.make_widen

    def counting_make_widen(psd):
        resolved.append(1)
        return original_make_widen(psd)

    # sys.modules, not the dotted string: psd_tools.composite re-exports the
    # composite() *function* under the module's own name, so attribute lookup
    # on the dotted path lands on the function instead of the module.
    monkeypatch.setattr(
        sys.modules["psd_tools.composite.composite"],
        "make_widen",
        counting_make_widen,
    )

    built: list[int] = []
    original_init = Compositor.__init__

    def counting_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        built.append(1)

    monkeypatch.setattr(Compositor, "__init__", counting_init)

    composite(PSDImage.open(full_name("clipping-mask.psd")), force=True)

    assert len(built) > 1, "the fixture built no sub-compositor to thread into"
    assert len(resolved) == 1, (
        "the document was resolved %d times for %d compositors; it should be "
        "resolved once per composite() and threaded" % (len(resolved), len(built))
    )


def test_scalar_backdrop_reaches_the_conversion_on_a_lab_document() -> None:
    """The default backdrop, which is where #753 actually bites.

    ``composite()`` defaults to ``color=1.0``, so this is what a Lab document
    composites against wherever nothing covers it. Broadcasting that scalar put
    both chroma axes at 1.0 -- byte 255, the extreme corner of each -- so the
    default backdrop was maximum chroma at maximum lightness rather than white,
    which on a Lab canvas is ``(255, 128, 128)``.

    The viewport is wider than the layer so that bare backdrop is exposed;
    without that the layer covers every pixel and the backdrop never shows.
    """
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_lab.psd"))
    color, _, _ = composite(psd[0], viewport=(0, 0, 8, 8), force=True)
    bare = color[7, 7]
    assert bare[0] == pytest.approx(1.0)
    assert bare[1] == pytest.approx(128 / 255, abs=1e-6)
    assert bare[2] == pytest.approx(128 / 255, abs=1e-6)


@pytest.mark.parametrize(
    "filename",
    ["colormodes/4x4_8bit_lab.psd", "colormodes/4x4_8bit_cmyk.psd"],
)
@pytest.mark.parametrize("value", [0.0, 0.25, 1.0])
def test_scalar_and_single_channel_backdrops_agree(filename: str, value: float) -> None:
    """The same backdrop, spelled two ways, end to end.

    This is the defect underneath #753 rather than one mode's symptom: the
    array spelling went through the conversion #722 added and the scalar did
    not, so which answer a caller got depended on how they happened to write
    it. Lab is where that produced a colour off the neutral axis entirely;
    CMYK is where it produced the over-inked build this module exists to avoid
    -- ``0.0`` broadcast to ``(0, 0, 0, 0)``, which is every plate at 100%.
    """
    psd = PSDImage.open(full_name(filename))
    canvas = np.full((psd.height, psd.width, 1), value, dtype=np.float32)
    scalar_color, _, _ = composite(
        psd, color=value, alpha=1.0, layer_filter=lambda layer: False
    )
    canvas_color, _, _ = composite(
        psd, color=canvas, alpha=1.0, layer_filter=lambda layer: False
    )
    assert np.array_equal(scalar_color, canvas_color)


# --- Sources, not only backdrops ---------------------------------------------
#
# A *source* is allowed to arrive one channel wide -- ``_assert_source_fits()``
# says so -- and the blend arithmetic used to broadcast it, which is the
# replication above reached by another door. So one grey got two answers on one
# document depending on incidental layer structure: converted as a backdrop, as
# a clip base, as the base colour under a stroke or as a pattern overlay,
# replicated as a plain fill layer -- or as a stroke's own fill (#749).

# The forged pattern's identifier, arbitrary but shared by the record and the
# descriptor that names it -- ``_get_pattern()`` matches them exactly.
FORGED_PATTERN_ID = "4c1b6c4e-7a2f-4d5b-9b3a-000000000749"


def _gray_pattern(level: int, size: tuple[int, int] = (4, 4)) -> Pattern:
    """A flat grayscale pattern, laid out the way Photoshop lays out its own.

    26 channel slots, of which only the first is written: that is what all of
    the grayscale patterns Photoshop 2026 ships carry, and what
    ``get_pattern_color_channels()`` reads the colour/alpha boundary off.
    """
    height, width = size
    plane = VirtualMemoryArray()
    plane.set_data((width, height), bytes([level]) * (width * height), 8)
    channels = [plane] + [VirtualMemoryArray() for _ in range(25)]
    return Pattern(
        image_mode=ColorMode.GRAYSCALE,
        point=(height, width),
        name="Forged Gray\x00",
        pattern_id=FORGED_PATTERN_ID,
        data=VirtualMemoryArrayList(rectangle=(0, 0, height, width), channels=channels),
    )


def _pattern_fill_desc() -> Descriptor:
    """The descriptor a pattern fill layer and a pattern overlay both carry."""
    pattern = Descriptor(classID=b"Ptrn")
    pattern[Key.ID] = String(FORGED_PATTERN_ID + "\x00")
    pattern[Key.Name] = String("Forged Gray\x00")
    desc = Descriptor(classID=b"patternFill")
    desc[Enum.Pattern] = pattern
    return desc


def _gray_pattern_fill(
    filename: str = "colormodes/4x4_8bit_cmyk.psd", level: int = 128
) -> tuple[PSDImage, Layer]:
    """A document whose only fill is a *grayscale* pattern.

    Photoshop does not author this: it converts a pattern to the document's
    colour mode when embedding it, so a pattern applied in a CMYK document is
    stored ``image_mode=ColorMode.CMYK`` -- verified by scripting Photoshop
    2026. The mismatch is reachable from files other tools write, and by
    building the layer through psd-tools, so the pattern is forged into a
    document that is otherwise Photoshop's own, embedded profile included.
    *filename* picks that document, and with it the mode being converted into.

    The gradient block is removed so the fixture cannot rest on
    ``create_fill()`` happening to check the pattern block first. The layer
    object stays a ``GradientFill`` either way; nothing here reads its kind.
    """
    psd = PSDImage.open(full_name(filename))
    # The grey has to have somewhere to widen into, or nothing here is tested.
    assert psd.channels > 1
    blocks = psd.tagged_blocks
    assert blocks is not None
    # Same ignore as ``Patterns.read()``'s own: ``ListElement`` carries an
    # unbound item type, so every construction of one is untypeable here.
    blocks.set_data(Tag.PATTERNS1, Patterns([_gray_pattern(level)]))  # type: ignore[list-item]
    layer = psd[1]
    del layer.tagged_blocks[Tag.GRADIENT_FILL_SETTING]
    layer.tagged_blocks.set_data(Tag.PATTERN_FILL_SETTING, _pattern_fill_desc())
    return psd, layer


def _with_pattern_overlay(layer: Layer) -> Layer:
    """Give *layer* a pattern overlay effect naming that same forged pattern.

    Photoshop files an overlay's descriptor under ``patternOverlay`` with the
    class ID ``patternFill`` -- the class the fill layer's own block holds, and
    the one ``draw_pattern_fill()`` reads -- so both paths below get what
    ``_pattern_fill_desc()`` builds, and differ only by the two flags an
    effects block needs to be read at all.

    Call this before anything reads ``layer.effects``: that property caches on
    first access, so a block set afterwards is never seen.
    """
    overlay = _pattern_fill_desc()
    overlay[Key.Enabled] = Bool(True)
    overlay[b"present"] = Bool(True)
    effects = Descriptor(classID=b"null")
    effects[b"masterFXSwitch"] = Bool(True)
    effects[b"patternOverlay"] = overlay
    layer.tagged_blocks.set_data(Tag.OBJECT_BASED_EFFECTS_LAYER_INFO, effects)
    return layer


@pytest.mark.parametrize("render", ["layer", "document"])
def test_gray_pattern_fill_reaches_the_conversion(render: str) -> None:
    """The end-to-end path the issue reports, as the fill layer it names.

    Rendered ``[0.502] * 4`` -- the grey in every plate, an over-inked build
    that is not the grey it came from -- where the same grey as a backdrop, and
    the same pattern as an *overlay effect* on the same document, had converted
    since #722.
    """
    psd, layer = _gray_pattern_fill(level=128)
    target = (
        composite(layer, force=True)
        if render == "layer"
        else composite(psd, force=True, layer_filter=lambda other: other is layer)
    )
    color = target[0]

    assert color.shape == (psd.height, psd.width, 4)
    assert np.allclose(color, make_widen(psd)(_grey(128 / 255.0), 4))
    assert not np.allclose(color, 128 / 255.0, atol=2 / 255)


def test_gray_pattern_agrees_between_the_fill_and_the_overlay() -> None:
    """The first two rows of the issue's table, on one document.

    A pattern fill layer and a pattern overlay effect carry the same
    descriptor and name the same pattern, so the colour they paint cannot
    depend on which of the two a person reached for. It did: the overlay
    widened through ``make_widen`` and the fill was broadcast.

    Driven through ``_apply_overlay`` rather than through
    ``_draw_pattern_overlay``, because since #777 the draw function no longer
    converts anything -- it hands back the pattern at its own width and
    ``_fit_source()`` widens it, like every other source. Comparing the raw
    return would now compare two one-channel arrays and pass however the
    conversion was wired. Comparing a composited overlay against a composited
    fill is only sound because the fill is opaque over the whole viewport: it
    is the pattern colour and nothing of the backdrop.
    """
    psd, layer = _gray_pattern_fill(level=128)
    _with_pattern_overlay(layer)

    # A second, independent copy of the same document for the fill: attaching
    # the effect to one layer and compositing it would apply the overlay to the
    # very render it is being compared against.
    _, fill_layer = _gray_pattern_fill(level=128)
    fill = composite(fill_layer, force=True)[0]

    ones = np.ones((psd.height, psd.width, 1), dtype=np.float32)
    compositor = Compositor(
        psd.viewbox,
        np.zeros((psd.height, psd.width, 4), dtype=np.float32),
        np.zeros((psd.height, psd.width, 1), dtype=np.float32),
        widen=make_widen(psd),
    )
    compositor._apply_overlay(layer, "patternoverlay", ones, ones)
    overlay = compositor.finish()[0]

    assert overlay.shape == (psd.height, psd.width, 4)
    assert np.allclose(fill, overlay)
    assert not np.allclose(overlay, 128 / 255.0, atol=2 / 255)


def test_pattern_overlay_pads_with_white_rather_than_replicated_ones() -> None:
    """Where the overlay's widening moved to is observable, and it is better.

    Dropping the draw function's own widening (#777) moves the conversion from
    before ``paste()`` to after it, and ``paste()`` fills outside the layer's
    bbox with 1.0 -- white in the pattern's own one-channel encoding. Converted
    before, that padding stayed 1.0 in a single channel and the blend
    arithmetic broadcast it to ``(1, 1, 1)``, which on a Lab canvas is not
    white but L=100 with both chroma axes pinned to +127. Converted after, it
    widens like any other grey, to ``(1, 128/255, 128/255)``: white.

    Reaching those pixels takes coverage outliving the layer's bbox, which
    ``_get_object()`` hands back for a layer carrying no transparency channel.
    Measured over every fixture in both force modes, no corpus document pairs
    one with a pattern overlay, so the coverage is passed in directly here.
    (Separately, and for a simpler reason, the corpus renders bitwise
    identically either way: no pattern overlay in it is one channel wide at
    all.) Lab is the mode that shows it: on CMYK white widens to
    ``(1, 1, 1, 1)`` either way.
    """
    # Not 128: on Lab that widens to (0.502, 0.502, 0.502), which is exactly
    # what replication gives, so the content assertion below could not tell the
    # conversion from the bug. 200 widens to (0.784, 0.502, 0.502).
    psd, layer = _gray_pattern_fill("colormodes/4x4_8bit_lab.psd", level=200)
    assert psd.color_mode == ColorMode.LAB
    _with_pattern_overlay(layer)

    # A viewport two pixels larger on every side than the layer, so the ring
    # around it is the padding and nothing else.
    pad = 2
    height, width = psd.height + 2 * pad, psd.width + 2 * pad
    ones = np.ones((height, width, 1), dtype=np.float32)
    compositor = Compositor(
        (-pad, -pad, psd.width + pad, psd.height + pad),
        np.zeros((height, width, 3), dtype=np.float32),
        np.zeros((height, width, 1), dtype=np.float32),
        widen=make_widen(psd),
    )
    compositor._apply_overlay(layer, "patternoverlay", ones, ones)
    result = compositor.finish()[0]

    assert np.allclose(result[0, 0], [1.0, LAB_NEUTRAL_CHROMA, LAB_NEUTRAL_CHROMA])
    assert not np.allclose(result[0, 0], 1.0)
    # And the pattern itself still converts, so this pins where the padding
    # ends rather than that the whole canvas turned neutral.
    assert np.allclose(result[pad, pad], make_widen(psd)(_grey(200 / 255.0), 3)[0, 0])
    assert not np.allclose(result[pad, pad], 200 / 255.0)


def test_single_channel_source_and_backdrop_agree() -> None:
    """The distinction the issue is named for, at the compositor itself.

    One grey, handed to the same CMYK document twice: once as the backdrop it
    composites against, once as a source composited onto it. A source is
    allowed to arrive narrow and a backdrop is not, but that is a statement
    about array widths -- it was never meant to be a statement about what
    colour a grey is.
    """
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_cmyk.psd"))
    widen = make_widen(psd)
    height, width = psd.height, psd.width
    grey = np.full((height, width, 1), 0.75, dtype=np.float32)
    ones = np.ones((height, width, 1), dtype=np.float32)

    compositor = Compositor(
        psd.viewbox,
        np.zeros((height, width, 4), dtype=np.float32),
        np.zeros((height, width, 1), dtype=np.float32),
        widen=widen,
    )
    compositor._apply_source(grey, ones, ones, BlendMode.NORMAL)
    as_source = compositor.finish()[0]

    as_backdrop, _, _ = composite(
        psd, color=grey, alpha=1.0, layer_filter=lambda layer: False
    )

    assert np.allclose(as_source, as_backdrop)
    assert np.allclose(as_source, widen(_grey(0.75), 4))
    assert not np.allclose(as_source, 0.75, atol=2 / 255)
