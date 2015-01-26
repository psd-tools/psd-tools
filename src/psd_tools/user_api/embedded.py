# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, division

import os
import logging
import contextlib


class Embedded(object):
    """Embedded Smart Object"""

    def __repr__(self):
        return "<psd_tools.Embedded: %s, %s bytes>" % (
            self.filename,
            len(self.data)
        )

    def __init__(self, linked_layer):
        self._layer = linked_layer
        self.filename = linked_layer.filename.strip('\0x0')
        self.unique_id = linked_layer.unique_id

    def preferred_extension(self):
        filetype = self._layer.filetype   # 4 chars: 'png ', 'PDF ', ...
        return filetype.lower().strip()

    @property
    def data(self):
        """
        The embedded file content
        """
        return self._layer.decoded

    def save(self, filename=None):
        """
        Save the embedded file
        """
        if filename is None:
            filename = self.filename
        with open(filename, 'wb') as f:
            f.write(self.data)

    def _inkscape(self, *args):
        """Convert using inkscape"""
        import subprocess
        subprocess.check_call(['inkscape', '-z'] + list(args))

    @contextlib.contextmanager
    def _tmp_file(self):
        """Context manager for accessing the content through a temporary file"""
        import tempfile
        tmp_dir = tempfile.mkdtemp()
        tmp_file = os.path.join(tmp_dir, self.filename)
        try:
            self.save(tmp_file)
            yield tmp_file
        finally:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
            os.rmdir(tmp_dir)

    def save_as_png(self, filename=None):
        """
        Save embedded file as PNG

        Requires inkscape to convert the file.
        """
        if filename is None:
            filename = self.filename
        with self._tmp_file() as src:
            self._inkscape('--file', src, '--export-png', filename)

    def save_as_svg(self, filename=None):
        """
        Save embedded file as PNG

        Requires inkscape to convert the file.
        """
        if filename is None:
            filename = self.filename
        with self._tmp_file() as src:
            self.save(src)
            self._inkscape('--file', src, '--export-plain-svg', filename)

