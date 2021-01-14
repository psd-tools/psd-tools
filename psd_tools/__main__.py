# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, print_function
import logging
import docopt

import psd_tools.reader
import psd_tools.decoder
from psd_tools import PSDImage
from psd_tools.debug import pprint
from psd_tools._version import __version__

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())


def main():
    """
    psd-tools

    Usage:
        psd-tools convert <psd_filename> <out_filename> [options]
        psd-tools export_layer <psd_filename> <layer_index> <out_filename> \
[options]
        psd-tools debug <filename> [options]
        psd-tools -h | --help
        psd-tools --version

    Options:
        -v --verbose                Be more verbose.
        --encoding <encoding>       Text encoding [default: utf8].

    """
    args = docopt.docopt(main.__doc__, version=__version__)

    if args['--verbose']:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    encoding = args['--encoding']

    if args['convert']:
        psd = PSDImage.load(args['<psd_filename>'], encoding=encoding)
        im = psd.as_PIL()
        im.save(args['<out_filename>'])

    elif args['export_layer']:
        psd = PSDImage.load(args['<psd_filename>'], encoding=encoding)
        index = int(args['<layer_index>'])
        im = psd.layers[index].as_PIL()
        im.save(args['<out_filename>'])
        print(psd.layers)

        psd.as_PIL()

    elif args['debug']:
        psd = PSDImage.load(args['<filename>'], encoding=encoding)

        print("\nHeader\n------")
        print(psd.decoded_data.header)
        print("\nDecoded data\n-----------")
        pprint(psd.decoded_data)
        print("\nLayers\n------")
        psd.print_tree()


if __name__ == "__main__":
    main()
