# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, division
import logging

import psd_tools.reader.header
import psd_tools.reader.color_mode_data
import psd_tools.reader.image_resources
import psd_tools.reader.layers
from psd_tools.debug import pretty_namedtuple

logger = logging.getLogger(__name__)

ParseResult = pretty_namedtuple(
    'ParseResult',
    'header, color_data, image_resource_blocks, layer_and_mask_data, image_data'
)

def parse(fp, encoding='utf8'):

    header = psd_tools.reader.header.read(fp)
    return ParseResult(
        header,
        psd_tools.reader.color_mode_data.read(fp),
        psd_tools.reader.image_resources.read(fp, encoding),
        psd_tools.reader.layers.read(fp, encoding, header.depth),
        psd_tools.reader.layers.read_image_data(fp, header)
    )
