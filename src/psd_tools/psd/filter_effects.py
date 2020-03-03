"""
Filter effects structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import io
import logging

from psd_tools.psd.base import BaseElement, ListElement
from psd_tools.utils import (
    read_fmt,
    write_fmt,
    read_length_block,
    write_length_block,
    is_readable,
    write_bytes,
    read_pascal_string,
    write_pascal_string,
)

logger = logging.getLogger(__name__)


@attr.s(repr=False, slots=True)
class FilterEffects(ListElement):
    """
    List-like FilterEffects structure. See :py:class:`FilterEffect`.

    .. py:attribute:: version
    """
    version = attr.ib(default=1, type=int)

    @classmethod
    def read(cls, fp, **kwargs):
        version = read_fmt('I', fp)[0]
        assert version in (1, 2, 3), 'Invalid version %d' % (version)
        items = []
        while is_readable(fp, 8):
            with io.BytesIO(read_length_block(fp, fmt='Q', padding=4)) as f:
                items.append(FilterEffect.read(f))
        return cls(version=version, items=items)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'I', self.version)
        for item in self:
            written += write_length_block(
                fp, lambda f: item.write(f), fmt='Q', padding=4
            )
        return written


@attr.s(repr=False, slots=True)
class FilterEffect(BaseElement):
    """
    FilterEffect structure.

    .. py:attribute:: uuid
    .. py:attribute:: version
    .. py:attribute:: rectangle
    .. py:attribute:: depth
    .. py:attribute:: max_channels
    .. py:attribute:: channels

        List of :py:class:`FilterEffectChannel`.

    .. py:attribute:: extra

        See :py:class:`FilterEffectExtra`.
    """
    uuid = attr.ib(default=None)
    version = attr.ib(default=None)
    rectangle = attr.ib(default=None)
    depth = attr.ib(default=None)
    max_channels = attr.ib(default=None)
    channels = attr.ib(default=None)
    extra = attr.ib(default=None)

    @classmethod
    def read(cls, fp, **kwargs):
        uuid = read_pascal_string(fp, encoding='ascii', padding=1)
        version = read_fmt('I', fp)[0]
        assert version <= 1, 'Invalid version %d' % (version)
        with io.BytesIO(read_length_block(fp, fmt='Q')) as f:
            rectangle, depth, max_channels, channels = cls._read_body(f)
        # Documentation is incorrect here.
        extra = FilterEffectExtra.read(fp) if is_readable(fp) else None
        return cls(
            uuid, version, rectangle, depth, max_channels, channels, extra
        )

    @classmethod
    def _read_body(cls, fp):
        rectangle = read_fmt('4i', fp)
        depth, max_channels = read_fmt('2I', fp)
        channels = []
        for _ in range(max_channels + 2):
            channels.append(FilterEffectChannel.read(fp))
        return rectangle, depth, max_channels, channels

    def write(self, fp, **kwargs):
        written = write_pascal_string(
            fp, self.uuid, encoding='ascii', padding=1
        )
        written += write_fmt(fp, 'I', self.version)

        def writer(f):
            return self._write_body(f)

        written += write_length_block(fp, writer, fmt='Q')

        if self.extra is not None:
            written += self.extra.write(fp)
        return written

    def _write_body(self, fp):
        written = write_fmt(fp, '4i', *self.rectangle)
        written += write_fmt(fp, '2I', self.depth, self.max_channels)
        for channel in self.channels:
            written += channel.write(fp)
        return written


@attr.s(repr=False, slots=True)
class FilterEffectChannel(BaseElement):
    """
    FilterEffectChannel structure.

    .. py:attribute:: is_written
    .. py:attribute:: compression
    .. py:attribute:: data
    """
    is_written = attr.ib(default=0)
    compression = attr.ib(default=None)
    data = attr.ib(default=b'')

    @classmethod
    def read(cls, fp, **kwargs):
        is_written = read_fmt('I', fp)[0]
        if is_written == 0:
            return cls(is_written=is_written)
        data = read_length_block(fp, fmt='Q')
        if len(data) == 0:
            return cls(is_written=is_written)
        with io.BytesIO(data) as f:
            compression = read_fmt('H', f)[0]
            data = f.read()
        return cls(is_written, compression, data)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'I', self.is_written)
        if self.is_written == 0:
            return written

        def writer(f):
            if self.compression is None:
                return 0
            length = write_fmt(f, 'H', self.compression)
            length += write_bytes(f, self.data)
            return length

        written += write_length_block(fp, writer, fmt='Q')
        return written


@attr.s(repr=False, slots=True)
class FilterEffectExtra(BaseElement):
    """
    FilterEffectExtra structure.

    .. py:attribute:: is_written
    .. py:attribute:: rectangle
    .. py:attribute:: compression
    .. py:attribute:: data
    """
    is_written = attr.ib(default=0)
    rectangle = attr.ib(factory=lambda: [0, 0, 0, 0], converter=list)
    compression = attr.ib(default=0, type=int)
    data = attr.ib(default=b'', type=bytes)

    @classmethod
    def read(cls, fp):
        is_written = read_fmt('B', fp)[0]
        if not is_written:
            return cls(is_written=is_written)

        rectangle = read_fmt('4i', fp)
        compression = 0
        data = b''
        with io.BytesIO(read_length_block(fp, fmt='Q')) as f:
            compression = read_fmt('H', f)[0]
            data = f.read()

        return cls(is_written, rectangle, compression, data)

    def write(self, fp):
        written = write_fmt(fp, 'B', self.is_written)

        def writer(f):
            length = write_fmt(f, 'H', self.compression)
            length += write_bytes(f, self.data)
            return length

        if self.is_written:
            written += write_fmt(fp, '4i', *self.rectangle)
            written += write_length_block(fp, writer, fmt='Q')
        return written
