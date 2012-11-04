# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import logging
import collections
import warnings

from psd_tools.exceptions import Error
from psd_tools.utils import read_fmt
from psd_tools.constants import ColorMode

logger = logging.getLogger(__name__)

_PsdHeader = collections.namedtuple("PsdHeader", "number_of_channels, height, width, depth, color_mode")

class PsdHeader(_PsdHeader):
    def __repr__(self):
        return "PsdHeader(number_of_channels=%s, height=%s, width=%s, depth=%s, color_mode=%s)" % (
            self.number_of_channels, self.height, self.width, self.depth,
            ColorMode.name_of(self.color_mode)
        )

def read(fp):
    """
    Reads PSD file header.
    """
    logger.debug("reading header..")
    signature = fp.read(4)
    if signature != b'8BPS':
        raise Error("This is not a PSD file")

    version = read_fmt("H", fp)[0]
    if version != 1:
        raise Error("Unsupported PSD version (%s)" % version)

    header = PsdHeader(*read_fmt("6x HIIHH", fp))

    if not ColorMode.is_known(header.color_mode):
        warnings.warn("Unknown color mode: %s" % header.color_mode)

    logger.debug(header)
    return header
