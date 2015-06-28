# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, division
import logging

from psd_tools.utils import read_fmt, trimmed_repr, read_pascal_string, pad
from psd_tools.exceptions import Error
from psd_tools.constants import ImageResourceID
from psd_tools.debug import pretty_namedtuple

logger = logging.getLogger(__name__)

_ImageResource = pretty_namedtuple("ImageResource", "resource_id, name, data")

class ImageResource(_ImageResource):

    def __repr__(self):
        return "ImageResource(%r %s, %r, %s)" % (
            self.resource_id, ImageResourceID.name_of(self.resource_id),
            self.name, trimmed_repr(self.data)
        )

    def _repr_pretty_(self, p, cycle):
        if cycle:
            p.text(repr(self))
        else:
            with p.group(0, 'ImageResource(', ')'):
                p.text("%r %s, %r, " % (
                    self.resource_id, ImageResourceID.name_of(self.resource_id),
                    self.name
                ))
                if isinstance(self.data, bytes):
                    p.text(trimmed_repr(self.data))
                else:
                    p.pretty(self.data)


def read(fp, encoding):
    """ Reads image resources. """
    logger.debug("reading image resources..")

    resource_section_length = read_fmt("I", fp)[0]
    end_position = fp.tell() + resource_section_length

    blocks = []
    while fp.tell() < end_position:
        block = _read_block(fp, encoding)
        if block is not None:
            logger.debug("%r", block)
            blocks.append(block)

    return blocks

def _read_block(fp, encoding):
    """
    Reads single image resource block. Such blocks contain non-pixel data
    for the images (e.g. pen tool paths).
    """
    sig = fp.read(4)
    if not sig in (b'8BIM', b'MeSa'):
        raise Error("Invalid resource signature (%r)" % sig)

    resource_id = read_fmt("H", fp)[0]
    name = read_pascal_string(fp, encoding, 2)

    data_size = pad(read_fmt("I", fp)[0], 2)
    if not data_size:
        logger.debug(
            "Found image resource with no data (%d %s). Dropping..." % (
            resource_id, ImageResourceID.name_of(resource_id)
        ))
        return None

    data = fp.read(data_size)
    return ImageResource(resource_id, name, data)
