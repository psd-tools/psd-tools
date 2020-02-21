import pytest
import logging

from .test_composite import test_composite_quality

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(("filename", ), [
    ('effects/stroke-effects.psd', ),
])
@pytest.mark.xfail  # TODO: Fix me!
def test_stroke_effects(filename):
    test_composite_quality(filename, threshold=0.1)
