# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import pytest

from .utils import full_name, tobytes
from PIL import ImageMath
from psd_tools import PSDImage
from psd_tools.constants import BlendMode


DIFF_STATS_PER_MODE = (
    (True,  True,   None,   None,   None ),     # Normal
    (True,  False,  -127,   +128,   20000),     # Dissolve

    (True,  True,   None,   None,   None ),     # Darken
    (True,  True,   None,   None,   None ),     # Multiply
    (True,  True,   None,   None,   None ),     # Color Burn
    (True,  True,   None,   None,   None ),     # Linear Burn
    (False, False,  -1,     0,      1    ),     # Darker Color

    (True,  True,   None,   None,   None ),     # Lighten
    (True,  True,   None,   None,   None ),     # Screen
    (True,  True,   None,   None,   None ),     # Color Dodge
    (True,  True,   None,   None,   None ),     # Linear Dodge
    (False, True,   None,   None,   None ),     # Lighter Color

    (True,  True,   None,   None,   None ),     # Overlay
    (True,  False,  -1,     +1,     37902),     # Soft Light
    (True,  False,  0,      +1,     29706),     # Hard Light
    (True,  False,  0,      +128,   37630),     # Vivid Light
    (True,  False,  0,      +1,     20794),     # Linear Light
    (True,  False,  0,      +1,     32942),     # Pin Light
    (True,  True,   None,   None,   None ),     # Hard Mix

    (True,  True,   None,   None,   None ),     # Difference
    (True,  False,  -1,     +1,     33224),     # Exclusion
    (True,  True,   None,   None,   None ),     # Subtract
    (True,  True,   None,   None,   None ),     # Divide

    (False, False,  0,      +1,     39800),     # Hue
    (False, False,  0,      +1,     39800),     # Saturation
    (False, False,  0,      +1,     39800),     # Color
    (False, False,  -2,     0,      39909)      # Luminosity
)


def _calc_channel_diff(c1, c2):
    return ImageMath.eval('127 + c2 - c1', c1=c1, c2=c2).convert('L')

def _calc_luminance(bands):
    return ImageMath.eval(
        '(30*r + 59*g + 11*b + 50) / 100',
        r=bands[0], g=bands[1], b=bands[2]
    ).convert('L')

def _get_stat(ch):
    return dict((c, n) for n, c in ch.getcolors())

def _get_diff_channels(im1, im2):
    im1 = im1.split()[:3]
    im2 = im2.split()[:3]

    diff_bands = [x for x in map(_calc_channel_diff, im1, im2)]
    diff_stats = [x for x in map(_get_stat, diff_bands)]

    return diff_stats

def _get_diff_luminance(im1, im2):
    im1 = im1.split()
    im2 = im2.split()

    diff_lum = _calc_channel_diff(_calc_luminance(im1), _calc_luminance(im2))

    return _get_stat(diff_lum)


def test_blend_modes_basics():
    psd = PSDImage.load(full_name('blend_modes.psd'))
    composite_image = psd.as_PIL()
    merged_image = psd.as_PIL_merged()

    for i in range(27):
        is_separable  = DIFF_STATS_PER_MODE[i][0]
        is_precise    = DIFF_STATS_PER_MODE[i][1]
        deviation_neg = DIFF_STATS_PER_MODE[i][2]
        deviation_pos = DIFF_STATS_PER_MODE[i][3]
        match_count   = DIFF_STATS_PER_MODE[i][4]

        y = i // 7 * 200
        x = i % 7 * 200
        bbox = (x, y, x + 200, y + 200)

        ethalon = composite_image.crop(bbox)
        result = merged_image.crop(bbox)

        if is_separable:
            diff = _get_diff_channels(ethalon, result)

            if is_precise:
                assert len(diff[0]) == 1
                assert len(diff[1]) == 1
                assert len(diff[2]) == 1

                assert 127 in diff[0]
                assert 127 in diff[1]
                assert 127 in diff[2]
            else:
                keys_r = sorted(diff[0].keys())
                keys_g = sorted(diff[1].keys())
                keys_b = sorted(diff[2].keys())
                min_color_value = min(keys_r[ 0], keys_g[ 0], keys_b[ 0])
                max_color_value = max(keys_r[-1], keys_g[-1], keys_b[-1])

                assert max_color_value - 127 == deviation_pos
                assert min_color_value - 127 == deviation_neg

                assert diff[0][127] >= match_count
                assert diff[1][127] >= match_count
                assert diff[2][127] >= match_count
        else:
            diff = _get_diff_luminance(ethalon, result)

            if is_precise:
                assert len(diff) == 1
                assert 127 in diff
            else:
                keys = sorted(diff.keys())
                assert keys[-1] - 127 == deviation_pos
                assert keys[ 0] - 127 == deviation_neg

                assert diff[127] >= match_count


def test_blend_transparent_areas():
    psd = PSDImage.load(full_name('blend_modes2.psd'))
    composite_image = psd.as_PIL()
    merged_image = psd.as_PIL_merged()

    assert merged_image is not None
    assert tobytes(composite_image) == tobytes(merged_image)


def test_group_merging():
    psd = PSDImage.load(full_name('blend_modes3.psd'))
    composite_image = psd.as_PIL()
    merged_image = psd.as_PIL_merged()

    group_left = psd.layers[1]
    group_right = psd.layers[0]
    assert group_left.blend_mode == BlendMode.PASS_THROUGH
    assert group_right.blend_mode == BlendMode.NORMAL

    layer_left = group_left.layers[0]
    layer_right = group_right.layers[0]
    assert layer_left.blend_mode == BlendMode.DIFFERENCE
    assert layer_right.blend_mode == BlendMode.DIFFERENCE

    assert merged_image is not None
    assert tobytes(composite_image) == tobytes(merged_image)
