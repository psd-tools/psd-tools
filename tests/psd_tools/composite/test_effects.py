import logging

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
