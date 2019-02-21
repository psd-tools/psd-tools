"""
File header structure.
"""
from __future__ import absolute_import, unicode_literals
import attr
import logging
from psd_tools.validators import in_, range_
from psd_tools.psd.base import BaseElement
from psd_tools.constants import ColorMode
from psd_tools.utils import read_fmt, write_fmt

logger = logging.getLogger(__name__)


@attr.s(slots=True)
class FileHeader(BaseElement):
    """
    Header section of the PSD file.

    Example::

        from psd_tools.psd.header import FileHeader
        from psd_tools.constants import ColorMode

        header = FileHeader(channels=2, height=359, width=400, depth=8,
                            color_mode=ColorMode.GRAYSCALE)

    .. py:attribute:: signature

        Signature: always equal to ``b'8BPS'``.

    .. py:attribute:: version

        Version number. PSD is 1, and PSB is 2.

    .. py:attribute:: channels

        The number of channels in the image, including any alpha channels.

    .. py:attribute:: height

        The height of the image in pixels.

    .. py:attribute:: width

        The width of the image in pixels.

    .. py:attribute:: depth

        The number of bits per channel.

    .. py:attribute:: color_mode

        The color mode of the file. See
        :py:class:`~psd_tools.constants.ColorMode`
    """
    _FORMAT = '4sH6xHIIHH'

    signature = attr.ib(default=b'8BPS', type=bytes, repr=False)
    version = attr.ib(default=1, type=int, validator=in_((1, 2)))
    channels = attr.ib(default=4, type=int, validator=range_(1, 57))
    height = attr.ib(default=64, type=int, validator=range_(1, 300001))
    width = attr.ib(default=64, type=int, validator=range_(1, 300001))
    depth = attr.ib(default=8, type=int, validator=in_((1, 8, 16, 32)))
    color_mode = attr.ib(default=ColorMode.RGB, converter=ColorMode,
                         validator=in_(ColorMode))

    @signature.validator
    def _validate_signature(self, attribute, value):
        if value != b'8BPS':
            raise ValueError('This is not a PSD or PSB file')

    @classmethod
    def read(cls, fp):
        return cls(*read_fmt(cls._FORMAT, fp))

    def write(self, fp):
        return write_fmt(fp, self._FORMAT, *attr.astuple(self))
