# -*- coding: utf-8 -*-
"""
Module for decoding path resource.
"""
from __future__ import absolute_import, unicode_literals
import warnings

import io
from psd_tools.utils import read_fmt
from psd_tools.constants import PathResource


# Path points are 8 bits + 24 bits fixed points. Convert to float here.
def _decode_fixed_point(fixed_point):
    return tuple(float(x) / 0x01000000 for x in fixed_point)


def decode_path_resource(data):
    fp = io.BytesIO(data)
    path = []
    path_rec = len(data) // 26
    while path_rec > 0:
        selector, = read_fmt("H", fp)
        record = {"selector": selector}
        if selector in (
            PathResource.CLOSED_SUBPATH_LENGTH_RECORD,
            PathResource.OPEN_SUBPATH_LENGTH_RECORD
        ):
            record["num_knot_records"], = read_fmt("H", fp)
            fp.seek(22, io.SEEK_CUR)
        elif selector in (
                PathResource.CLOSED_SUBPATH_BEZIER_KNOT_LINKED,
                PathResource.CLOSED_SUBPATH_BEZIER_KNOT_UNLINKED,
                PathResource.OPEN_SUBPATH_BEZIER_KNOT_LINKED,
                PathResource.OPEN_SUBPATH_BEZIER_KNOT_UNLINKED):
            record["control_preceding_knot"] = _decode_fixed_point(
                read_fmt("2i", fp))
            record["anchor"] = _decode_fixed_point(read_fmt("2i", fp))
            record["control_leaving_knot"] = _decode_fixed_point(
                read_fmt("2i", fp))
        elif selector == PathResource.PATH_FILL_RULE_RECORD:
            fp.seek(24, io.SEEK_CUR)
        elif selector == PathResource.CLIPBOARD_RECORD:
            record["top"], record["left"], record["bottom"], record["right"],
            record["resolution"] = _decode_fixed_point(read_fmt("5i", fp))
            fp.seek(4, io.SEEK_CUR)
        elif selector == PathResource.INITIAL_FILL_RULE_RECORD:
            record["initial_fill_rule"], = read_fmt("H", fp)
            fp.seek(22, io.SEEK_CUR)
        else:
            warnings.warn("Unknown path record found %s" % (selector))
        path.append(record)
        path_rec -= 1
    return path
