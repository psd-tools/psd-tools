import argparse
import logging
from typing import Optional, Union

from psd_tools import PSDImage
from psd_tools.api.layers import Layer
from psd_tools.version import __version__

try:
    from IPython.lib.pretty import pprint
except ImportError:
    from pprint import pprint

logger = logging.getLogger(__name__)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="psd-tools command line utility.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Be more verbose.")
    parser.add_argument("--version", action="version", version=__version__)

    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Export PSD or layer as PNG")
    export_parser.add_argument(
        "input_file",
        help="Input PSD file (optionally with layer index, e.g. file.psd[0])",
    )
    export_parser.add_argument("output_file", help="Output image file")

    show_parser = subparsers.add_parser("show", help="Show the file content")
    show_parser.add_argument("input_file", help="Input PSD file")

    debug_parser = subparsers.add_parser("debug", help="Show debug info for PSD file")
    debug_parser.add_argument("input_file", help="Input PSD file")

    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> Optional[int]:
    args = parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    if args.command == "export":
        input_parts = args.input_file.split("[")
        input_file = input_parts[0]
        if len(input_parts) > 1:
            indices = [int(x.rstrip("]")) for x in input_parts[1:]]
        else:
            indices = []
        layer: Union[PSDImage, Layer] = PSDImage.open(input_file)
        for index in indices:
            # PSDImage and Group both support indexing
            layer = layer[index]  # type: ignore[index]
        if isinstance(layer, PSDImage) and layer.has_preview():
            image = layer.topil()
        else:
            try:
                image = layer.composite()
            except ImportError as e:
                logger.error(str(e))
                return 1
        if image:
            image.save(args.output_file)

    elif args.command == "show":
        psd = PSDImage.open(args.input_file)
        pprint(psd)

    elif args.command == "debug":
        psd = PSDImage.open(args.input_file)
        pprint(psd._record)

    return None


if __name__ == "__main__":
    main()
