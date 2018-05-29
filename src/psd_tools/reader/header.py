# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import logging
import collections
import warnings

from psd_tools.exceptions import Error
from psd_tools.utils import read_fmt
from psd_tools.constants import ColorMode

logger = logging.getLogger(__name__)


class PsdHeader(collections.namedtuple(
    "PsdHeader",
    "version, number_of_channels, height, width, depth, color_mode"
)):
    """
    Header section of the PSD file.

    Example::

        PsdHeader(version=1, number_of_channels=2, height=359, width=400, \
depth=8, color_mode=GRAYSCALE)

    .. py:attribute:: version
    .. py:attribute:: number_of_channels
    .. py:attribute:: height
    .. py:attribute:: width
    .. py:attribute:: depth
    .. py:attribute:: color_mode

        :py:class:`~psd_tools.constants.ColorMode`
    """
    def __repr__(self):
        return (
            "PsdHeader(version=%s, number_of_channels=%s, height=%s, "
            "width=%s, depth=%s, color_mode=%s)" % (
                self.version, self.number_of_channels, self.height,
                self.width, self.depth, ColorMode.name_of(self.color_mode)
            )
        )


def read(fp):
    """
    Reads PSD file header.
    """
    logger.debug("reading header..")
    signature = fp.read(4)
    if signature != b'8BPS':
        raise Error("This is not a PSD or PSB file")

    version = read_fmt("H", fp)[0]
    if version not in (1, 2):
        raise Error("Unsupported PSD version (%s)" % version)

    header = PsdHeader(version, *read_fmt("6x HIIHH", fp))

    if not ColorMode.is_known(header.color_mode):
        warnings.warn("Unknown color mode: %s" % header.color_mode)

    logger.debug(header)
    return header
