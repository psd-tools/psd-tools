"""
Image resources section structure. Image resources are used to store non-pixel
data associated with images, such as pen tool paths.
"""
from __future__ import absolute_import, unicode_literals
import attr
import logging
import io
from psd_tools2.utils import (
    read_fmt, write_fmt, read_pascal_string, write_pascal_string,
    read_length_block, write_length_block, write_bytes
)
from psd_tools2.validators import in_
from psd_tools2.psd.base import BaseElement, ListElement
from psd_tools2.constants import ImageResourceID

logger = logging.getLogger(__name__)


@attr.s(repr=False)
class ImageResources(ListElement):
    """
    Image resources section of the PSD file. List of
    :py:class:`.ImageResource`.
    """
    @classmethod
    def read(cls, fp, encoding='macroman'):
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: :py:class:`.ImageResources`
        """
        items = []
        data = read_length_block(fp)
        logger.debug('reading image resources, len=%d' % (len(data)))
        with io.BytesIO(data) as f:
            while f.tell() < len(data):
                item = ImageResource.read(f, encoding)
                items.append(item)
        return cls(items)

    def write(self, fp, encoding='macroman'):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        def writer(f):
            written = sum(item.write(f, encoding) for item in self)
            logger.debug('writing image resources, len=%d' % (written))
            return written

        return write_length_block(fp, writer)


@attr.s
class ImageResource(BaseElement):
    """
    Image resource block.

    .. py:attribute:: signature

        Binary signature, always ``b'8BIM'``.

    .. py:attribute:: id

        Unique identifier for the resource. See
        :py:class:`~psd_tools2.constants.ImageResourceID`.

    .. py:attribute:: name
    .. py:attribute:: data

        The resource data.
    """
    signature = attr.ib(default=b'8BIM', type=bytes, repr=False,
                        validator=in_((b'8BIM', b'MeSa')))
    id = attr.ib(default=1000, type=int)
    name = attr.ib(default='', type=str)
    data = attr.ib(default=b'', type=bytes, repr=False)

    @classmethod
    def read(cls, fp, encoding='macroman'):
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: :py:class:`.ImageResource`
        """
        signature, id = read_fmt('4sH', fp)
        name = read_pascal_string(fp, encoding, padding=2)
        data = read_length_block(fp, padding=2)
        # TODO: parse image resource
        return cls(signature, id, name, data)

    def write(self, fp, encoding='macroman'):
        """Write the element to a file-like object.

        :param fp: file-like object
        :rtype: int
        """
        written = write_fmt(fp, '4sH', self.signature, self.id)
        written += write_pascal_string(fp, self.name, encoding, 2)
        written += write_length_block(fp, lambda f: write_bytes(f, self.data),
                                      padding=2)
        return written
