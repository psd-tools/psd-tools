# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import logging
import docopt
import pprint

import psd_tools.reader
import psd_tools.decoder

logger = logging.getLogger('psd_tools')
logger.addHandler(logging.StreamHandler())

def main():
    """
    psd-tools.py

    Usage:
        psd-tools.py <filename> [--encoding <encoding>] [--verbose]
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

    with open(args['<filename>'], 'rb') as f:
        res = psd_tools.reader.parse(f, args['--encoding'])
        decoded = psd_tools.decoder.decode(res)
        for it in decoded:
            pprint.pprint(it)

