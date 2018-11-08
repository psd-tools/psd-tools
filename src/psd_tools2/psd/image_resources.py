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
    BaseElement, BooleanElement, ByteElement, DictElement, IntegerElement,
    ShortIntegerElement, ValueElement,
)
from psd_tools2.psd.color import Color
from psd_tools2.psd.descriptor import DescriptorBlock
from psd_tools2.utils import (
    read_fmt, write_fmt, read_pascal_string, write_pascal_string,
    read_length_block, write_length_block, write_bytes, new_registry,
    read_unicode_string, write_unicode_string, is_readable, trimmed_repr
)
from psd_tools2.validators import in_


logger = logging.getLogger(__name__)

TYPES, register = new_registry()

TYPES.update({
    ImageResourceID.BACKGROUND_COLOR: Color,
})


@attr.s(repr=False)
class ImageResources(DictElement):
    """
    Image resources section of the PSD file. Dict of
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
            item = ImageResource.read(fp, *args, **kwargs)
            items.append((item.key, item))
        return cls(items)

    def write(self, fp, encoding='macroman'):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        def writer(f):
            written = sum(self[key].write(f, encoding) for key in self)
            logger.debug('writing image resources, len=%d' % (written))
            return written

        return write_length_block(fp, writer)

    def _repr_pretty_(self, p, cycle):
        if cycle:
            return "{{...}".format(name=self.__class__.__name__)

        with p.group(2, '{{'.format(name=self.__class__.__name__), '}'):
            p.breakable('')
            for idx, key in enumerate(self._items):
                if idx:
                    p.text(',')
                    p.breakable()
                value = self._items[key]
                if hasattr(key, 'name'):
                    p.text(key.name)
                else:
                    p.pretty(key)
                p.text(': ')
                if isinstance(value.data, bytes):
                    p.text(trimmed_repr(value.data))
                else:
                    p.pretty(value.data)
            p.breakable('')


@attr.s
class ImageResource(BaseElement):
    """
    Image resource block.

    .. py:attribute:: signature

        Binary signature, always ``b'8BIM'``.

    .. py:attribute:: key

        Unique identifier for the resource. See
        :py:class:`~psd_tools2.constants.ImageResourceID`.

    .. py:attribute:: name
    .. py:attribute:: data

        The resource data.
    """
    signature = attr.ib(default=b'8BIM', type=bytes, repr=False,
                        validator=in_((b'8BIM', b'MeSa')))
    key = attr.ib(default=1000, type=int)
    name = attr.ib(default='', type=str)
    data = attr.ib(default=b'', type=bytes, repr=False)

    @classmethod
    def read(cls, fp, encoding='macroman'):
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: :py:class:`.ImageResource`
        """
        signature, key = read_fmt('4sH', fp)
        try:
            key = ImageResourceID(key)
        except ValueError:
            logger.warning('Unknown image resource %d' % (key))
        name = read_pascal_string(fp, encoding, padding=2)
        data = read_length_block(fp, padding=2)
        if key in TYPES:
            data = TYPES[key].frombytes(data)
        return cls(signature, key, name, data)

    def write(self, fp, encoding='macroman'):
        """Write the element to a file-like object.

        :param fp: file-like object
        :rtype: int
        """
        written = write_fmt(fp, '4sH', self.signature,
                            getattr(self.key, 'value', self.key))
        written += write_pascal_string(fp, self.name, encoding, 2)

        def writer(f):
            if hasattr(self.data, 'write'):
                return self.data.write(f)
            return write_bytes(f, self.data)

        written += write_length_block(fp, writer, padding=2)
        return written


@register(ImageResourceID.GLOBAL_ALTITUDE)
@register(ImageResourceID.GLOBAL_ANGLE)
@register(ImageResourceID.IDS_SEED_NUMBER)
class Integer(IntegerElement):
    """
    Integer element.
    """
    @classmethod
    def read(cls, fp, **kwargs):
        return cls(*read_fmt('i', fp))

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'i', self.value)


@register(ImageResourceID.INDEXED_COLOR_TABLE_COUNT)
@register(ImageResourceID.LAYER_STATE_INFO)
@register(ImageResourceID.TRANSPARENCY_INDEX)
class ShortInteger(ShortIntegerElement):
    """
    Short integer element.
    """
    @classmethod
    def read(cls, fp, **kwargs):
        return cls(*read_fmt('H', fp))

    def write(self, fp, **kwargs):
        return write_fmt(fp, 'H', self.value)


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

    def write(self, fp, **kwargs):
        return write_unicode_string(fp, self.value, padding=2)


# @register(ImageResourceID.LAYER_COMPS)
class DescriptorBlockPad2(DescriptorBlock):
    def write(self, fp, **kwargs):
        return super(DescriptorBlockPad2, self).write(fp, padding=2, **kwargs)
