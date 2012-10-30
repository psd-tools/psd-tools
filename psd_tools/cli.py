# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, print_function
import logging
import docopt
import pprint

import psd_tools.reader
import psd_tools.decoder
from psd_tools import PSDImage
from psd_tools.user_api.layers import group_layers, composite_image_to_PIL

logger = logging.getLogger('psd_tools')
logger.addHandler(logging.StreamHandler())

def main():
    """
    psd-tools.py

    Usage:
        psd-tools.py <filename> [--encoding <encoding>] [--verbose]
        psd-tools.py convert <psd_filename> <out_filename> [--verbose]
        psd-tools.py -h | --help
        psd-tools.py --version

    Options:
        -v --verbose                Be more verbose.
        --encoding <encoding>       Text encoding [default: ascii].

    """
    args = docopt.docopt(main.__doc__)

    if args['--verbose']:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    if args['convert']:
        psd = PSDImage.load(args['<psd_filename>'])
        im = psd.composite_image()
        im.save(args['<out_filename>'])

    else:
        encoding = args['--encoding']
        with open(args['<filename>'], "rb") as f:
            decoded = psd_tools.decoder.parse(
                psd_tools.reader.parse(f, encoding)
            )

        print(decoded.header)
        pprint.pprint(decoded.image_resource_blocks)
        pprint.pprint(group_layers(decoded))
