import logging
from typing import Callable

import numpy as np
import pytest
from PIL import Image

from psd_tools import PSDImage
from psd_tools.api.layers import GroupMixin, PixelLayer
from psd_tools.composite.blend import (
    BLEND_FUNC,
    color,
    darker_color,
    hue,
    lighter_color,
    luminosity,
    normal,
    saturation,
)
from psd_tools.constants import BlendMode
from .test_composite import check_composite_quality

logger = logging.getLogger(__name__)


def test_lighter_color_descriptor_key() -> None:
    """Regression: b"lighterColor" was previously a typo (b"ligherColor")
    which silently fell back to the normal blend mode for effects/strokes."""
    assert BLEND_FUNC.get(b"lighterColor") is lighter_color
    assert BLEND_FUNC.get(b"lighterColor") is not normal


@pytest.mark.parametrize(
    ("filename",),
    [
        ("blend-modes/normal.psd",),
        ("blend-modes/multiply.psd",),
        ("blend-modes/screen.psd",),
        ("blend-modes/overlay.psd",),
        ("blend-modes/darken.psd",),
        ("blend-modes/lighten.psd",),
        ("blend-modes/color-dodge.psd",),
        ("blend-modes/linear-dodge.psd",),
        ("blend-modes/color-burn.psd",),
        ("blend-modes/linear-burn.psd",),
        ("blend-modes/hard-light.psd",),
        ("blend-modes/soft-light.psd",),
        pytest.param(
            "blend-modes/vivid-light.psd",
            marks=pytest.mark.xfail(reason="vivid light algorithm discrepency"),
        ),
        ("blend-modes/linear-light.psd",),
        ("blend-modes/pin-light.psd",),
        ("blend-modes/difference.psd",),
        ("blend-modes/exclusion.psd",),
        ("blend-modes/subtract.psd",),
        ("blend-modes/hard-mix.psd",),
        ("blend-modes/saturation.psd",),
        ("blend-modes/divide.psd",),
        ("blend-modes/hue.psd",),
        ("blend-modes/color.psd",),
        ("blend-modes/luminosity.psd",),
        ("blend-modes/pass-through.psd",),
        # Total test
        ("blend-modes/rgb-blend-modes.psd",),
        ("blend-modes/gray-blend-modes.psd",),
    ],
)
def test_blend_quality(filename: str) -> None:
    check_composite_quality(filename, threshold=0.01)


@pytest.mark.parametrize(
    ("filename",),
    [
        ("blend-modes/dissolve.psd",),
        ("blend-modes/cmyk-blend-modes.psd",),  # Fix me!
    ],
)
@pytest.mark.xfail
def test_blend_quality_xfail(filename: str) -> None:
    check_composite_quality(filename, threshold=0.01)


@pytest.mark.parametrize(
    "property",
    [
        ("opacity"),
        ("fill_adjustment"),
        ("fill_blendmode"),
        ("clipping_mask_adjustment"),
        ("clipping_mask_blendmode"),
        ("vector_mask"),
        ("blendmodes1"),
        ("blendmodes2"),
        ("blendmodes3"),
    ],
)
def test_passthrough_properties(property) -> None:
    filename = f"passthrough_{property}"
    check_composite_quality(f"{filename}.psd", 0.001, False)


def _nested_passthrough_psd_with(
    depth: int, opacity: int, layer_alpha: int, background_alpha: int
) -> PSDImage:
    """Build ``depth`` nested pass-through groups holding a single blue layer.

    Only the innermost group carries ``opacity``; the outer ones are opaque, so
    the rendered result must not depend on ``depth``.
    """
    psd = PSDImage.new(mode="RGB", size=(8, 8))
    if background_alpha:
        psd.create_pixel_layer(
            image=Image.new("RGBA", (8, 8), (255, 0, 0, background_alpha)),
            name="Background",
        )

    parent: GroupMixin = psd
    for i in range(depth):
        group = psd.create_group(name=f"Group {i}")
        group.blend_mode = BlendMode.PASS_THROUGH
        group.opacity = opacity if i == depth - 1 else 255
        if parent is not psd:
            psd.remove(group)
            parent.append(group)
        parent = group

    blue = PixelLayer.frompil(Image.new("RGBA", (8, 8), (0, 0, 255, layer_alpha)), psd)
    blue.name = "Blue"
    parent.append(blue)
    return psd


