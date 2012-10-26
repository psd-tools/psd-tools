# -*- coding: utf-8 -*-
from __future__ import absolute_import
import io
import struct
import warnings
from psd_tools.utils import unpack, read_fmt, read_unicode_string

def single_value(fmt):
    def decoder(data):
        return unpack(fmt, data)[0]
    return decoder

def unicode_string(data):
    return read_unicode_string(io.BytesIO(data))

def boolean(fmt="?"):
    fmt_size = struct.calcsize(str(fmt))
    def decoder(data):
        return bool(single_value(fmt)(data[:fmt_size]))
    return decoder


def new_registry():
    """
    Returns an empty dict and a @register decorator
    """
    decoders = {}

    def register(key):
        def decorator(func):
            decoders[key] = func
            return func
        return decorator

    return decoders, register
