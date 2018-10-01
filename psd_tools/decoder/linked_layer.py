# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, print_function
import warnings
import io
import struct

from psd_tools.constants import LinkedLayerType
from psd_tools.utils import read_fmt, read_pascal_string, read_unicode_string
from psd_tools.debug import pretty_namedtuple
from psd_tools.decoder.actions import decode_descriptor

LinkedLayerCollection = pretty_namedtuple('LinkedLayerCollection',
                                          'linked_list ')
_LinkedLayer = pretty_namedtuple(
    'LinkedLayer',
    'type version unique_id filename filetype creator filesize '
    'file_open_descriptor linked_file_descriptor timestamp decoded '
    'child_document_id asset_mod_time asset_lock_state')


class LinkedLayer(_LinkedLayer):

    def __repr__(self):
        return "LinkedLayer(type=%s filename='%s', size=%s)" % (
            self.type, self.filename, self.filesize)

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
                p.text("size=%s, " % self.filesize)


def decode(data):
    """
    Reads and decodes info about linked layers.

    These are embedded files (embedded smart objects). But Adobe calls
    them "linked layers", so we'll follow that nomenclature.
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
        filetype, creator, datasize, have_file_open_descriptor = read_fmt(
            '4s 4s Q B', fp)
        if have_file_open_descriptor:
            # Does not seem to contain any useful information
            undocumented_integer = read_fmt("I", fp)
            file_open_descriptor = decode_descriptor(None, fp)
        else:
            file_open_descriptor = None

        linked_file_descriptor = None
        timestamp = None
        decoded = None
        file_size = None
        child_document_id = None
        asset_mod_time = None
        asset_lock_state = None

        if link_type == LinkedLayerType.EXTERNAL:
            fp.read(4)  # Undocumented zero padding
            linked_file_descriptor = decode_descriptor(None, fp)
            if version > 3:
                timestamp = read_fmt('I B B B B d', fp)
            file_size = read_fmt('Q', fp)[0]  # External file size.
            if version > 2:
                decoded = fp.read(datasize)
        elif link_type == LinkedLayerType.ALIAS:
            fp.seek(8, io.SEEK_CUR)

        if link_type == LinkedLayerType.DATA:
            decoded = fp.read(datasize)
            if len(decoded) != datasize:
                warnings.warn('failed to read linked file data (%d vs %d)' % (
                    len(decoded), datasize))

        # The following are not well documented...
        if version >= 5:
            child_document_id = read_unicode_string(fp)
        if version >= 6:
            asset_mod_time = read_fmt('d', fp)
        if version >= 7:
            asset_lock_state = read_fmt('B', fp)
        if link_type == LinkedLayerType.EXTERNAL and version == 2:
            decoded = fp.read(datasize)

        layers.append(
            LinkedLayer(
                link_type, version, unique_id, filename, filetype, creator,
                file_size if file_size else datasize, file_open_descriptor,
                linked_file_descriptor, timestamp, decoded, child_document_id,
                asset_mod_time, asset_lock_state)
        )
        # Gobble up anything that we don't know how to decode
        # first 8 bytes contained the length
        expected_position = start + 8 + length
        current_position = fp.tell()
        if expected_position != current_position:
            warnings.warn(
                'skipping over undocumented additional fields (%d vs %d)' % (
                    current_position, expected_position))
            fp.read(expected_position - current_position)
        # Each layer is padded to start and end at 4-byte boundary
        pad = -fp.tell() % 4
        fp.read(pad)

    return LinkedLayerCollection(layers)
