import logging
from typing import Any, Optional, cast

import numpy as np
import pytest

from psd_tools.api.layers import AdjustmentLayer, GroupMixin, Layer, PixelLayer
from psd_tools.api.psd_image import PSDImage
from psd_tools.composite import composite
from psd_tools.composite.composite import Compositor
from psd_tools.constants import BlendMode, ColorMode, CompatibilityMode, Tag
from psd_tools.psd.base import ByteElement
from PIL import Image

from ..utils import full_name

logger = logging.getLogger(__name__)


def _mse(x: Any, y: Any) -> Any:
    return np.nanmean((x - y) ** 2)


def composite_error(
    layer: Any, threshold: float, force: bool = True, channel: Optional[str] = None
) -> Any:
    reference = layer.numpy(channel)
    color, _, alpha = composite(layer, force=force)
    result = color
    if reference.shape[2] > color.shape[2]:
        result = np.concatenate((color, alpha), axis=2)
    error = _mse(reference, result)
    assert error <= threshold
    return error


def check_composite_quality(
    filename: str, threshold: float = 0.1, force: bool = False
) -> None:
    psd = PSDImage.open(full_name(filename))
    composite_error(psd, threshold, force)


def check_icc_composite_quality(
    filename: str, threshold: float = 0.001, force: bool = False
) -> None:
    reference = (
        np.array(Image.open(full_name(filename + ".png")), dtype=np.float32) / 255.0
    )
    psd = PSDImage.open(full_name(filename + ".psd"))
    result = (
        np.array(
            psd.composite(
                apply_icc=True,
                layer_filter=lambda layer: layer.is_visible(),
                force=force,
            ),
            dtype=np.float32,
        )
        / 255.0
    )

    assert reference.shape == result.shape
    assert _mse(reference, result) <= threshold


@pytest.mark.parametrize(
    ("filename",),
    [
        ("background-red-opacity-80.psd",),
        ("32bit.psd",),
        ("clipping-mask2.psd",),
        ("clipping-mask.psd",),
        ("clipping-mask2.psd",),
        ("clipping-mask3.psd",),
        ("clipping-mask4.psd",),
        ("clipping-mask5.psd",),
        ("opacity-fill.psd",),
        ("transparency/transparency-group.psd",),
        ("transparency/knockout-isolated-groups.psd",),
        ("transparency/knockout-none-normal.psd",),
        ("transparency/knockout-none-passthrough.psd",),
        ("transparency/knockout-none-nested.psd",),
        ("transparency/knockout-none-cyanbg.psd",),
        ("transparency/knockout-shallow-nested.psd",),
        ("transparency/knockout-shallow-nested-pt.psd",),
        ("transparency/knockout-deep-normal.psd",),
        ("transparency/knockout-deep-passthrough.psd",),
        ("transparency/knockout-deep-nested.psd",),
        ("transparency/knockout-deep-nested-pt.psd",),
        ("transparency/knockout-deep-cyanbg.psd",),
        ("transparency/knockout-deep-nobg.psd",),
        ("transparency/clip-opacity.psd",),
        ("transparency/fill-opacity.psd",),
        ("mask.psd",),
        ("mask-disabled.psd",),
        ("mask-density-layermask.psd",),
        ("mask-density-vectormask.psd",),
        pytest.param(
            "mask-density-layervectormask.psd",
            marks=pytest.mark.xfail(
                reason=(
                    "usermask carries over layer and vector mask properties"
                    "(layer and vector masks are not isolated)"
                )
            ),
        ),
        # ('vector-mask.psd', ),  # 32-bit blending not working.
        ("vector-mask-disabled.psd",),
        ("vector-mask3.psd",),
    ],
)
def test_composite_quality(filename: str) -> None:
    check_composite_quality(filename, 0.001, False)


@pytest.mark.parametrize(
    ("filename",),
    [
        ("advanced-blending.psd",),
        ("vector-mask2.psd",),
    ],
)
@pytest.mark.xfail
def test_composite_quality_xfail(filename: str) -> None:
    check_composite_quality(filename, 0.01, False)


@pytest.mark.parametrize(
    "filename",
    [
        "smartobject-layer.psd",
        "type-layer.psd",
        "gradient-fill.psd",
        "shape-layer.psd",
        "pixel-layer.psd",
        "solid-color-fill.psd",
        "pattern-fill.psd",
    ],
)
def test_composite_minimal(filename: str) -> None:
    source = PSDImage.open(full_name("layers-minimal/" + filename))
    reference = PSDImage.open(full_name("layers/" + filename)).numpy()
    color, _, alpha = composite(source, force=True)
    result = color
    if reference.shape[2] > color.shape[2]:
        result = np.concatenate((color, alpha), axis=2)
    assert _mse(reference, result) <= 0.017


@pytest.mark.parametrize(
    "colormode, depth",
    [
        ("bitmap", 1),
        ("cmyk", 8),
        ("duotone", 8),
        ("grayscale", 8),
        ("index_color", 8),
        ("rgb", 8),
        ("rgba", 8),
        ("lab", 8),
        ("multichannel", 16),
    ],
)
def test_composite_colormodes(colormode: str, depth: int) -> None:
    filename = "colormodes/4x4_%gbit_%s.psd" % (depth, colormode)
    psd = PSDImage.open(full_name(filename))
    composite_error(psd, 0.01, False, "color")


