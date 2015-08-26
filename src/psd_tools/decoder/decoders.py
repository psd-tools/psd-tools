# -*- coding: utf-8 -*-
from __future__ import absolute_import
import io
import struct
from psd_tools.utils import unpack, read_unicode_string, read_pascal_string

def single_value(fmt):
    fmt_size = struct.calcsize(fmt)
    def decoder(data):
        # truncating data if it's bigger...
        return unpack(fmt, data[:fmt_size])[0]
    return decoder

def unicode_string(data):
    return read_unicode_string(io.BytesIO(data))

def pascal_string(data):
    return read_pascal_string(io.BytesIO(data))

def boolean(data):
    return bool(unpack("?", data[:1])[0])


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
