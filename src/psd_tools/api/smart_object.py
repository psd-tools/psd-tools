"""
Smart object module.
"""

from __future__ import absolute_import, unicode_literals

import contextlib
import io
import logging
import os

from psd_tools.constants import Tag

logger = logging.getLogger(__name__)


class SmartObject(object):
    """
    Smart object that represents embedded or external file.

    Smart objects are attached to
    :py:class:`~psd_tools.api.layers.SmartObjectLayer`.
    """

    def __init__(self, layer):
        self._config = None
        for key in (Tag.SMART_OBJECT_LAYER_DATA1, Tag.SMART_OBJECT_LAYER_DATA2):
            if key in layer.tagged_blocks:
                self._config = layer.tagged_blocks.get_data(key)
                break

        self._placed_layer = None
        for key in (Tag.PLACED_LAYER1, Tag.PLACED_LAYER2):
            if key in layer.tagged_blocks:
                self._placed_layer = layer.tagged_blocks.get_data(key)
                break

        self._data = None
        for key in (
            Tag.LINKED_LAYER1,
            Tag.LINKED_LAYER2,
            Tag.LINKED_LAYER3,
            Tag.LINKED_LAYER_EXTERNAL,
        ):
            if key in layer._psd.tagged_blocks:
                data = layer._psd.tagged_blocks.get_data(key)
                for item in data:
                    if item.uuid == self.unique_id:
                        self._data = item
                        break
                if self._data:
                    break

    @property
    def kind(self):
        """Kind of the link, 'data', 'alias', or 'external'."""
        return self._data.kind.name.lower()

    @property
    def filename(self):
        """Original file name of the object."""
        return self._data.filename.strip("\x00")

    @contextlib.contextmanager
    def open(self, external_dir=None):
        """
        Open the smart object as binary IO.

        :param external_dir: Path to the directory of the external file.

        Example::

            with layer.smart_object.open() as f:
                data = f.read()
        """
        if self.kind == "data":
            with io.BytesIO(self._data.data) as f:
                yield f
        elif self.kind == "external":
            filepath = self._data.linked_file[b"fullPath"].value
            filepath = filepath.replace("\x00", "").replace("file://", "")
            if not os.path.exists(filepath):
                filepath = self._data.linked_file[b"relPath"].value
                filepath = filepath.replace("\x00", "")
                if external_dir is not None:
                    filepath = os.path.join(external_dir, filepath)
            with open(filepath, "rb") as f:
                yield f
        else:
            raise NotImplementedError("alias is not supported.")

    @property
    def data(self):
        """Embedded file content, or empty if kind is `external` or `alias`"""
        if self.kind == "data":
            return self._data.data
        else:
            with self.open() as f:
                return f.read()

    @property
    def unique_id(self):
        """UUID of the object."""
        return self._config.data.get(b"Idnt").value.strip("\x00")

    @property
    def filesize(self):
        """File size of the object."""
        if self.kind == "data":
            return len(self._data.data)
        return self._data.filesize

    @property
    def filetype(self):
        """Preferred file extension, such as `jpg`."""
        return self._data.filetype.lower().strip().decode("ascii")

    def is_psd(self):
        """Return True if the file is embedded PSD/PSB."""
        return self.filetype in ("8bpb", "8bps")

    @property
    def warp(self):
        """Warp parameters."""
        return self._config.data.get(b"warp")

    @property
    def resolution(self):
        """Resolution of the object."""
        return self._config.data.get(b"Rslt").value

    @property
    def transform_box(self):
        """
        A tuple representing the coordinates of the smart objects's transformed box. This box is the result of one or more transformations such as scaling, rotation, translation, or skewing to the original bounding box of the smart object.

        The format of the tuple is as follows:
        (x1, y1, x2, y2, x3, y3, x4, y4)

        Where 1 is top left corner, 2 is top right, 3 is bottom right and 4 is bottom left.
        """
        if self._placed_layer and hasattr(self._placed_layer, "transform"):
            return self._placed_layer.transform
        else:
            return None

    def save(self, filename=None):
        """
        Save the smart object to a file.

        :param filename: File name to export. If None, use the embedded name.
        """
        if filename is None:
            filename = self.filename
        with open(filename, "wb") as f:
            f.write(self.data)

    def __repr__(self):
        return "SmartObject(%r kind=%r type=%r size=%s)" % (
            self.filename,
            self.kind,
            self.filetype,
            self.filesize,
        )