# These failures are due to inaccurate gradient fill synthesis.
@pytest.mark.parametrize(
    "colormode, depth",
    [
        ("cmyk", 16),
        ("grayscale", 16),
        ("lab", 16),
        ("rgb", 16),
        ("grayscale", 32),
        ("rgb", 32),
    ],
)
@pytest.mark.xfail
def test_composite_colormodes_xfail(colormode: str, depth: int) -> None:
    filename = "colormodes/4x4_%gbit_%s.psd" % (depth, colormode)
    psd = PSDImage.open(full_name(filename))
    composite_error(psd, 0.01, False, "color")


def test_composite_artboard() -> None:
    psd = PSDImage.open(full_name("artboard.psd"))
    document_image = psd.numpy()
    assert document_image.shape[:2] == (psd.height, psd.width)
    artboard = psd[0]
    artboard_image = composite(artboard)[0]
    assert artboard_image.shape[:2] == (artboard.height, artboard.width)


def test_composite_artboard_bgcolor() -> None:
    """Regression test for issue #395: artboard background color in compositing."""
    psd = PSDImage.open(full_name("artboard-bgcolor.psd"))

    # Artboard 0: blue background (18, 108, 200)
    # Child layer bbox=(79,46,308,234) — pixel (0,0) is guaranteed background-only
    ab0 = psd[0]
    assert ab0.kind == "artboard"
    img0 = ab0.composite()
    assert img0 is not None
    pixel0 = img0.getpixel((0, 0))
    assert isinstance(pixel0, tuple)
    r, g, b = pixel0[:3]
    assert abs(r - 18) <= 2 and abs(g - 108) <= 2 and abs(b - 200) <= 2
    # Opaque backdrop → alpha channel omitted (RGB mode) or fully opaque
    if len(pixel0) == 4:
        assert pixel0[3] == 255

    # Artboard 1: orange background (200, 95, 18)
    # Child layer bbox=(571,59,680,410); local (0,0) is outside child
    ab1 = psd[1]
    assert ab1.kind == "artboard"
    img1 = ab1.composite()
    assert img1 is not None
    pixel1 = img1.getpixel((0, 0))
    assert isinstance(pixel1, tuple)
    r, g, b = pixel1[:3]
    assert abs(r - 200) <= 2 and abs(g - 95) <= 2 and abs(b - 18) <= 2
    if len(pixel1) == 4:
        assert pixel1[3] == 255


def test_composite_viewport() -> None:
    psd = PSDImage.open(full_name("layers/smartobject-layer.psd"))
    bbox = (1, 1, 31, 31)

    shape = (bbox[3] - bbox[1], bbox[2] - bbox[0], 1)
    assert composite(psd)[1].shape == (psd.height, psd.width, 1)
    assert composite(psd, viewport=bbox)[1].shape == shape

    assert composite(psd[0])[1].shape == (psd[0].height, psd[0].width, 1)
    assert composite(psd[0], viewport=bbox)[1].shape == shape


@pytest.mark.parametrize(
    "colormode, depth, mode, ignore_preview, apply_icc",
    [
        ("bitmap", 1, "1", False, False),
        ("cmyk", 8, "CMYK", False, False),
        ("duotone", 8, "L", False, False),
        ("grayscale", 8, "L", False, False),
        ("index_color", 8, "P", False, False),
        ("rgb", 8, "RGB", False, False),
        ("rgba", 8, "RGB", False, False),  # Extra alpha is not transparency
        ("lab", 8, "LAB", False, False),
        ("multichannel", 16, "L", False, False),
        ("bitmap", 1, "1", True, False),
        ("cmyk", 8, "CMYK", True, False),
        ("duotone", 8, "LA", True, False),
        ("grayscale", 8, "LA", True, False),
        ("index_color", 8, "RGBA", True, False),
        ("rgb", 8, "RGBA", True, False),
        ("rgba", 8, "RGBA", True, False),
        ("lab", 8, "LAB", True, False),
        ("multichannel", 16, "LA", True, False),
        ("cmyk", 8, "RGBA", True, True),
        ("rgb", 8, "RGB", False, True),
        ("duotone", 8, "L", False, True),
    ],
)
def test_composite_pil(
    colormode: str, depth: int, mode: str, ignore_preview: bool, apply_icc: bool
) -> None:
    filename = "colormodes/4x4_%gbit_%s.psd" % (depth, colormode)
    psd = PSDImage.open(full_name(filename))
    image = psd.composite(ignore_preview=ignore_preview, apply_icc=apply_icc)
    assert isinstance(image, Image.Image)
    assert image.mode == mode
    for layer in psd:
        assert isinstance(layer.composite(apply_icc=apply_icc), Image.Image)


_BACKDROP_SPELLINGS = [
    pytest.param(1, id="int"),
    pytest.param(1.0, id="float"),
    pytest.param(np.float32(1.0), id="numpy-scalar"),
    pytest.param(np.int64(1), id="numpy-int"),
    pytest.param((1.0, 1.0, 1.0), id="tuple"),
    pytest.param([1.0, 1.0, 1.0], id="list"),
    pytest.param(np.ones((4, 4, 3), dtype=np.float32), id="ndarray"),
    pytest.param(np.ones((4, 4, 1), dtype=np.float32), id="single-channel-canvas"),
]


