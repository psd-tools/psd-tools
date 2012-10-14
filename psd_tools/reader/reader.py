# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, division
import logging

import psd_tools.reader.header
import psd_tools.reader.color_mode_data
import psd_tools.reader.image_resources
import psd_tools.reader.layers

logger = logging.getLogger(__name__)

def parse(fp, encoding='latin1'):
    header = psd_tools.reader.header.read(fp)
    color_data = psd_tools.reader.color_mode_data.read(fp)
    image_resource_blocks = psd_tools.reader.image_resources.read(fp, encoding)
    layer_and_mask_info = psd_tools.reader.layers.read(fp, encoding)
    image_data = psd_tools.reader.layers.read_image_data(fp, header)

    return header, color_data, image_resource_blocks, layer_and_mask_info, image_data

