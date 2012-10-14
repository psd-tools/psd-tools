# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, division
import collections
import logging

from psd_tools.utils import read_fmt, trimmed_repr, read_pascal_string, pad
from psd_tools.exceptions import Error

logger = logging.getLogger(__name__)

class ImageResource(collections.namedtuple("ImageResource", "resource_id, name, data")):
    def __repr__(self):
        return "ImageResource(%r, %r, %s)" % (
            self.resource_id, self.name, trimmed_repr(self.data, 20))


def read(fp, encoding):
    """ Reads image resources. """
    logger.debug("reading image resources..")

    resource_section_length = read_fmt("I", fp)[0]
    position = fp.tell()
    blocks = []
    while fp.tell() < position + resource_section_length:
        block = _read_block(fp, encoding)
        logger.debug("%r", block)
        blocks.append(block)
    return blocks

def _read_block(fp, encoding):
    """
    Reads single image resource block. Such blocks contain non-pixel data
    for the images (e.g. pen tool paths).
    """
    sig = fp.read(4)
    if sig != b'8BIM':
        raise Error("Invalid resource signature (%r)" % sig)

    resource_id = read_fmt("H", fp)[0]
    name = read_pascal_string(fp, encoding, 2)
    fp.seek(1, 1) # XXX: why is this needed??

    data_size = read_fmt("I", fp)[0]
    data = fp.read(pad(data_size, 2))

    return ImageResource(resource_id, name, data)