@pytest.mark.parametrize("color", _BACKDROP_SPELLINGS)
def test_composite_backdrop_spellings_agree(color: Any) -> None:
    """Every accepted spelling of the same white backdrop must composite alike.

    Regression test for #709: ``color=1`` and ``color=np.float32(1.0)`` raised
    ``TypeError`` because only ``float`` was recognised as a scalar.
    """
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_rgb.psd"))
    reference, _, _ = composite(psd, color=1.0)
    result, _, _ = composite(psd, color=color)
    assert result.shape == reference.shape
    assert np.array_equal(result, reference)


@pytest.mark.parametrize("color", [1, 1.0, np.float32(1.0), (1.0,), [1.0]])
def test_composite_backdrop_spellings_agree_grayscale(color: Any) -> None:
    """Same as above for a single-channel document."""
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_grayscale.psd"))
    reference, _, _ = composite(psd, color=1.0)
    result, _, _ = composite(psd, color=color)
    assert result.shape == reference.shape
    assert np.array_equal(result, reference)


@pytest.mark.parametrize("alpha", [1, 1.0, np.float32(1.0)])
def test_composite_backdrop_alpha_spellings_agree(alpha: Any) -> None:
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_rgba.psd"))
    reference, _, _ = composite(psd, color=0.0, alpha=1.0)
    result, _, _ = composite(psd, color=0.0, alpha=alpha)
    assert np.array_equal(result, reference)


@pytest.mark.parametrize(
    "alpha",
    [
        pytest.param(0, id="int"),
        pytest.param(0.0, id="float"),
        pytest.param(np.float32(0.0), id="numpy-scalar"),
        pytest.param(np.array(0.0), id="0d-array"),
        pytest.param(np.zeros((4, 4, 1), dtype=np.float32), id="array-of-zeros"),
    ],
)
def test_composite_transparent_backdrop_is_skipped_in_any_spelling(
    alpha: Any,
) -> None:
    """A transparent backdrop must be recognised however it is spelled.

    The zero-layer path skips the blend for a transparent backdrop, because
    blending it in anyway sends ``utils.divide`` down its 0 / 0 -> 1.0 branch
    and whitens every uncovered pixel. The old guard tested for ``int`` and
    ``float`` only, so a NumPy scalar took the blend and came back white; a
    per-pixel array of zeros did too (PR #721 review).
    """
    psd = PSDImage.new("RGBA", (4, 4), color=(0, 0, 0, 0))
    assert len(psd) == 0
    result, _, _ = composite(psd, color=1.0, alpha=alpha)
    assert np.array_equal(result, np.zeros_like(result))


@pytest.mark.parametrize(
    ("filename", "kwargs"),
    [
        # Nothing to composite: every layer filtered out.
        ("colormodes/4x4_8bit_rgb.psd", {"layer_filter": lambda layer: False}),
        # Nothing to composite either: the only layer is an adjustment, which
        # transforms the backdrop rather than applying a source over it.
        ("layers/curves.psd", {}),
        ("layers/levels.psd", {}),
        ("layers/brightness-contrast.psd", {}),
    ],
)
def test_composite_single_channel_backdrop_without_a_source(
    filename: str, kwargs: Any
) -> None:
    """A one-channel backdrop must still produce a document-width image (#710).

    The canvas used to be widened lazily at the first source, so a document
    with no source to apply kept a one-channel color array and blew up on the
    way out -- in ``Image.fromarray()``, or in ``_preserve_alpha`` for the
    adjustment cases.
    """
    psd = PSDImage.open(full_name(filename))
    backdrop = np.full((psd.height, psd.width, 1), 0.25, dtype=np.float32)
    image = psd.composite(color=backdrop, alpha=1.0, ignore_preview=True, **kwargs)
    assert image.mode == "RGB"
    assert image.size == (psd.width, psd.height)


def test_composite_backdrop_rejects_an_unresolvable_channel_count() -> None:
    """Three channels against a four-channel document has no reading (#710)."""
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_cmyk.psd"))
    with pytest.raises(ValueError, match="has 3 channels, expected 1 or 4"):
        composite(psd, color=np.ones((4, 4, 3), dtype=np.float32), alpha=1.0)


def test_composite_backdrop_rejects_a_mismatched_channel_count() -> None:
    """A wrong-width backdrop is an error rather than a silently odd canvas."""
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_rgb.psd"))
    with pytest.raises(ValueError, match="cannot be expanded"):
        composite(psd, color=(1.0, 0.0))


def test_composite_backdrop_rejects_a_wrong_width_sequence_for_the_color_mode() -> None:
    """**Backwards incompatible.** A 3-tuple over a 1-channel document raises.

    This used to produce a three-channel result for a grayscale document,
    which ``composite_pil`` then silently reduced by taking channel 0. Pinned
    deliberately: the loud failure is the intent, not an accident.
    """
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_grayscale.psd"))
    with pytest.raises(ValueError, match="cannot be expanded"):
        composite(psd, color=(1.0, 1.0, 1.0), alpha=1.0)


def test_composite_backdrop_rejects_a_multi_channel_alpha() -> None:
    """Alpha is single-channel by definition (PR #721 review).

    A wider alpha survived to ``finish()`` on the zero-layer path, where
    ``composite_pil()`` concatenates it onto the color array and would build an
    image of the wrong width.
    """
    psd = PSDImage.new("RGBA", (4, 4), color=(0, 0, 0, 0))
    with pytest.raises(ValueError, match=r"alpha has shape"):
        composite(psd, color=1.0, alpha=np.ones((4, 4, 3), dtype=np.float32))


