import pytest
import logging

from .test_composite import check_composite_quality

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(("filename", ), [
    ('blend-modes/normal.psd', ),
    ('blend-modes/multiply.psd', ),
    ('blend-modes/screen.psd', ),
    ('blend-modes/overlay.psd', ),
    ('blend-modes/darken.psd', ),
    ('blend-modes/lighten.psd', ),
    ('blend-modes/color-dodge.psd', ),
    ('blend-modes/linear-dodge.psd', ),
    ('blend-modes/color-burn.psd', ),
    ('blend-modes/linear-burn.psd', ),
    ('blend-modes/hard-light.psd', ),
    ('blend-modes/soft-light.psd', ),
    ('blend-modes/vivid-light.psd', ),
    ('blend-modes/linear-light.psd', ),
    ('blend-modes/pin-light.psd', ),
    ('blend-modes/difference.psd', ),
    ('blend-modes/exclusion.psd', ),
    ('blend-modes/subtract.psd', ),
    ('blend-modes/hard-mix.psd', ),
    ('blend-modes/saturation.psd', ),
    ('blend-modes/divide.psd', ),
    ('blend-modes/hue.psd', ),
    ('blend-modes/color.psd', ),
    ('blend-modes/luminosity.psd', ),
    ('blend-modes/pass-through.psd', ),
    # Total test
    ('blend-modes/rgb-blend-modes.psd', ),
    ('blend-modes/gray-blend-modes.psd', ),
])
def test_blend_quality(filename):
    check_composite_quality(filename, threshold=0.01)


@pytest.mark.parametrize(("filename", ), [
    ('blend-modes/dissolve.psd', ),
    ('blend-modes/cmyk-blend-modes.psd', ),  # Fix me!
])
@pytest.mark.xfail
def test_blend_quality_xfail(filename):
    check_composite_quality(filename, threshold=0.01)
