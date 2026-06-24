import logging
import sys

import numpy as np
import pytest

from psd_tools import PSDImage
from psd_tools.composite import composite
from psd_tools.composite.effects import draw_drop_shadow, draw_outer_glow

from ..utils import full_name
from .test_composite import _mse, check_composite_quality

logger = logging.getLogger(__name__)


def _disc_shape(w, h, cx, cy, rad):
    """A (h, w, 1) float32 silhouette: 1.0 inside a disc, else 0."""
    yy, xx = np.mgrid[0:h, 0:w]
    disc = ((xx - cx) ** 2 + (yy - cy) ** 2 <= rad**2).astype(np.float32)
    return disc[:, :, None]


def _centroid(mask):
    m = mask[:, :, 0]
    yy, xx = np.mgrid[0 : m.shape[0], 0 : m.shape[1]]
    total = m.sum()
    return (xx * m).sum() / total, (yy * m).sum() / total


# ── Drop shadow / outer glow renderers (unit, synthetic) ────────────────────── #


def test_draw_drop_shadow_casts_opposite_to_light():
    """A 30deg light casts the shadow down-left (image coords, y-down)."""
    w = h = 200
    shape = _disc_shape(w, h, 100, 100, 30)
    mask = draw_drop_shadow(
        (0, 0, w, h), shape, distance=20, angle=30, size=1.0, choke=0
    )
    cx, cy = _centroid(mask)
    assert cx < 100 - 5, f"shadow not cast left: cx={cx}"
    assert cy > 100 + 5, f"shadow not cast down: cy={cy}"


def test_draw_drop_shadow_blur_softens_and_spreads():
    """A larger size produces a softer, wider shadow (partial coverage spreads out)."""
    w = h = 200
    shape = _disc_shape(w, h, 100, 100, 30)
    hard = draw_drop_shadow((0, 0, w, h), shape, distance=0, angle=0, size=0, choke=0)
    soft = draw_drop_shadow((0, 0, w, h), shape, distance=0, angle=0, size=18, choke=0)
    soft_partial = ((soft[:, :, 0] > 0.05) & (soft[:, :, 0] < 0.95)).sum()
    hard_partial = ((hard[:, :, 0] > 0.05) & (hard[:, :, 0] < 0.95)).sum()
    assert soft_partial > hard_partial + 200, "size did not soften the shadow edge"
    assert (soft[:, :, 0] > 0.05).sum() > (shape[:, :, 0] > 0.5).sum() + 200, (
        "blur did not spread the shadow footprint"
    )


def test_draw_drop_shadow_choke_tightens_matte():
    """Choke (a percent of size) erodes the matte before blur, shrinking coverage."""
    w = h = 200
    shape = _disc_shape(w, h, 100, 100, 40)
    loose = draw_drop_shadow((0, 0, w, h), shape, distance=0, angle=0, size=20, choke=0)
    tight = draw_drop_shadow(
        (0, 0, w, h), shape, distance=0, angle=0, size=20, choke=80
    )
    assert (tight[:, :, 0] > 0.5).sum() < (loose[:, :, 0] > 0.5).sum() - 200, (
        "choke did not tighten the matte"
    )


def test_draw_outer_glow_spreads_symmetrically_no_offset():
    """Outer glow has no light/offset — its halo stays centered on the silhouette."""
    w = h = 200
    shape = _disc_shape(w, h, 100, 100, 30)
    mask = draw_outer_glow((0, 0, w, h), shape, size=14, spread=0)
    cx, cy = _centroid(mask)
    assert abs(cx - 100) < 2 and abs(cy - 100) < 2, f"glow off-centre: ({cx}, {cy})"
    assert (mask[:, :, 0] > 0.05).sum() > (shape[:, :, 0] > 0.5).sum() + 200, (
        "glow did not spread a soft halo beyond the silhouette"
    )


def test_draw_outer_glow_spread_dilates_footprint():
    """A nonzero spread grows the glow outward (dilation), unlike a shadow's choke."""
    w = h = 200
    shape = _disc_shape(w, h, 100, 100, 30)
    tight = draw_outer_glow((0, 0, w, h), shape, size=14, spread=0)
    wide = draw_outer_glow((0, 0, w, h), shape, size=14, spread=80)
    assert (wide[:, :, 0] > 0.5).sum() > (tight[:, :, 0] > 0.5).sum() + 200, (
        "spread did not dilate the glow outward"
    )


def _shadow_zone_mse(psd, ref):
    """MSE of a force=True recomposite vs the baked preview, restricted to the
    drop-shadow layer's neighbourhood in ``layer_effects.psd``."""
    color, _, _ = composite(psd, force=True)
    # The "Drop Shadow" text layer sits at bbox (99, 225, 564, 284); its cast shadow
    # falls just around/below it, clear of the neighbouring effect demos.
    crop = (slice(220, 296), slice(60, 580))
    return _mse(ref[crop], color[crop])


def test_drop_shadow_improves_composite_fidelity(monkeypatch):
    """Rendering the drop shadow moves the force=True composite closer to Photoshop's
    baked preview than a no-op shadow renderer does (falsifiable: a zero renderer ties)."""
    # The package __init__ re-exports the composite() function, shadowing the submodule
    # attribute, so reach the real module (where _apply_drop_shadow looks up the name).
    composite_mod = sys.modules["psd_tools.composite.composite"]

    psd = PSDImage.open(full_name("layer_effects.psd"))
    ref = psd.numpy()[:, :, :3]

    def _noop(viewport, shape, **kwargs):
        h, w = viewport[3] - viewport[1], viewport[2] - viewport[0]
        return np.zeros((h, w, 1), dtype=np.float32)

    monkeypatch.setattr(composite_mod, "draw_drop_shadow", _noop)
    mse_noop = _shadow_zone_mse(psd, ref)
    monkeypatch.undo()
    mse_real = _shadow_zone_mse(psd, ref)

    assert mse_real < mse_noop, (
        f"drop shadow did not improve fidelity: real={mse_real:.5f} noop={mse_noop:.5f}"
    )


def _glow_zone_mse(psd, ref):
    """MSE of a force=True recomposite vs the baked preview, restricted to the
    outer-glow layer's neighbourhood in ``layer_effects.psd``."""
    color, _, _ = composite(psd, force=True)
    # The "Outer Glow" layer sits at bbox (99, 98, 498, 146); crop its body + halo,
    # clear of the bevel row above (y<81) and the inner-glow demo below (y>=164).
    crop = (slice(95, 160), slice(55, 545))
    return _mse(ref[crop], color[crop])


def test_outer_glow_improves_composite_fidelity(monkeypatch):
    """Rendering the outer glow moves the force=True composite closer to Photoshop's
    baked preview than a no-op renderer does (falsifiable: a zero renderer ties)."""
    composite_mod = sys.modules["psd_tools.composite.composite"]

    psd = PSDImage.open(full_name("layer_effects.psd"))
    ref = psd.numpy()[:, :, :3]

    def _noop(viewport, shape, **kwargs):
        h, w = viewport[3] - viewport[1], viewport[2] - viewport[0]
        return np.zeros((h, w, 1), dtype=np.float32)

    monkeypatch.setattr(composite_mod, "draw_outer_glow", _noop)
    mse_noop = _glow_zone_mse(psd, ref)
    monkeypatch.undo()
    mse_real = _glow_zone_mse(psd, ref)

    assert mse_real < mse_noop, (
        f"outer glow did not improve fidelity: real={mse_real:.5f} noop={mse_noop:.5f}"
    )


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