def test_composite_does_not_mutate_a_caller_supplied_backdrop() -> None:
    """The compositor stores the caller's array; it must never write to it."""
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_rgb.psd"))
    backdrop = np.full((psd.height, psd.width, 3), 0.25, dtype=np.float32)
    composite(psd, color=backdrop, alpha=1.0)
    assert np.array_equal(backdrop, np.full_like(backdrop, 0.25))


def test_composite_empty_document_backdrop() -> None:
    """The zero-layer path normalizes its backdrop like any other.

    It is reached before any layer exists, so it sizes the backdrop from the
    preview array rather than from the color mode.
    """
    psd = PSDImage.new("RGB", (4, 4), color=0)
    assert len(psd) == 0
    reference, _, _ = composite(psd, color=1.0, alpha=1.0)
    spellings: list[Any] = [1, np.float32(1.0), (1.0, 1.0, 1.0)]
    for color in spellings:
        result, _, _ = composite(psd, color=color, alpha=1.0)
        assert np.array_equal(result, reference), color


def test_composite_layerless_multichannel_over_a_backdrop() -> None:
    """A multichannel document has more channels than its color mode predicts.

    ``EXPECTED_CHANNELS[MULTICHANNEL]`` is 64, so sizing the backdrop from the
    color mode could not be blended against the document's own array and raised
    ``ValueError``. The zero-layer path sizes from that array instead.
    """
    psd = PSDImage.open(full_name("colormodes/4x4_16bit_multichannel.psd"))
    assert len(psd) == 0
    color, _, _ = composite(psd, color=1.0, alpha=1.0)
    assert color.shape == (psd.height, psd.width, psd.numpy("color").shape[2])


def _layered_multichannel(**kwargs: Any) -> PSDImage:
    """A multichannel document *with* layers, which no fixture provides.

    Photoshop neither produces nor preserves this shape: converting to
    Multichannel flattens, and *opening* a hand-built layered multichannel file
    discards the layer records outright. Verified against Photoshop 2026, which
    reduced a 13-layer retagged document to a single Background layer whose
    three channels it presents as spot channels ("Alpha 1".."Alpha 3") holding
    the file's merged image data bit-for-bit. So a document of this shape is
    only ever hand-built -- which is exactly the input the allocation guard
    exists for -- and there is no Photoshop render to check a layered
    multichannel composite against, because Photoshop declines to composite
    one.

    Retagging the RGB fixture's color mode in place is the whole of
    it: that fixture's three document channels and its layers' three color
    channels already agree, as they would in a multichannel file with three
    spot channels, so nothing else about the document has to change.

    Built this way rather than with ``PSDImage.new`` + ``PixelLayer.frompil``
    on purpose. ``frompil`` converts to the document's ``pil_mode``, which is
    ``"LA"`` for a three-channel multichannel document, so the layer would
    carry a single color channel against a header declaring three -- and a
    one-channel source broadcasts, so the test would pass without ever
    exercising the canvas width it is about.
    """
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_rgb.psd"), **kwargs)
    psd._record.header.color_mode = ColorMode.MULTICHANNEL
    return psd


def test_composite_layered_multichannel_uses_the_header_channel_count() -> None:
    """A multichannel backdrop is as wide as the document says it is (#720).

    ``EXPECTED_CHANNELS[MULTICHANNEL]`` is 64 -- the format's maximum, not any
    document's count -- so the backdrop was allocated 64 channels wide and the
    first three-channel layer met it with an ``AssertionError``. The zero-layer
    path was fixed in #708 by sizing from the document's own array; the layered
    path has no such array to consult, so it asks the header instead.
    """
    psd = _layered_multichannel()
    assert psd.channels == 3
    assert len(psd) > 0
    color, _, _ = composite(psd)
    assert color.shape == (psd.height, psd.width, psd.channels)
    # Its one layer carrying pixel data covers the whole canvas opaquely, so
    # the composite reproduces the document's own merged preview.
    assert _mse(color, psd.numpy("color")) <= 1e-6


def test_composite_layered_multichannel_within_a_budget() -> None:
    """A budget that admits the real canvas is no longer overrun (#720).

    The three-channel canvas needs 192 bytes where the 64-channel one needed
    4096, so this budget sits between the two. It is not the guard that used to
    reject the document -- the guard was told 3 all along -- it is the canvas
    that used to be built ~21x wider than the guard was promised.
    """
    psd = _layered_multichannel(max_alloc_bytes=1024)
    color, _, _ = composite(psd)
    assert color.shape == (psd.height, psd.width, 3)


def test_composite_guard_estimate_covers_a_mode_that_expands() -> None:
    """The estimate never falls below the canvas that follows it (#720).

    ``max_alloc_bytes`` is there to reject a file *before* it allocates, so the
    number it is checked against has to bound what comes next. An indexed
    document stores one channel and composites over three, its palette having
    expanded it, so the header count alone under-estimated the canvas by 3x.

    Retagged rather than taken from a fixture for the same reason as
    ``_layered_multichannel``: Photoshop flattens on conversion to Indexed
    Color, so ``colormodes/4x4_8bit_index_color.psd`` has no layers and takes
    ``composite()``'s zero-layer early return, never reaching this estimate.
    Only the *layered* path consults the palette-expanded width, and it does not
    read the palette itself, so retagging a layered grayscale document is
    enough. This is the only mode left where the canvas is wider than the
    header, so it is the only way to exercise that side of the ``max()``.
    """
    psd = PSDImage.open(
        full_name("colormodes/4x4_8bit_grayscale.psd"), max_alloc_bytes=100
    )
    psd._record.header.color_mode = ColorMode.INDEXED
    assert psd.channels == 1
    assert len(psd) > 0
    # 4 * 4 * 3 * 4 = 192 bytes, over the budget; the header's own count of one
    # channel would have estimated 64 bytes and let it through.
    with pytest.raises(ValueError, match="4x4x3"):
        composite(psd)