def _nested_passthrough_psd(depth: int, opacity: int, background: bool) -> PSDImage:
    return _nested_passthrough_psd_with(
        depth, opacity, layer_alpha=128, background_alpha=255 if background else 0
    )


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_passthrough_group_opacity_over_opaque_backdrop(depth: int) -> None:
    """Group opacity must scale the effective alpha of the group's contents
    instead of blending the backdrop in twice (issue #703)."""
    psd = _nested_passthrough_psd(depth, opacity=128, background=True)
    image = psd.composite(ignore_preview=True).convert("RGB")
    pixel = tuple(np.array(image, dtype=int)[4, 4])
    # 50% layer alpha * 50% group opacity = 25% blue over red.
    assert pixel == pytest.approx((191, 0, 64), abs=2)


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_passthrough_group_opacity_over_transparent_backdrop(depth: int) -> None:
    """Without a backdrop, group opacity only scales alpha; the initial
    backdrop color must not bleed into the result (issue #703)."""
    psd = _nested_passthrough_psd(depth, opacity=128, background=False)
    image = psd.composite(ignore_preview=True).convert("RGBA")
    pixel = tuple(np.array(image, dtype=int)[4, 4])
    assert pixel == pytest.approx((0, 0, 255, 64), abs=2)


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_passthrough_group_opacity_over_partial_backdrop(depth: int) -> None:
    """The interpolation has to happen in premultiplied space, so a partially
    transparent backdrop contributes in proportion to its own alpha.

    This is the case the pre-#703 code got wrong even without nesting, because
    it keyed off ``_shape_g`` rather than the backdrop alpha.
    """
    psd = _nested_passthrough_psd_with(
        depth, opacity=128, layer_alpha=128, background_alpha=128
    )
    image = psd.composite(ignore_preview=True).convert("RGBA")
    pixel = tuple(np.array(image, dtype=int)[4, 4])
    # backdrop 0.5 red, group result 0.25 blue over it, group opacity 0.5:
    #   alpha = union(0.5, 0.5 * 0.5)   = 0.625  -> 159
    #   color = (0.375 * red + 0.25 * blue) / 0.625 = 0.6 red + 0.4 blue
    assert pixel == pytest.approx((153, 0, 102, 159), abs=2)


def _flat_psd(alpha: int, background_alpha: int) -> PSDImage:
    """The ungrouped counterpart of :py:func:`_nested_passthrough_psd`."""
    psd = PSDImage.new(mode="RGB", size=(8, 8))
    if background_alpha:
        psd.create_pixel_layer(
            image=Image.new("RGBA", (8, 8), (255, 0, 0, background_alpha)), name="BG"
        )
    psd.append(PixelLayer.frompil(Image.new("RGBA", (8, 8), (0, 0, 255, alpha)), psd))
    return psd


@pytest.mark.parametrize("depth", [1, 2, 3])
@pytest.mark.parametrize("opacity", [255, 192, 128, 64, 0])
@pytest.mark.parametrize("layer_alpha", [255, 128, 64])
@pytest.mark.parametrize("background_alpha", [255, 128, 0])
def test_passthrough_group_opacity_equivalence(
    depth: int, opacity: int, layer_alpha: int, background_alpha: int
) -> None:
    """A pass-through group at opacity ``m`` around a single normal layer at
    alpha ``a`` must render identically to that layer ungrouped at ``m * a``.

    This is the invariant issue #703 violated: group opacity has to scale the
    effective alpha of the contents rather than blend the backdrop in twice.
    """
    grouped = _nested_passthrough_psd_with(
        depth, opacity, layer_alpha, background_alpha
    )
    flat = _flat_psd(round(opacity * layer_alpha / 255.0), background_alpha)

    got = np.array(grouped.composite(ignore_preview=True).convert("RGBA"), dtype=int)
    ref = np.array(flat.composite(ignore_preview=True).convert("RGBA"), dtype=int)
    if got[4, 4, 3] == 0 and ref[4, 4, 3] == 0:
        return  # Fully transparent; the color channels are undefined.
    assert tuple(got[4, 4]) == pytest.approx(tuple(ref[4, 4]), abs=2)


