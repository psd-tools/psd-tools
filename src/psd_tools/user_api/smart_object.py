# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, division

import os
import logging
from psd_tools.constants import LinkedLayerType


class SmartObject(object):
    """Embedded smart object."""

    def __init__(self, linked_layer):
        self._linked_layer = linked_layer

    @property
    def kind(self):
        """Kind of the object, one of `data`, `external`, `alias`."""
        return LinkedLayerType.human_name_of(self._linked_layer.type)

    @property
    def filename(self):
        """Original file name of the object."""
        return self._linked_layer.filename.strip("\0x0")

    @property
    def data(self):
        """Embedded file content, or empty if kind is `external` or `alias`"""
        return self._linked_layer.decoded

    @property
    def unique_id(self):
        """UUID of the object."""
        return self._linked_layer.unique_id

    @property
    def filesize(self):
        """File size of the object."""
        return self._linked_layer.filesize

    def preferred_extension(self):
        """Preferred file extension, such as `jpg`."""
        return self._linked_layer.filetype.lower().strip()

    def is_psd(self):
        """Return True if the file is embedded PSD/PSB."""
        return self.preferred_extension() in (b"8bpb", b"8bps")

    def save(self, filename=None):
        """
        Save the embedded file.

        :param filename: File name to export. If None, use the embedded name.
        """
        if filename is None:
            filename = self.filename
        with open(filename, 'wb') as f:
            f.write(self.data)

    def __repr__(self):
        return "<%r, type=%s, %s bytes>" % (
            self.filename, self.kind, len(self.data))
