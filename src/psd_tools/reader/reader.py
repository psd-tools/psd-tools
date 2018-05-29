# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, division
import logging

import psd_tools.reader.header
import psd_tools.reader.color_mode_data
import psd_tools.reader.image_resources
import psd_tools.reader.layers
from psd_tools.debug import pretty_namedtuple

logger = logging.getLogger(__name__)


class ParseResult(pretty_namedtuple(
    'ParseResult',
    'header, color_data, image_resource_blocks, layer_and_mask_data, '
    'image_data'
)):
    """
    Result of :py:func:`~psd_tools.reader.parse`. The result consists of the
    following fields in a PSD file.

    .. py:attribute:: header

        :py:class:`~psd_tools.reader.header.PsdHeader`

    .. py:attribute:: color_data

        :py:class:`bytes`

    .. py:attribute:: image_resource_blocks

        :py:class:`list` of
        :py:class:`~psd_tools.reader.image_resources.ImageResource`

    .. py:attribute:: layer_and_mask_data

        :py:class:`~psd_tools.reader.layers.LayerAndMaskData`

    .. py:attribute:: image_data

        :py:class:`list` of :py:class:`~psd_tools.reader.layers.ChannelData`
    """


def parse(fp, encoding='utf8'):
    """
    Read PSD file from file-like object.

    :rtype: ParseResult

    Example::

        from psd_tools.reader.reader import parse

        with open('/path/to/input.psd', 'rb') as fp:
            result = parse(fp)
    """

    header = psd_tools.reader.header.read(fp)
    return ParseResult(
        header,
        psd_tools.reader.color_mode_data.read(fp),
        psd_tools.reader.image_resources.read(fp, encoding),
        psd_tools.reader.layers.read(fp, encoding, header.depth,
                                     header.version),
        psd_tools.reader.layers.read_image_data(fp, header)
    )
