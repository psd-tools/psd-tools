"""Widening a single-channel canvas to a document's channel count (#722).

``_widen()`` replicated the value across every channel. That is right for RGB
and wrong for CMYK, where a grey is a profile-dependent CMY build rather than
``(g, g, g, g)``, and wrong for Lab, where a lightness copied into a/b is not
neutral.

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

from psd_tools.api.pil_io import post_process
from psd_tools.api.psd_image import PSDImage
from psd_tools.composite import composite
from psd_tools.composite.composite import (
    _OVERLAY_DRAWS,
    Compositor,
    _draw_pattern_overlay,
    _widen,
)
from psd_tools.composite import widen as widen_module
from psd_tools.composite.widen import make_widen
from psd_tools.constants import ColorMode, Resource

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


def test_every_sub_compositor_inherits_the_conversion(monkeypatch) -> None:
    """A sub-compositor that forgets ``widen`` reverts its subtree to replication.

    ``_get_group()`` did exactly that, and because the group compositor is the
    parent of the clip and stroke ones, losing it there took the whole subtree
    with it -- the three sites that do pass it on were only right at the
    document's top level. No fixture caught it: no CMYK or Lab fixture has
    groups, so the corpus renders identically either way.

    Pinned on the identity of the callable rather than on any rendered value,
    so a new ``Compositor(...)`` that omits the argument fails here regardless
    of which document it is exercised with.
    """
    seen: list[bool] = []
    original = Compositor.__init__

    def spy(self, *args, **kwargs):
        original(self, *args, **kwargs)
        seen.append(self._widen is _widen)

    monkeypatch.setattr(Compositor, "__init__", spy)

    psd = PSDImage.open(full_name("clipping-mask.psd"))
    composite(psd, force=True)

    assert seen, "no compositor was constructed"
    assert not any(seen), "%d of %d compositors fell back to the mode-blind _widen" % (
        sum(seen),
        len(seen),
    )


def test_pattern_overlay_reuses_the_threaded_conversion(monkeypatch) -> None:
    """The overlay must take the compositor's widening, not build its own.

    It did build its own, which was correct but wasteful: ``make_widen()``
    digests the document's ICC profile, ~180 us for a press profile, so a fresh
    closure per overlay effect paid that again each time. It also meant one path
    resolved the conversion outside the tree the rest of this change threads it
    through, which is the kind of divergence that goes stale.

    Counting ``make_widen`` calls rather than inspecting the argument the draw
    function receives: it receives the threaded callable either way, so a spy on
    the parameter cannot tell whether the body used it or quietly built its own.
    What is observable is how many times the document gets resolved -- once per
    ``composite()``, however many overlays are drawn.
    """
    drawn: list[int] = []

    def counting_draw(layer, value, channels, widen):
        drawn.append(1)
        return _draw_pattern_overlay(layer, value, channels, widen)

    monkeypatch.setitem(_OVERLAY_DRAWS, "patternoverlay", counting_draw)

    resolved: list[int] = []
    original = widen_module.make_widen

    def counting_make_widen(psd):
        resolved.append(1)
        return original(psd)

    # sys.modules, not the dotted string: psd_tools.composite re-exports the
    # composite() *function* under the module's own name, so attribute lookup
    # on the dotted path lands on the function instead of the module.
    monkeypatch.setattr(
        sys.modules["psd_tools.composite.composite"],
        "make_widen",
        counting_make_widen,
    )

    psd = PSDImage.open(full_name("layer_effects.psd"))
    composite(psd, force=True)

    assert drawn, "no pattern overlay was drawn"
    assert len(resolved) == 1, (
        "the document was resolved %d times for %d pattern overlays; it should "
        "be resolved once per composite() and threaded" % (len(resolved), len(drawn))
    )
