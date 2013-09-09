# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, division
import collections
import logging

from psd_tools.utils import read_fmt, trimmed_repr, read_pascal_string, pad
from psd_tools.exceptions import Error
from psd_tools.constants import ImageResourceID

logger = logging.getLogger(__name__)

_ImageResource = collections.namedtuple("ImageResource", "resource_id, name, data")

class ImageResource(_ImageResource):
    def __repr__(self):
        return "ImageResource(%r %s, %r, %s)" % (
            self.resource_id, ImageResourceID.name_of(self.resource_id),
            self.name, trimmed_repr(self.data)
        )


def read(fp, encoding):
    """ Reads image resources. """
    logger.debug("reading image resources..")

    resource_section_length = read_fmt("I", fp)[0]
    position = fp.tell()
    end_position = position + resource_section_length

    blocks = []
    while fp.tell() < end_position:
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
    if not sig in [b'8BIM', b'MeSa']:
        raise Error("Invalid resource signature (%r)" % sig)

    resource_id = read_fmt("H", fp)[0]
    name = read_pascal_string(fp, encoding, 2)

    data_size = pad(read_fmt("I", fp)[0], 2)
    data = fp.read(data_size)

    return ImageResource(resource_id, name, data)
