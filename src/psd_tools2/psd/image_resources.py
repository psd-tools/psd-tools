"""
Image resources section structure. Image resources are used to store non-pixel
data associated with images, such as pen tool paths.
"""
from __future__ import absolute_import, unicode_literals
import attr
import logging
import io

from psd_tools2.constants import ImageResourceID
from psd_tools2.psd.base import (
    BaseElement, BooleanElement, ByteElement, ListElement, IntegerElement,
    ShortIntegerElement, ValueElement,
)
from psd_tools2.utils import (
    read_fmt, write_fmt, read_pascal_string, write_pascal_string,
    read_length_block, write_length_block, write_bytes, new_registry,
    read_unicode_string, write_unicode_string, is_readable
)
from psd_tools2.validators import in_


logger = logging.getLogger(__name__)

TYPES, register = new_registry()

TYPES.update({
    ImageResourceID.COPYRIGHT_FLAG: ShortIntegerElement,
    ImageResourceID.EFFECTS_VISIBLE: BooleanElement,
    ImageResourceID.GLOBAL_ALTITUDE: IntegerElement,
    ImageResourceID.GLOBAL_ANGLE: IntegerElement,
    ImageResourceID.ICC_UNTAGGED_PROFILE: BooleanElement,
    ImageResourceID.IDS_SEED_NUMBER: IntegerElement,
    ImageResourceID.INDEXED_COLOR_TABLE_COUNT: ShortIntegerElement,
    ImageResourceID.LAYER_STATE_INFO: ShortIntegerElement,
    ImageResourceID.TRANSPARENCY_INDEX: ShortIntegerElement,
    ImageResourceID.WATERMARK: ByteElement,
})


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
        data = read_length_block(fp)
        logger.debug('reading image resources, len=%d' % (len(data)))
        with io.BytesIO(data) as f:
            return cls._read_body(f, encoding=encoding)

    @classmethod
    def _read_body(cls, fp, *args, **kwargs):
        items = []
        while is_readable(fp, 4):
            items.append(ImageResource.read(fp, *args, **kwargs))
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


@register(ImageResourceID.ALPHA_NAMES_UNICODE)
@register(ImageResourceID.AUTO_SAVE_FILE_PATH)
@register(ImageResourceID.AUTO_SAVE_FORMAT)
@register(ImageResourceID.WORKFLOW_URL)
class String(ValueElement):
    """
    String element.
    """
    @classmethod
    def read(cls, fp, **kwargs):
        return cls(read_unicode_string(fp, padding=2))

    def write(cls, fp, **kwargs):
        return write_unicode_string(fp, self.value, padding=2)
