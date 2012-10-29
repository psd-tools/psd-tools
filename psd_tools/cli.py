# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, print_function
import logging
import docopt
import pprint

import psd_tools.reader
import psd_tools.decoder
from psd_tools import user_api
from psd_tools.user_api.layers import group_layers, image_to_PIL

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

        with open(args['<psd_filename>'], 'rb') as f:
            res = psd_tools.reader.parse(f)
            decoded = psd_tools.decoder.parse(res)
            im = image_to_PIL(decoded)
            im.save(args['<out_filename>'])

    else:
        decoded = user_api.parse(args['<filename>'])

        print(decoded.header)
        pprint.pprint(decoded.image_resource_blocks)
        pprint.pprint(group_layers(decoded))
