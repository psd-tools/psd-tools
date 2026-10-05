import numpy as np
import pytest

from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import BlendMode

from ..utils import full_name

pytest.importorskip("scipy")


def test_a_vector_stroke_ignores_its_blend_mode() -> None:
    """A centred red stroke set to Multiply, over a fill and a gradient (#940).

    The fixture is Photoshop's own save, so its preview is the render the
    redrawn stroke is held to: Multiply would darken the band against the
    fill inside the path and against the backdrop outside it.
    """
    psd = PSDImage.open(full_name("effects/stroke-blend-mode.psd"))
    layer = next(x for x in psd if x.name == "Plain")
    assert layer.stroke is not None
    assert layer.stroke.blend_mode is BlendMode.MULTIPLY

    preview = psd.topil()
    redrawn = psd.composite(force=True, ignore_preview=True)
    assert preview is not None and redrawn is not None
    expected = np.asarray(preview.convert("RGB"), dtype=np.int16)
    rendered = np.asarray(redrawn.convert("RGB"), dtype=np.int16)

    # Mid-height row through the band: outside the path, then inside it.
    row = expected.shape[0] * 70 // 256
    assert np.abs(rendered[row, 12:36] - expected[row, 12:36]).max() <= 1
