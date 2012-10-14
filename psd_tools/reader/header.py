# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import logging
import collections

from psd_tools.exceptions import Error
from psd_tools.utils import read_fmt
from psd_tools.constants import ColorMode

logger = logging.getLogger(__name__)

Header = collections.namedtuple("PsdHeader", "number_of_channels, height, width, depth, color_mode")

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

    header = Header(*read_fmt("6x HIIHH", fp))

    if not ColorMode.is_known(header.color_mode):
        raise Error("Unknown color mode: %s" % header.color_mode)

    logger.debug(header)
    return header
