"""
File header structure.
"""

import logging
from typing import Any, BinaryIO, TypeVar

from attrs import define, field, astuple

from psd_tools.constants import ColorMode
from psd_tools.psd.base import BaseElement
from psd_tools.psd.bin_utils import read_fmt, write_fmt
from psd_tools.validators import in_, range_

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="FileHeader")


@define(repr=True)
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

        The number of channels in the image, including any user-defined alpha
        channel.

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

    _FORMAT = "4sH6xHIIHH"

    signature: bytes = field(default=b"8BPS", repr=False)
    version: int = field(default=1, validator=in_((1, 2)))
    channels: int = field(default=4, validator=range_(1, 57))
    height: int = field(default=64, validator=range_(1, 300001))
    width: int = field(default=64, validator=range_(1, 300001))
    depth: int = field(default=8, validator=in_((1, 8, 16, 32)))
    color_mode: ColorMode = field(
        default=ColorMode.RGB, converter=ColorMode, validator=in_(ColorMode)
    )

    @signature.validator
    def _validate_signature(self, attribute: Any, value: bytes) -> None:
        if value != b"8BPS":
            raise ValueError("This is not a PSD or PSB file")

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        return cls(*read_fmt(cls._FORMAT, fp))

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, self._FORMAT, *astuple(self))
