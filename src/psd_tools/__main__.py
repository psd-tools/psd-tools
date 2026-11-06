"""Command line interface."""

import argparse
import json
import logging
import sys

from psd_tools import PSDImage
from psd_tools.api.export import export_layers
from psd_tools.api.layers import Layer
from psd_tools.version import __version__

try:
    from IPython.lib.pretty import pprint
except ImportError:
    from pprint import pprint

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
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

    layers_parser = subparsers.add_parser(
        "export-layers", help="Export layers as PNGs with a JSON manifest"
    )
    layers_parser.add_argument("input_file", help="Input PSD or PSB file")
    layers_parser.add_argument(
        "output_dir", help="New output directory (must not exist)"
    )
    layers_parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden layers and descendants",
    )
    layers_parser.add_argument(
        "--include-groups",
        action="store_true",
        help="Also export group/artboard composites",
    )
    layers_parser.add_argument(
        "--raw",
        action="store_true",
        help="Export stored pixels without masks or effects",
    )
    layers_parser.add_argument(
        "--full-canvas", action="store_true", help="Render each PNG at document size"
    )
    layers_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the JSON plan without rendering or writing",
    )

    show_parser = subparsers.add_parser("show", help="Show the file content")
    show_parser.add_argument("input_file", help="Input PSD file")

    debug_parser = subparsers.add_parser("debug", help="Show debug info for PSD file")
    debug_parser.add_argument("input_file", help="Input PSD file")

    args = parser.parse_args(argv)
    if (
        args.command == "export-layers"
        and args.raw
        and (args.include_groups or args.full_canvas)
    ):
        layers_parser.error(
            "--raw cannot be combined with --include-groups or --full-canvas"
        )
    return args


def main(argv: list[str] | None = None) -> int | None:
    """Run the command line interface and return the exit status."""
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
        layer: PSDImage | Layer = PSDImage.open(input_file)
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

    elif args.command == "export-layers":
        try:
            report = export_layers(
                PSDImage.open(args.input_file),
                args.output_dir,
                include_hidden=args.include_hidden,
                include_groups=args.include_groups,
                mode="raw" if args.raw else "composite",
                full_canvas=args.full_canvas,
                dry_run=args.dry_run,
            )
        except (ValueError, OSError, ImportError) as error:
            logger.error("Batch export failed: %s", error)
            return 1
        if args.dry_run:
            print(json.dumps(report, indent=2))
        else:
            counts = report["counts"]
            print(
                f"Exported {counts['exported']} layer(s); skipped {counts['skipped']}; "
                f"failed {counts['error']}. Manifest: {args.output_dir!r}/manifest.json"
            )
        return 1 if report["counts"]["error"] else 0

    elif args.command == "show":
        psd = PSDImage.open(args.input_file)
        pprint(psd)

    elif args.command == "debug":
        psd = PSDImage.open(args.input_file)
        pprint(psd._record)

    return None


if __name__ == "__main__":
    sys.exit(main())
