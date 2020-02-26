from __future__ import unicode_literals
import logging
import docopt

from psd_tools import PSDImage
from psd_tools.version import __version__

try:
    from IPython.lib.pretty import pprint
except ImportError:
    from pprint import pprint

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())


def main(argv=None):
    """
    psd-tools command line utility.

    Usage:
        psd-tools export <input_file> <output_file> [options]
        psd-tools show <input_file> [options]
        psd-tools debug <input_file> [options]
        psd-tools -h | --help
        psd-tools --version

    Options:
        -v --verbose                Be more verbose.

    Example:
        psd-tools show example.psd  # Show the file content
        psd-tools export example.psd example.png  # Export as PNG
        psd-tools export example.psd[0] example-0.png  # Export layer as PNG
    """

    args = docopt.docopt(main.__doc__, version=__version__, argv=argv)

    if args['--verbose']:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    if args['export']:
        input_parts = args['<input_file>'].split('[')
        input_file = input_parts[0]
        if len(input_parts) > 1:
            indices = [int(x.rstrip(']')) for x in input_parts[1:]]
        else:
            indices = []
        layer = PSDImage.open(input_file)
        for index in indices:
            layer = layer[index]
        if isinstance(layer, PSDImage) and layer.has_preview():
            image = layer.topil()
        else:
            image = layer.composite()
        image.save(args['<output_file>'])

    elif args['show']:
        psd = PSDImage.open(args['<input_file>'])
        pprint(psd)

    elif args['debug']:
        psd = PSDImage.open(args['<input_file>'])
        pprint(psd._record)


if __name__ == "__main__":
    main()
