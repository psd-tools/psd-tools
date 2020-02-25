import pytest
import logging

from .test_composite import check_composite_quality

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(("filename", ), [
    ('effects/stroke-effects.psd', ),
])
@pytest.mark.xfail  # TODO: Fix me!
def test_stroke_effects(filename):
    check_composite_quality(filename, threshold=0.1)


@pytest.mark.parametrize(("filename", ), [
    ('effects/shape-fx.psd', ),
])
def test_effects_disabled(filename):
    check_composite_quality(filename, threshold=0.01)
