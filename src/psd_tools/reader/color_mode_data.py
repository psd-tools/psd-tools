# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, division
import logging
from psd_tools.utils import read_fmt

logger = logging.getLogger(__name__)

def read(fp):
    """
    Reads data from the color mode data section.

    For indexed color images the data is the color table
    for the image in a non-interleaved order.

    Duotone images also have this data, but the data format is undocumented.
    """
    logger.debug("reading color mode data..")
    length = read_fmt("I", fp)[0]
    data = fp.read(length)
    return data
