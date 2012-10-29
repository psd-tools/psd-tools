# -*- coding: utf-8 -*-
from __future__ import absolute_import
import psd_tools.reader
import psd_tools.decoder

from .layers import group_layers

def parse(filename):
    with open(filename, 'rb') as f:
        decoded_data = psd_tools.decoder.parse(
            psd_tools.reader.parse(f)
        )
    return decoded_data


