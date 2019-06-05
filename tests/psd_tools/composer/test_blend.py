from __future__ import absolute_import, unicode_literals
import pytest
import logging

from ..utils import full_name
from .test_composer import test_compose_quality

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
])
def test_blend_quality(filename):
    test_compose_quality(filename, threshold=0.02)


def test_pass_through_blend():
    test_compose_quality('blend-modes/pass-through.psd')
