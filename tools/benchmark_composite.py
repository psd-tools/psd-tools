#!/usr/bin/env python
"""Benchmark compositing on a synthetic large document.

The fixture suite is too small to show the compositor's memory behaviour: the
largest canvas in ``tests/psd_files`` is 1200x628, while the cost that matters
is driven by the *number* of layers, since every layer, mask and effect is
expanded to the full viewport by ``paste()`` regardless of its own size.

Use this to get a before/after number for changes motivated by that behaviour
-- notably #212 (composite over the source-backdrop intersection) and #708
(normalise the backdrop at the API boundary).

Usage::

    uv run python tools/benchmark_composite.py
    uv run python tools/benchmark_composite.py --size 4000 --layers 100

Cost grows as canvas area x layer count, so raising either argument gets
expensive quickly -- the defaults are deliberately modest.

Reports wall time, peak Python allocation, and the total bytes returned by
``paste()`` expressed as a multiple of one full-canvas RGBA float32 buffer.
"""

from __future__ import annotations

import argparse
import importlib
import time
import tracemalloc
from typing import Any

from PIL import Image

from psd_tools import PSDImage


def build_document(size: int, layers: int, layer_size: int) -> PSDImage:
    """A ``size`` x ``size`` canvas holding ``layers`` small tiles."""
    psd = PSDImage.new(mode="RGB", size=(size, size))
    step = max(1, (size - layer_size) // max(1, layers))
    for index in range(layers):
        offset = (index * step) % max(1, size - layer_size)
        tile = Image.new(
            "RGBA",
            (layer_size, layer_size),
            (index * 5 % 256, index * 11 % 256, index * 17 % 256, 128),
        )
        psd.create_pixel_layer(image=tile, name=f"L{index}", top=offset, left=offset)
    return psd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=2000, help="canvas edge in px")
    parser.add_argument("--layers", type=int, default=50, help="number of layers")
    parser.add_argument("--layer-size", type=int, default=200, help="tile edge in px")
    args = parser.parse_args()

    # importlib, not a plain import: ``psd_tools.composite.composite`` is
    # shadowed by the ``composite`` *function* re-exported from the package
    # __init__, so ``from psd_tools.composite import composite`` binds the
    # function and never the module. Typed Any so patching paste() is allowed.
    module: Any = importlib.import_module("psd_tools.composite.composite")

    print(f"Building {args.size}x{args.size} with {args.layers} layers...")
    build_started = time.perf_counter()
    psd = build_document(args.size, args.layers, args.layer_size)
    print(f"  built in {time.perf_counter() - build_started:.1f}s")

    stats = {"calls": 0, "bytes": 0}
    original_paste = module.paste

    def counting_paste(viewport, bbox, values, background=None):  # type: ignore[no-untyped-def]
        result = original_paste(viewport, bbox, values, background)
        stats["calls"] += 1
        stats["bytes"] += result.nbytes
        return result

    module.paste = counting_paste
    try:
        tracemalloc.start()
        started = time.perf_counter()
        module.composite(psd)
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    finally:
        module.paste = original_paste

    canvas_bytes = args.size * args.size * 4 * 4  # RGBA float32
    print(f"\n  wall time         {elapsed:8.2f} s")
    print(f"  peak allocation   {peak / 1e6:8.1f} MB")
    print(f"  paste() calls     {stats['calls']:8d}")
    print(
        f"  paste() bytes     {stats['bytes'] / 1e6:8.1f} MB"
        f"  ({stats['bytes'] / canvas_bytes:.1f}x one RGBA float32 canvas)"
    )


if __name__ == "__main__":
    main()
