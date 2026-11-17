import numpy as np
import pytest

from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import Tag

from ..utils import full_name

pytest.importorskip("scipy")
pytest.importorskip("aggdraw")

# A 60..140 square on a 200x200 canvas, centre-stroked 6 units wide.
POINTS_PER_INCH = 72
DPI = 300
WIDTH = 6
# Photoshop's pen edge differs from aggdraw's by a fraction of a pixel's coverage.
EDGE_TOLERANCE = 12


def _render(name: str, width_scale: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    psd = PSDImage.open(full_name(name))
    if width_scale != 1.0:
        data = psd[-1].tagged_blocks.get_data(Tag.VECTOR_STROKE_DATA)
        data[b"strokeStyleLineWidth"].value *= width_scale
    preview = psd.topil()
    redrawn = psd.composite(force=True, ignore_preview=True)
    assert preview is not None and redrawn is not None
    return (
        np.asarray(preview.convert("RGB"), dtype=np.int16),
        np.asarray(redrawn.convert("RGB"), dtype=np.int16),
    )


def _stroke_px(image: np.ndarray) -> float:
    """Stroke thickness on the middle row left of the square, as coverage."""
    row = image[100, :100]
    return float(((255 - row[:, 1]) / 255).sum())


@pytest.mark.parametrize(
    "name, expected_px",
    [
        ("effects/stroke-width-points-300dpi.psd", WIDTH * DPI / POINTS_PER_INCH),
        ("effects/stroke-width-pixels-300dpi.psd", WIDTH),
    ],
)
def test_a_stroke_width_is_drawn_in_its_own_unit(name: str, expected_px: float) -> None:
    """Photoshop's preview is 6 pt at 300 dpi, drawn 25 px wide, and 6 px at 6 px.

    The width widens the render, so a fixture whose stroke fell off-canvas
    could not pass.
    """
    preview, rendered = _render(name)
    assert _stroke_px(preview) == pytest.approx(expected_px, abs=0.5)
    assert np.abs(rendered - preview).max() <= EDGE_TOLERANCE

    _, wider = _render(name, width_scale=2.0)
    assert _stroke_px(wider) > _stroke_px(rendered) + 1
