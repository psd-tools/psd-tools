# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import os
import psd_tools.reader
import psd_tools.decoder

DATA_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'psd_files')

def full_name(filename):
    return os.path.join(DATA_PATH, filename)

def load_psd(filename):
    with open(full_name(filename), 'rb') as f:
        return psd_tools.reader.parse(f)

def decode_psd(filename):
    return psd_tools.decoder.parse(load_psd(filename))