def test_composite_guard_estimate_takes_the_header_when_it_is_wider() -> None:
    """The other side of the same ``max()`` (#720).

    ``4x4_8bit_rgba.psd`` declares four channels and composites over three, so
    here it is the header that bounds the pair. Both sides are pinned because
    the guard is a security control: an estimate below the allocation defeats
    it, and one needlessly above it rejects files that would have been fine.
    """
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_rgba.psd"), max_alloc_bytes=200)
    assert psd.channels == 4
    with pytest.raises(ValueError, match="4x4x4"):
        composite(psd)


def test_composite_duotone_is_one_channel_wide() -> None:
    """Duotone composites at its stored width, not its ink count (#733).

    ``EXPECTED_CHANNELS[DUOTONE]`` was 2 -- the inks -- while duotone pixel data
    is a single grayscale channel, the ink curves living in the color mode data
    section. So the backdrop was built two channels wide and every real source
    broadcast against it: the second channel of the result was not data from the
    file at all, it was the backdrop copied.
    """
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_duotone.psd"))
    assert psd.channels == 1
    assert psd.numpy("color").shape[2] == 1
    color, _, _ = composite(psd)
    assert color.shape == (psd.height, psd.width, 1)


@pytest.mark.parametrize(
    "blend_mode",
    [
        BlendMode.COLOR_BURN,
        BlendMode.COLOR_DODGE,
        BlendMode.HARD_LIGHT,
        BlendMode.LINEAR_LIGHT,
        BlendMode.PIN_LIGHT,
        BlendMode.SOFT_LIGHT,
        BlendMode.VIVID_LIGHT,
    ],
)
def test_composite_duotone_with_a_channelwise_blend_mode(blend_mode: BlendMode) -> None:
    """These blend modes crashed on every duotone document (#733).

    They index the color array with a mask derived from it -- ``blend.py``'s
    ``B[Cs == 1] = 1`` and friends -- which needs the operands to agree in
    width. A two-channel canvas against a one-channel source did not::

        IndexError: boolean index did not match indexed array along axis 2;
        size of axis is 2 but size of corresponding boolean axis is 1

    All seven of the blend modes listed here raised it. Photoshop keeps layers
    in duotone mode, so this was reachable on ordinary documents rather than
    only on hand-built ones.

    ``Hue``, ``Saturation``, ``Color`` and ``Luminosity`` still raise, and are
    deliberately not listed: they fail identically on
    ``colormodes/4x4_8bit_grayscale.psd``, so that is a pre-existing
    single-channel-document bug rather than anything duotone-specific. Duotone
    now behaves exactly as grayscale does, which is the point.
    """
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_duotone.psd"))
    for layer in psd:
        layer.blend_mode = blend_mode
    color, _, _ = composite(psd)
    assert color.shape == (psd.height, psd.width, 1)


def test_composite_pil_duotone_force_keeps_the_luminance_plane_intact() -> None:
    """``force=True`` returned sheared pixels for duotone documents (#733).

    With the canvas two channels wide, ``composite_pil()`` concatenated alpha
    onto it and handed ``Image.fromarray()`` a 3-byte-per-pixel buffer declared
    as 2-byte ``"LA"``. PIL does not reject that, so the planes came out shifted
    against each other -- the first row's luminance read ``[75, 255, 53, 179]``
    where the composite says ``[75, 53, 179, 241]``, the 255 being an alpha byte
    that had slid into the colour plane. This is a wrong-pixels bug, not a
    width one, so it is pinned against the numpy composite rather than by shape.
    """
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_duotone.psd"))
    image = psd.composite(ignore_preview=True, force=True, apply_icc=False)
    assert isinstance(image, Image.Image)
    assert image.mode == "LA"
    color, _, _ = composite(psd, force=True)
    luminance = np.asarray(image)[:, :, 0].astype(np.int16)
    expected = (color[:, :, 0] * 255).round().astype(np.int16)
    assert np.abs(luminance - expected).max() <= 2
    # The document is opaque; the alpha plane must be alpha, not a colour byte.
    assert (np.asarray(image)[:, :, 1] == 255).all()


def test_composite_pil_layered_multichannel_truncates_like_the_layerless_one() -> None:
    """Pinning what the PIL exit does now that this shape reaches it (#720).

    ``get_pil_mode(MULTICHANNEL)`` is ``"L"``, so ``composite_pil()`` keeps the
    first spot channel and drops the rest. That is not new -- it is what the
    layerless fixture already does in ``test_composite_pil``, and a layered
    document now lands on exactly the same two modes instead of raising. Pinned
    here so the truncation is a recorded consequence of letting these documents
    composite at all. Only the numpy ``composite()`` entry point returns every
    channel.
    """
    psd = _layered_multichannel()
    preview = psd.composite(apply_icc=False)
    assert isinstance(preview, Image.Image)
    assert preview.mode == "L"  # served from the stored preview, uncomposited
    image = psd.composite(ignore_preview=True, apply_icc=False)
    assert isinstance(image, Image.Image)
    assert image.mode == "LA"  # first spot channel, plus the composite alpha
    color, _, _ = composite(psd)
    assert _mse(np.asarray(image)[:, :, 0] / 255.0, color[:, :, 0]) <= 1e-4


