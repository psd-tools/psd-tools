# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, print_function
import warnings
import io
import struct

from psd_tools.utils import read_fmt, read_pascal_string, read_unicode_string
from psd_tools.debug import pretty_namedtuple

LinkedLayerCollection = pretty_namedtuple('LinkedLayerCollection', 'linked_list ')
_LinkedLayer = pretty_namedtuple('LinkedLayer',
                               'version unique_id filename filetype creator decoded uuid')


class LinkedLayer(_LinkedLayer):

    def __repr__(self):
        return "LinkedLayer(filename='%s', size=%s)" % (self.filename, len(self.decoded))

    def _repr_pretty_(self, p, cycle):
        if cycle:
            p.text("LinkedLayer(...)")
        else:
            with p.group(1, "LinkedLayer(", ")"):
                p.breakable()
                p.text("filename='%s', ", self.filename)
                p.breakable()
                p.text("size=%s, ", len(self.decoded))
                p.breakable()
                p.text("unique_id=%s, ", self.unique_id)
                p.breakable()
                p.text("type='%s', ", self.filetype)
                p.breakable()
                p.text("creator='%s', ", self.creator)


def decode(data):
    """
    Reads and decodes info about linked layers.

    These are embedded files (embedded smart objects). But Adobe calls
    them "linked layers", so we'll follow that nomenclature. Note that
    non-embedded smart objects are not included here.
    """
    fp = io.BytesIO(data)
    position = 0
    layers = []
    while True:
        length_buf = fp.read(8)
        if not length_buf:
            break   # end of file
        length = struct.unpack('>Q', length_buf)[0]
        liFD, version = read_fmt('4s I', fp)
        if liFD != b'liFD':
            warnings.warn('unknown layer type')
            break
        unique_id = read_pascal_string(fp, 'ascii')
        filename = read_unicode_string(fp)
        filetype, creator, remaining_length, file_open_descriptor = read_fmt('4s 4s Q B', fp)
        filetype = str(filetype)
        if not file_open_descriptor:
            if remaining_length + 198 != length:
                warnings.warn('record length mismatch')
        else:
            # WTF is this, Adobe: "variable length: Descriptor of open parameters"
            warnings.warn('decoding of file open descriptor not implemented')
            size = length - remaining_length - 198 + 4   # undocumented guess
            fp.read(size)
        decoded = fp.read(remaining_length)
        uuid = read_unicode_string(fp)
        layers.append(
            LinkedLayer(version, unique_id, filename, filetype, creator, decoded, uuid)
        )
        # Each layer is padded to start at 4-byte boundary
        position += length
        pad = -position % 4
        fp.read(pad)
        position += pad
    return LinkedLayerCollection(layers)