NON_SEPARABLE = [hue, saturation, color, luminosity, darker_color, lighter_color]


@pytest.mark.parametrize("func", NON_SEPARABLE, ids=lambda f: f.__name__)
@pytest.mark.parametrize("channels", [1, 2, 5])
def test_non_separable_falls_back_to_normal_off_rgb(
    func: Callable, channels: int
) -> None:
    """Widths other than RGB and CMYK degrade instead of crashing (#735).

    The four component modes raised on any single-channel document -- every
    grayscale and duotone fixture that has layers::

        hue, saturation:    IndexError: boolean index did not match indexed
                            array along axis 2
        color, luminosity:  ValueError: zero-size array to reduction operation
                            minimum which has no identity

    ``darker_color`` and ``lighter_color`` did not raise, which was worse: the
    empty mask they built selected nothing, so both returned the backdrop
    untouched whatever the source was. Two and five channels -- a duotone canvas
    widened to its inks, a multichannel document with spot plates -- are broken
    too, differing only in which exception comes out and in that five channels
    raises for all six rather than silently passing the backdrop through. So
    the fallback keys on "not RGB" rather than on "single channel".

    ``normal`` is the fallback because Photoshop refuses to set any of these
    six modes on such a document, so there is no result to reproduce.
    """
    Cb = np.full((2, 2, channels), 0.4, dtype=np.float32)
    Cs = np.full((2, 2, channels), 0.6, dtype=np.float32)
    result = func(Cb, Cs)
    assert result.shape == (2, 2, channels)
    assert np.array_equal(result, normal(Cb, Cs))


@pytest.mark.parametrize("func", NON_SEPARABLE, ids=lambda f: f.__name__)
@pytest.mark.parametrize("channels", [3, 4])
def test_non_separable_still_blends_rgb_and_cmyk(
    func: Callable, channels: int, caplog: pytest.LogCaptureFixture
) -> None:
    """The fallback must not swallow the widths that do have ground truth.

    The source is brighter than the backdrop in one pixel and darker in the
    other. A spatially constant pair would not do: ``darker_color`` and
    ``lighter_color`` return one whole operand, so on constant input one of the
    two always coincides with ``normal`` and the comparison could not tell a
    real blend from the fallback.
    """
    Cb = np.full((1, 2, channels), 0.4, dtype=np.float32)
    Cs = np.full((1, 2, channels), 0.6, dtype=np.float32)
    Cs[0, 0, 0] = 0.9
    Cs[0, 1, :] = 0.1
    with caplog.at_level(logging.DEBUG, logger="psd_tools.composite.blend"):
        result = func(Cb.copy(), Cs.copy())
    assert result.shape == (1, 2, channels)
    assert not np.array_equal(result, normal(Cb, Cs))
    assert "falling back to normal" not in caplog.text


def test_non_separable_fallback_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Degrading silently would hide a mode the caller asked for (#735)."""
    Cb = np.full((2, 2, 1), 0.4, dtype=np.float32)
    Cs = np.full((2, 2, 1), 0.6, dtype=np.float32)
    with caplog.at_level(logging.DEBUG, logger="psd_tools.composite.blend"):
        luminosity(Cb, Cs)
    assert "luminosity blend is not defined for a 1-channel source" in caplog.text