def test_composite_layer_filter() -> None:
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_rgba.psd"))
    # Check layer_filter.
    rendered = psd.composite(layer_filter=lambda x: False)
    reference = psd.topil()
    assert reference is not None
    assert all(a != b for a, b in zip(rendered.getextrema(), reference.getextrema()))


def test_apply_mask() -> None:
    psd = PSDImage.open(full_name("masks/2.psd"))
    reference = np.asarray(Image.open(full_name("masks/2.png"))) / 255.0
    result = np.concatenate(composite(psd)[::2], axis=2)
    assert reference.shape == result.shape
    # Hidden color seems different.
    assert _mse(reference[:, :, -1], result[:, :, -1]) <= 0.01


def test_group_mask() -> None:
    psd = PSDImage.open(full_name("masks3.psd"))
    reference = psd.numpy()
    result = composite(psd, force=True)[0]
    assert _mse(reference, result) <= 0.01


def test_apply_opacity() -> None:
    psd = PSDImage.open(full_name("opacity-fill.psd"))
    result = composite(psd)
    assert _mse(psd.numpy("shape"), result[2]) < 0.01


# Photoshop-authored fixtures pinning Knockout semantics; see issue #707.
#
# Knockout has no visible effect while fill opacity is 100%, which is why the
# pre-existing knockout-isolated-groups.psd fixture never exercised it. Every
# fixture below therefore sets the knockout group's fill opacity to 50%.
#
# Each stack is: white Background / red BG / group. The "nested" fixtures put a
# green sibling next to the knockout group inside an ``Outer`` group, so three
# outcomes are distinguishable at the sampled pixel:
#
#   green  -> no knockout                          (composites over the sibling)
#   red    -> knocked out to the enclosing group's backdrop
#   white  -> knocked out to the document backdrop
#
# Expected values are Photoshop 2026's own rendering, sampled at (16, 16).
_KNOCKOUT_CASES = [
    # No knockout: the group simply composites over what is below it.
    ("knockout-none-normal", (127, 0, 128)),
    ("knockout-none-passthrough", (127, 0, 128)),
    ("knockout-none-nested", (0, 127, 128)),
    ("knockout-none-cyanbg", (127, 0, 128)),
    # Shallow knockout stops at the enclosing group's backdrop (the red BG).
    ("knockout-shallow-nested", (127, 0, 128)),
    ("knockout-shallow-nested-pt", (127, 0, 128)),
    # An isolated (non pass-through) ``Outer`` bounds deep knockout too, so this
    # matches the shallow result rather than reaching the document backdrop.
    ("knockout-deep-nested", (127, 0, 128)),
    # Deep knockout reaches the document backdrop. The Background layer is part
    # of that backdrop and is *not* knocked out -- knockout-deep-cyanbg pins
    # this down, since a white Background cannot be told apart from knocking
    # through to transparency and flattening onto white.
    ("knockout-deep-cyanbg", (0, 127, 255)),
    ("knockout-deep-normal", (127, 127, 255)),
    # A knockout group renders the same whether or not it is pass-through:
    # when knockout is set, the pass-through blend mode stops mattering.
    ("knockout-deep-passthrough", (127, 127, 255)),
    # ``Outer`` is pass-through here, so it is not an isolation boundary and
    # deep knockout escapes it to reach the document backdrop.
    ("knockout-deep-nested-pt", (127, 127, 255)),
]


@pytest.mark.parametrize(("name", "expected"), _KNOCKOUT_CASES)
def test_composite_knockout(name: str, expected: tuple[int, int, int]) -> None:
    psd = PSDImage.open(full_name(f"transparency/{name}.psd"))
    image = psd.composite(ignore_preview=True)
    assert image is not None
    pixel = image.convert("RGBA").getpixel((16, 16))
    assert isinstance(pixel, tuple)
    # Every fixture has an opaque Background layer, so a correct render is
    # opaque (254 rather than 255 after the compositor's rounding). Asserting
    # this matters: knocking through to transparency would otherwise be masked
    # by dropping the alpha channel before comparing.
    assert pixel[3] >= 250, f"{name}: expected an opaque result, got alpha={pixel[3]}"
    assert all(abs(a - b) <= 2 for a, b in zip(pixel[:3], expected)), (
        f"{name}: Photoshop renders {expected}, psd-tools rendered {pixel[:3]}"
    )


def test_composite_knockout_without_background_layer() -> None:
    """Deep knockout reaches full transparency when there is no Background layer.

    This is the other half of the semantics pinned by knockout-deep-cyanbg: the
    Background layer is the canvas, not an ordinary layer. The fixture is the
    same stack with its Background converted to an ordinary layer, and Photoshop
    knocks all the way through to transparency, removing both layers beneath.
    """
    psd = PSDImage.open(full_name("transparency/knockout-deep-nobg.psd"))
    image = psd.composite(ignore_preview=True)
    assert image is not None
    r, g, b, a = image.convert("RGBA").getpixel((16, 16))  # type: ignore[misc]
    # Photoshop renders (0, 0, 255, 128): pure blue at half alpha.
    assert (r, g, b) == (0, 0, 255)
    assert abs(a - 128) <= 2


