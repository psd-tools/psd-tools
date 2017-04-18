# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, print_function
import warnings
import io
import struct

from psd_tools.utils import read_fmt, read_pascal_string, read_unicode_string
from psd_tools.debug import pretty_namedtuple
from psd_tools.decoder.actions import decode_descriptor

LinkedLayerCollection = pretty_namedtuple('LinkedLayerCollection', 'linked_list ')
_LinkedLayer = pretty_namedtuple(
    'LinkedLayer',
    'type version unique_id filename filetype creator file_open_descriptor '
    'linked_file_descriptor timestamp decoded child_document_id asset_mod_time '
    'asset_lock_state')


class LinkedLayer(_LinkedLayer):

    def __repr__(self):
        return "LinkedLayer(filename='%s', size=%s)" % (self.filename, len(self.decoded))

    def _repr_pretty_(self, p, cycle):
        if cycle:
            p.text("LinkedLayer(...)")
        else:
            with p.group(1, "LinkedLayer(", ")"):
                p.breakable()
                p.text("type='%s', " % self.type)
                p.breakable()
                p.text("version='%s', " % self.version)
                p.breakable()
                p.text("unique_id=%s, " % self.unique_id)
                p.breakable()
                p.text("filename='%s', " % self.filename)
                p.breakable()
                p.text("filetype='%s', " % self.filetype)
                p.breakable()
                p.text("creator='%s', " % self.creator)
                p.breakable()
                p.text("size=%s, " % len(self.decoded))


def decode(data):
    """
    Reads and decodes info about linked layers.

    These are embedded files (embedded smart objects). But Adobe calls
    them "linked layers", so we'll follow that nomenclature. Note that
    non-embedded smart objects are not included here.
    """
    fp = io.BytesIO(data)
    layers = []
    while True:
        start = fp.tell()
        length_buf = fp.read(8)
        if not length_buf:
            break   # end of file
        length = struct.unpack(str('>Q'), length_buf)[0]
        link_type, version = read_fmt('4s I', fp)
        if link_type not in (b'liFD', b'liFE', b'liFA'):
            warnings.warn('unknown layer type')
            break
        if version < 1 or 7 < version:
            warnings.warn('unsupported linked layer version (%s)' % version)
            break

        unique_id = read_pascal_string(fp, 'ascii')
        filename = read_unicode_string(fp)
        filetype, creator, filelength, have_file_open_descriptor = read_fmt('4s 4s Q B', fp)
        filetype = str(filetype)
        if have_file_open_descriptor:
            # Does not seem to contain any useful information
            undocumented_integer = read_fmt("I", fp)
            file_open_descriptor = decode_descriptor(None, fp)
        else:
            file_open_descriptor = None

        linked_file_descriptor = None
        timestamp = None
        file_data = None
        child_document_id = None
        asset_mod_time = None
        asset_lock_state = None

        if link_type == b'liFE':
            linked_file_descriptor = decode_descriptor(None, fp)
            if version > 3:
                timestamp = read_fmt('I B B B B d', fp)
            file_size, = read_fmt('Q', fp)
            if version > 2:
                file_data = fp.read(file_size)
        elif link_type == b'liFA':
            fp.seek(8, io.SEEK_CUR)

        if link_type == b'liFD':
            file_data = fp.read(filelength)
            if len(file_data) == filelength:
                warnings.warn('failed to read linked file data')

        # The following are not well documented...
        if version >= 5:
            child_document_id = read_unicode_string(fp)
        if version >= 6:
            asset_mod_time = read_fmt('d', fp)
        if version >= 7:
            asset_lock_state = read_fmt('B', fp)

        # if link_type == b'liFE' and version == 2:
        #     file_data = fp.read()

        layers.append(
            LinkedLayer(link_type, version, unique_id, filename, filetype,
                creator, file_open_descriptor, linked_file_descriptor,
                timestamp, file_data, child_document_id, asset_mod_time,
                asset_lock_state)
        )
        # Gobble up anything that we don't know how to decode
        expected_position = start + 8 + length      # first 8 bytes contained the length
        if expected_position != fp.tell():
            warnings.warn('skipping over undocumented additional fields')
            fp.read(expected_position - fp.tell())
        # Each layer is padded to start and end at 4-byte boundary
        pad = -fp.tell() % 4
        fp.read(pad)
    return LinkedLayerCollection(layers)

