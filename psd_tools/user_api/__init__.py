# -*- coding: utf-8 -*-
from __future__ import absolute_import
import psd_tools.reader
import psd_tools.decoder

def parse(filename):
    with open(filename, 'rb') as f:
        raw_data = psd_tools.decoder.parse(
            psd_tools.reader.parse(f)
        )

    return raw_data


