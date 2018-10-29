"""
Tagged block data structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import io
import logging

from psd_tools2.decoder.base import BaseElement, ListElement
from psd_tools2.decoder.descriptor import Descriptor
from psd_tools2.constants import TaggedBlockID
from psd_tools2.validators import in_
from psd_tools2.utils import (
    read_fmt, write_fmt, read_length_block, write_length_block, is_readable,
    write_bytes, read_unicode_string, write_unicode_string,
)

logger = logging.getLogger(__name__)


TYPES = {}


def register(key):
    def _register(cls):
        TYPES[key] = cls
        return cls
    return _register


@attr.s(repr=False)
class TaggedBlocks(ListElement):
    """
    List of tagged blocks.

    .. py:attribute:: items
    """
    items = attr.ib(factory=list)

    @classmethod
    def read(cls, fp, version=1, padding=1):
        """Read the element from a file-like object.

        :param fp: file-like object
        :param version: psd file version
        :rtype: :py:class:`.TaggedBlocks`
        """
        items = []
        while is_readable(fp, 8):  # len(signature) + len(key) = 8
            block = TaggedBlock.read(fp, version, padding)
            if block is None:
                break
            items.append(block)
        return cls(items)

    def write(self, fp, version=1, padding=1):
        """Write the element to a file-like object.

        :param fp: file-like object
        :rtype: int
        """
        return sum(item.write(fp, version, padding) for item in self)


@attr.s
class TaggedBlock(BaseElement):
    """
    Layer tagged block with extra info.

    .. py:attribute:: key

        4-character code. See :py:class:`~psd_tools2.constants.TaggedBlock`

    .. py:attribute:: data

        Data.
    """
    _SIGNATURES = (b'8BIM', b'8B64')
    _BIG_KEYS = {
        TaggedBlockID.USER_MASK,
        TaggedBlockID.LAYER_16,
        TaggedBlockID.LAYER_32,
        TaggedBlockID.LAYER,
        TaggedBlockID.SAVING_MERGED_TRANSPARENCY16,
        TaggedBlockID.SAVING_MERGED_TRANSPARENCY32,
        TaggedBlockID.SAVING_MERGED_TRANSPARENCY,
        TaggedBlockID.SAVING_MERGED_TRANSPARENCY16,
        TaggedBlockID.ALPHA,
        TaggedBlockID.FILTER_MASK,
        TaggedBlockID.LINKED_LAYER2,
        TaggedBlockID.LINKED_LAYER_EXTERNAL,
        TaggedBlockID.FILTER_EFFECTS1,
        TaggedBlockID.FILTER_EFFECTS2,
        TaggedBlockID.PIXEL_SOURCE_DATA2,
        TaggedBlockID.UNICODE_PATH_NAME,
    }

    signature = attr.ib(default=b'8BIM', repr=False,
                        validator=in_(_SIGNATURES))
    key = attr.ib(default=b'')
    data = attr.ib(default=b'', repr=True)

    @classmethod
    def read(cls, fp, version=1, padding=1):
        """Read the element from a file-like object.

        :param fp: file-like object
        :param version: psd file version
        :rtype: :py:class:`.TaggedBlock`
        """
        signature = read_fmt('4s', fp)[0]
        if signature not in cls._SIGNATURES:
            logger.warning('Invalid signature (%r)' % (signature))
            fp.seek(-4, 1)
            return None

        key = read_fmt('4s', fp)[0]
        try:
            key = TaggedBlockID(key)
        except ValueError:
            logger.warning('Unknown key: %r' % (key))

        fmt = cls._length_format(key, version)
        data = read_length_block(fp, fmt=fmt, padding=padding)

        kls = TYPES.get(key)
        # logger.debug('%s %s' % (key, kls))
        if kls and len(data) >= 4:
            try:
                data = kls.frombytes(data)
            except (ValueError,):
                logger.warning('Failed to read tagged block: %r' % (key))
        return cls(signature, key, data)

    def write(self, fp, version=1, padding=1):
        """Write the element to a file-like object.

        :param fp: file-like object
        :param version: psd file version
        """
        key = self.key if isinstance(self.key, bytes) else self.key.value
        written = write_fmt(fp, '4s4s', self.signature, key)

        def writer(f):
            if hasattr(self.data, 'write'):
                return self.data.write(f)
            return write_bytes(f, self.data)

        fmt = self._length_format(self.key, version)
        written += write_length_block(fp, writer, fmt=fmt, padding=padding)
        return written

    @classmethod
    def _length_format(cls, key, version):
        return ('I', 'Q')[int(version == 2 and key in cls._BIG_KEYS)]


@register(TaggedBlockID.BLEND_CLIPPING_ELEMENTS)
@register(TaggedBlockID.BLEND_INTERIOR_ELEMENTS)
@register(TaggedBlockID.KNOCKOUT_SETTING)
@register(TaggedBlockID.LAYER_ID)
@register(TaggedBlockID.LAYER_VERSION)
@register(TaggedBlockID.USING_ALIGNED_RENDERING)
@attr.s
class Integer(BaseElement):
    """
    Integer structure.

    .. py:attribute:: value
    """
    value = attr.ib(default=0, type=int)

    @classmethod
    def read(cls, fp):
        return cls(read_fmt('I', fp)[0])

    def write(self, fp):
        return write_fmt(fp, 'I', self.value)

    def __int__(self):
        return self.value

    def __index__(self):
        return self.value


@register(TaggedBlockID.BLEND_FILL_OPACITY)
@register(TaggedBlockID.LAYER_MASK_AS_GLOBAL_MASK)
@register(TaggedBlockID.TRANSPARENCY_SHAPES_LAYER)
@register(TaggedBlockID.VECTOR_MASK_AS_GLOBAL_MASK)
@attr.s
class Bytes(BaseElement):
    """
    Integer structure.

    .. py:attribute:: value
    """
    value = attr.ib(default=b'\x00\x00\x00\x00', type=bytes)

    @classmethod
    def read(cls, fp):
        return cls(read_fmt('B3x', fp)[0])

    def write(self, fp):
        return write_fmt(fp, 'B3x', self.value)

    def __bytes__(self):
        return self.value


@register(TaggedBlockID.UNICODE_LAYER_NAME)
@attr.s
class String(BaseElement):
    """
    Integer structure.

    .. py:attribute:: value
    """
    value = attr.ib(default='', type=str)

    @classmethod
    def read(cls, fp):
        return cls(read_unicode_string(fp))

    def write(self, fp):
        return write_unicode_string(fp, self.value)

    def __str__(self):
        return self.value


# @register(TaggedBlockID.ANIMATION_EFFECTS)
# @register(TaggedBlockID.ARTBOARD_DATA1)
# @register(TaggedBlockID.ARTBOARD_DATA2)
# @register(TaggedBlockID.ARTBOARD_DATA3)
# @register(TaggedBlockID.BLACK_AND_WHITE)
# @register(TaggedBlockID.CONTENT_GENERATOR_EXTRA_DATA)
# @register(TaggedBlockID.EXPORT_SETTING1)
# @register(TaggedBlockID.EXPORT_SETTING2)
# @register(TaggedBlockID.GRADIENT_FILL_SETTING)
# @register(TaggedBlockID.PATTERN_FILL_SETTING)
# @register(TaggedBlockID.PIXEL_SOURCE_DATA1)
# @register(TaggedBlockID.SOLID_COLOR_SHEET_SETTING)
# @register(TaggedBlockID.UNICODE_PATH_NAME)
# @register(TaggedBlockID.VIBRANCE)
@attr.s
class DescriptorBlock(BaseElement):
    """
    Integer structure.

    .. py:attribute:: version
    .. py:attribute:: data
    """
    version = attr.ib(default=1, type=int)
    data = attr.ib(default=None, type=Descriptor)

    @classmethod
    def read(cls, fp):
        version = read_fmt('I', fp)[0]
        data = Descriptor.read(fp)
        return cls(version, data)

    def write(self, fp):
        written = write_fmt(fp, 'I', self.version)
        written += self.data.write(fp)
        return written


# TaggedBlockID.BRIGHTNESS_AND_CONTRAST
# TaggedBlockID.EFFECTS_LAYER
# TaggedBlockID.OBJECT_BASED_EFFECTS_LAYER_INFO
# TaggedBlockID.OBJECT_BASED_EFFECTS_LAYER_INFO_V0
# TaggedBlockID.OBJECT_BASED_EFFECTS_LAYER_INFO_V1
#
