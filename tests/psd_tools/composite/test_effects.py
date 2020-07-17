import pytest
import logging

from .test_composite import check_composite_quality

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(("filename", ), [
    ('effects/stroke-effects.psd', ),
    ('effects/shape-fx2.psd', ),
    ('effects/stroke-effect-transparent-shape.psd', ),
])
@pytest.mark.xfail
def test_stroke_effects(filename):
    err = check_composite_quality(filename, threshold=0.01)


@pytest.mark.parametrize(("filename", ), [
    ('effects/shape-fx.psd', ),
])
def test_effects_disabled(filename):
    check_composite_quality(filename, threshold=0.01)
