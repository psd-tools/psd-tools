# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import warnings
from collections import namedtuple

from psd_tools.utils import read_fmt
from psd_tools.constants import ColorSpaceID

_Color = namedtuple('Color', 'color_space_id color_data')


class Color(_Color):

    def __repr__(self):
        return "Color(id=%s %s, %s)" % (
            self.color_space_id, ColorSpaceID.name_of(self.color_space_id),
            self.color_data
        )


def decode_color(fp):
    color_space_id = read_fmt("H", fp)[0]

    if not ColorSpaceID.is_known(color_space_id):
        warnings.warn("Unknown color space (%s)" % color_space_id)

    if color_space_id == ColorSpaceID.LAB:
        color_data = read_fmt("4h", fp)
    else:
        color_data = read_fmt("4H", fp)
    return Color(color_space_id, color_data)
