from __future__ import absolute_import, unicode_literals
import attr
import logging
from psd_tools2.validators import in_, range_
from psd_tools2.decoder.base import BaseElement
from psd_tools2.constants import ColorMode
from psd_tools2.utils import read_fmt, write_fmt

logger = logging.getLogger(__name__)


@attr.s
class FileHeader(BaseElement):
    """
    Header section of the PSD file.

    Example::

        FileHeader(signature=b'8BPS', version=1, number_of_channels=2,
                   height=359, width=400, depth=8, color_mode=GRAYSCALE)

    .. py:attribute:: version
    .. py:attribute:: channels
    .. py:attribute:: height
    .. py:attribute:: width
    .. py:attribute:: depth
    .. py:attribute:: color_mode

        :py:class:`~psd_tools2.constants.ColorMode`
    """
    FORMAT = '4sH6xHIIHH'

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
        """Read the element from a file-like object.

        :param fp: file-like object
        :rtype: FileHeader
        """
        return cls(*read_fmt(cls.FORMAT, fp))

    def write(self, fp):
        """Write the element to a file-like object.

        :param fp: file-like object
        """
        return write_fmt(fp, self.FORMAT, *attr.astuple(self))
