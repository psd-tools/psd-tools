import logging

import numpy as np
import pytest

from psd_tools.api.psd_image import PSDImage

from ..utils import full_name
from .test_composite import check_composite_quality

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    ("filename",),
    [
        ("effects/stroke-effects.psd",),
        ("effects/shape-fx2.psd",),
        ("effects/stroke-effect-transparent-shape.psd",),
        ("effects/double-stroke-effects.psd",),
    ],
)
@pytest.mark.xfail
def test_stroke_effects_xfail(filename: str) -> None:
    check_composite_quality(filename, threshold=0.01)


@pytest.mark.parametrize(
    ("filename",),
    [
        ("effects/shape-fx.psd",),
    ],
)
def test_effects_disabled(filename: str) -> None:
    check_composite_quality(filename, threshold=0.01)


def test_outside_stroke_reaches_outside_bbox() -> None:
    """An outset stroke is drawn outside the layer it outlines (#792).

    ``outside-stroke.psd`` is a 16x16 pixel square whose content fills its
    bounding box exactly, with a 3 px outset stroke -- so the entire stroke
    falls outside the box, and drawing it on the box alone loses all of it.
    The alpha bounds are asserted rather than only the error, because a stroke
    dropped in full and a stroke merely mis-shaded both raise the error while
    only the former moves the bounds.
    """
    psd = PSDImage.open(full_name("effects/outside-stroke.psd"))
    assert psd[0].bbox == (8, 8, 24, 24)
    # Photoshop's own preview of this file, i.e. the 3 px stroke on every side.
    expected = (5, 5, 27, 27)
    preview = psd.topil()
    assert preview is not None
    assert preview.getchannel("A").getbbox() == expected
    composited = psd.composite(ignore_preview=True)
    assert composited is not None
    assert composited.getchannel("A").getbbox() == expected
    check_composite_quality("effects/outside-stroke.psd", threshold=0.01)


def test_outside_stroke_fills_expanded_viewport() -> None:
    """An explicitly widened viewport receives the stroke, not just padding.

    This is the shape the report took: growing the viewport used to add
    transparent margin and nothing else, because the stroke was drawn on the
    layer's bounding box no matter how much room the viewport offered.
    """
    psd = PSDImage.open(full_name("effects/outside-stroke.psd"))
    layer = psd[0]
    left, top, right, bottom = layer.bbox
    padding = 3
    image = layer.composite(
        viewport=(left - padding, top - padding, right + padding, bottom + padding)
    )
    assert image is not None
    assert image.size == (22, 22)
    assert image.getchannel("A").getbbox() == (0, 0, 22, 22)


# How far a centered stroke of each nominal size reaches outside the layer, read
# off Photoshop's own render of ``center-stroke-sizes.psd``. The progression is
# ceil(size / 2), which is what makes it a formula rather than one measurement:
# an implementation that truncated instead reached 1 px for every odd size.
_CENTERED_REACH = {1: 1, 2: 1, 3: 2, 5: 3, 7: 4}


def _outward_reach(
    alpha: np.ndarray, bbox: tuple[int, int, int, int]
) -> tuple[int, int, int, int]:
    """How far non-zero alpha extends past ``bbox``, per side."""
    left, top, right, bottom = bbox
    pad = 12
    region = alpha[top - pad : bottom + pad, left - pad : right + pad]
    ys, xs = np.nonzero(region)
    return (
        int(pad - xs.min()),
        int(pad - ys.min()),
        int(xs.max() + 1 - (pad + right - left)),
        int(ys.max() + 1 - (pad + bottom - top)),
    )


def test_centered_stroke_reach_matches_photoshop() -> None:
    """A centered stroke straddles the layer edge as far as Photoshop's (#792).

    ``center-stroke-sizes.psd`` holds five squares carrying centered strokes of
    1, 2, 3, 5 and 7 px. Every side of every square is checked against the same
    measurement taken from Photoshop's own render of the file, so this pins the
    whole progression rather than a single size -- the defect it covers was a
    truncated dilation radius, which was correct at 1, 2 and 4 px and wrong at
    every odd size above.
    """
    psd = PSDImage.open(full_name("effects/center-stroke-sizes.psd"))
    preview = psd.topil()
    composited = psd.composite(ignore_preview=True)
    assert preview is not None and composited is not None
    reference = np.asarray(preview.convert("RGBA"), dtype=np.uint8)[:, :, 3]
    result = np.asarray(composited.convert("RGBA"), dtype=np.uint8)[:, :, 3]

    measured = {}
    for layer in psd:
        strokes = list(layer.effects.find("stroke"))
        if not strokes:  # The empty layer the document was created with.
            continue
        # Effects.find() is typed as the base _Effect; ``size`` lives on the
        # concrete Stroke class it actually returns.
        size = int(getattr(strokes[0], "size"))
        expected = _outward_reach(reference, layer.bbox)
        assert expected == (_CENTERED_REACH[size],) * 4, (
            f"Photoshop's own render of the {size} px stroke moved"
        )
        assert _outward_reach(result, layer.bbox) == expected, (
            f"{size} px centered stroke does not reach as far as Photoshop's"
        )
        measured[size] = expected[0]
    assert measured == _CENTERED_REACH

    check_composite_quality("effects/center-stroke-sizes.psd", threshold=0.01)
