"""Helpers shared by the compositor's tests."""

import numpy as np

from psd_tools.composite.composite import Compositor, _EffectCanvas, _Source
from psd_tools.constants import Knockout


def opaque_effect_canvas(compositor: Compositor) -> _EffectCanvas:
    """An effect canvas over a source that covers the whole viewport.

    An effect is composited into the layer it belongs to rather than onto the
    canvas, so reaching one directly takes a layer to compose it into. This is
    the simplest there is: opaque everywhere, one channel of white, so what
    comes back out of :py:meth:`_EffectCanvas.source` is the effect alone
    wherever it covers.
    """
    ones = np.ones((compositor.height, compositor.width, 1), dtype=np.float32)
    source = _Source(
        color=ones,
        shape=ones,
        alpha=ones,
        mask=1.0,
        shape_mask=1.0,
        fill_opacity=1.0,
        opacity=1.0,
        knockout=Knockout.NONE,
        adjustment_isolated=None,
        knockout_shape=ones,
    )
    return _EffectCanvas(compositor, source)