def test_composite_knockout_undefined_value(tmp_path: Any, caplog: Any) -> None:
    """An undefined KNOCKOUT_SETTING byte degrades instead of raising.

    The tagged block is a raw byte, so a corrupt or third-party file can carry a
    value outside the Knockout enum. Compositing must not crash on it.
    """
    psd = PSDImage.new(mode="RGB", size=(8, 8))
    psd.create_pixel_layer(image=Image.new("RGBA", (8, 8), (255, 0, 0, 255)), name="BG")
    group = psd.create_group(name="G0")
    group.blend_mode = BlendMode.NORMAL
    group.tagged_blocks.set_data(Tag.KNOCKOUT_SETTING, ByteElement(7))
    group.tagged_blocks.set_data(Tag.BLEND_FILL_OPACITY, ByteElement(128))
    group.append(PixelLayer.frompil(Image.new("RGBA", (8, 8), (0, 0, 255, 255)), psd))

    path = tmp_path / "undefined-knockout.psd"
    psd.save(str(path))

    with caplog.at_level(logging.WARNING, logger="psd_tools.composite.composite"):
        image = PSDImage.open(str(path)).composite(ignore_preview=True)
    assert image is not None
    # Falls back to Knockout.NONE, i.e. renders as if the setting were absent.
    assert image.convert("RGB").getpixel((4, 4)) == (127, 0, 128)
    assert any(
        "Unknown knockout setting" in record.message for record in caplog.records
    )


def test_composite_clipping_mask() -> None:
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    reference = composite(psd)
    result = composite(psd, layer_filter=lambda x: x.name != "Shape 3")
    assert _mse(reference[0], result[0]) > 0


def test_composite_group_clipping_photoshop() -> None:
    psd = PSDImage.open(full_name("group-clipping/group-clipping.psd"))
    reference = Image.open(full_name("group-clipping/group-clipping-photoshop.png"))
    psd.compatibility_mode = CompatibilityMode.PHOTOSHOP
    result = psd.composite(force=True)
    assert (
        _mse(np.array(reference, dtype=np.float32), np.array(result, dtype=np.float32))
        <= 0.001
    )


def test_composite_group_clipping_clip_studio() -> None:
    psd = PSDImage.open(full_name("group-clipping/group-clipping.psd"))
    reference = Image.open(full_name("group-clipping/group-clipping-clip-studio.png"))
    psd.compatibility_mode = CompatibilityMode.CLIP_STUDIO_PAINT
    result = psd.composite(force=True)
    assert (
        _mse(np.array(reference, dtype=np.float32), np.array(result, dtype=np.float32))
        <= 0.001
    )


def _pattern_overlay_layer(psd: PSDImage) -> Any:
    return next(
        sub
        for top in psd
        for sub in [top] + list(getattr(top, "_layers", None) or [])
        if list(sub.effects.find("patternoverlay"))
    )


def test_composite_pattern_overlay_targets_the_canvas_width() -> None:
    """The pattern's width comes from the compositor's canvas.

    ``_draw_pattern_overlay`` used to take it from the layer colour it was
    handed, which #710 allows to be narrower than the document. An RGB pattern
    was then compared against 1 and rejected with ``AssertionError: Inconsistent
    pattern channels.`` even though it matched the canvas exactly.

    Dropping that parameter (#711) makes the original mistake unconstructible --
    there is no longer a layer colour to derive the width from -- so this is a
    contract pin rather than a regression guard.
    """
    psd = PSDImage.open(full_name("patterns.psd"))
    layer = _pattern_overlay_layer(psd)
    shape = np.ones((psd.height, psd.width, 1), dtype=np.float32)
    compositor = Compositor(
        psd.viewbox,
        np.ones((psd.height, psd.width, 3), dtype=np.float32),
        np.zeros((psd.height, psd.width, 1), dtype=np.float32),
    )
    assert compositor.channels == 3
    compositor._apply_overlay(layer, "patternoverlay", shape, shape)
    assert compositor.finish()[0].shape == (psd.height, psd.width, 3)


@pytest.mark.parametrize("channels", [1, 4])
@pytest.mark.skipif(
    not __debug__, reason="the consistency check is an assert, stripped under -O"
)
def test_composite_pattern_overlay_rejects_a_width_it_cannot_reach(
    channels: int,
) -> None:
    """A pattern must be one channel or exactly the canvas width.

    Widening replicates a single channel, so it can reach 3 from 1 but cannot
    reach 1 or 4 from 3. That mismatch is a real inconsistency and stays caught.
    """
    psd = PSDImage.open(full_name("patterns.psd"))
    layer = _pattern_overlay_layer(psd)
    shape = np.ones((psd.height, psd.width, 1), dtype=np.float32)
    compositor = Compositor(
        psd.viewbox,
        np.ones((psd.height, psd.width, channels), dtype=np.float32),
        np.zeros((psd.height, psd.width, 1), dtype=np.float32),
    )
    with pytest.raises(AssertionError, match="Inconsistent pattern channels"):
        compositor._apply_overlay(layer, "patternoverlay", shape, shape)


def _descendants(group: Any) -> Any:
    for layer in group:
        yield layer
        if isinstance(layer, GroupMixin):
            yield from _descendants(layer)


