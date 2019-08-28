from __future__ import absolute_import, unicode_literals
import pytest
import logging
import colorsys
import numpy as np
import os
from psd_tools.composer.blend import rgb_to_hls, hls_to_rgb

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
    ('blend-modes/saturation.psd', ),
])
def test_blend_quality(filename):
    test_compose_quality(filename, threshold=0.02)


@pytest.mark.parametrize(("filename", ), [
    ('blend-modes/divide.psd', ),
    ('blend-modes/hue.psd', ),
    ('blend-modes/color.psd', ),
    ('blend-modes/luminosity.psd', ),
])
@pytest.mark.xfail
def test_blend_quality_xfail(filename):
    test_compose_quality(filename, threshold=0.02)


def test_pass_through_blend():
    test_compose_quality('blend-modes/pass-through.psd')


def test_rgb_to_hls():
    r = np.random.rand(10, 10)
    g = np.random.rand(10, 10)
    b = np.random.rand(10, 10)
    r[0, 0] = 0.
    g[0, 0] = 0.
    b[0, 0] = 0.
    hls = rgb_to_hls(np.stack((r, g, b), axis=2))
    ref = np.vectorize(colorsys.rgb_to_hls)(r, g, b)
    for i in range(3):
        assert np.allclose(hls[i], ref[i])


def test_hls_to_rgb():
    h = np.random.rand(10, 10)
    l = np.random.rand(10, 10)
    s = np.random.rand(10, 10)
    s[0, 0] = 0.
    rgb = hls_to_rgb(h, l, s)
    ref = np.vectorize(colorsys.hls_to_rgb)(h, l, s)
    for i in range(3):
        assert np.allclose(rgb[:, :, i], ref[i])