def _canvas(psd: PSDImage) -> Compositor:
    return Compositor(
        psd.viewbox,
        np.ones((psd.height, psd.width, 3), dtype=np.float32),
        np.zeros((psd.height, psd.width, 1), dtype=np.float32),
    )


def test_accepts_defers_a_clipping_layer_to_its_base() -> None:
    """A clipping layer is composited by the layer it clips to, not on its own.

    ``_apply_clip_layers()`` re-enters ``apply()`` with ``clip_compositing``,
    which is the only way past this rejection.
    """
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    clipped = next(layer for layer in _descendants(psd) if layer.clipping)
    compositor = _canvas(psd)
    assert not compositor._accepts(clipped, clip_compositing=False)
    assert compositor._accepts(clipped, clip_compositing=True)


def test_accepts_rejects_a_layer_outside_the_viewport() -> None:
    """Culling applies to ordinary layers; groups and adjustments are exempt."""
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    elsewhere = (1000, 1000, 1010, 1010)
    compositor = Compositor(
        elsewhere,
        np.ones((10, 10, 3), dtype=np.float32),
        np.zeros((10, 10, 1), dtype=np.float32),
    )
    # Both exemptions have to be excluded here, not just the group one: an
    # adjustment layer would legitimately be accepted and the assertion below
    # would then be pinning the wrong branch.
    ordinary = next(
        layer
        for layer in _descendants(psd)
        if not isinstance(layer, (GroupMixin, AdjustmentLayer))
    )
    assert not compositor._accepts(ordinary, clip_compositing=False)
    group = next(layer for layer in _descendants(psd) if isinstance(layer, GroupMixin))
    assert compositor._accepts(cast(Layer, group), clip_compositing=False)


def test_accepts_honours_the_layer_filter() -> None:
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    compositor = Compositor(
        psd.viewbox,
        np.ones((psd.height, psd.width, 3), dtype=np.float32),
        np.zeros((psd.height, psd.width, 1), dtype=np.float32),
        layer_filter=lambda layer: False,
    )
    assert not compositor._accepts(psd[0], clip_compositing=False)


def test_resolve_source_reads_the_layer_without_writing_the_canvas() -> None:
    """The split's contract: resolving is a read, compositing is the write."""
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    compositor = _canvas(psd)
    before = compositor.result_over_backdrop().copy()

    source = compositor._resolve_source(psd[0])
    assert source.color.shape == (psd.height, psd.width, 3)
    assert np.array_equal(compositor.result_over_backdrop(), before)

    compositor._composite_source(source, psd[0].blend_mode)
    assert not np.array_equal(compositor.result_over_backdrop(), before)


def test_resolve_source_folds_the_mask_and_opacity_into_the_operands() -> None:
    """Opacity reaches ``alpha`` but not ``shape``; fill opacity reaches neither.

    Fill opacity is left to ``_composite_source()`` because knockout applies it
    to ``alpha`` only, and the source's full coverage punches the hole.
    """
    psd = PSDImage.open(full_name("clipping-mask.psd"))
    layer = psd[0]
    layer.opacity = 128
    compositor = _canvas(psd)
    source = compositor._resolve_source(layer)
    assert np.allclose(source.alpha, source.shape * (128 / 255.0))
    assert source.fill_opacity == 1.0


def test_composite_stroke_effect_over_a_layer_without_a_mask() -> None:
    """A stroke effect must not require the layer to have a mask (#711).

    ``_get_mask()`` returns a bare 1.0 for a layer with no mask, and
    ``_apply_stroke_effect`` handed that straight to ``paste()``, which needs a
    canvas -- ``AttributeError: 'float' object has no attribute 'shape'``. The
    combination is reachable for a fill layer with no vector mask, and 26 calls
    in the fixture corpus already pass the scalar; they escape only because
    those layers have no stroke effect.
    """
    psd = PSDImage.open(full_name("effects/stroke-effects.psd"))
    layer = next(
        sub
        for top in psd
        for sub in (getattr(top, "_layers", None) or [])
        if list(sub.effects.find("stroke"))
    )
    backdrop = np.ones((psd.height, psd.width, 3), dtype=np.float32)
    alpha = np.zeros((psd.height, psd.width, 1), dtype=np.float32)
    compositor = Compositor(psd.viewbox, backdrop, alpha)
    # 1.0 is exactly what _get_mask() yields for an unmasked layer.
    compositor._apply_stroke_effect(layer, 1.0, np.ones_like(alpha))
    assert compositor.finish()[0].shape == (psd.height, psd.width, 3)


def test_composite_stroke() -> None:
    psd = PSDImage.open(full_name("stroke.psd"))
    reference = composite(psd, force=True)
    result = composite(psd)
    assert _mse(reference[0], result[0]) > 0


def test_composite_pixel_layer_with_vector_stroke() -> None:
    psd = PSDImage.open(full_name("effects/stroke-without-vector-mask.psd"))
    reference = composite(psd, force=True)
    result = composite(psd)
    assert _mse(reference[0], result[0]) <= 0.01


def test_composite_mixed_colorspace_stroke() -> None:
    """Regression test for issue #397: ValueError on vector layer with CMYK stroke + Grayscale fill."""
    psd = PSDImage.open(full_name("issues/issue397.psd"))
    psd.composite()
    for layer in psd:
        if isinstance(layer, GroupMixin):
            for sublayer in layer:
                sublayer.composite()
