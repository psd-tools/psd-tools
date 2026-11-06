"""Batch PNG export with a manifest mapping images back to their layers."""

import json
import unicodedata
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Literal, TypedDict

from PIL import Image

from psd_tools.api.layers import AdjustmentLayer, Artboard, Group, Layer
from psd_tools.api.psd_image import PSDImage


class LayerExportEntry(TypedDict):
    """Describe one layer and its planned or completed export."""

    index: list[int]
    layer_id: int
    name: str
    kind: str
    visible: bool
    effective_visible: bool
    bbox: list[int]
    viewport: list[int]
    filename: str | None
    status: Literal["planned", "exported", "skipped", "error"]
    reason: str | None
    image_size: list[int] | None


class LayerExportReport(TypedDict):
    """Describe an export batch, including skipped layers and individual errors."""

    schema_version: int
    size: list[int]
    color_mode: str
    depth: int
    mode: Literal["composite", "raw"]
    full_canvas: bool
    include_hidden: bool
    include_groups: bool
    counts: dict[str, int]
    layers: list[LayerExportEntry]


def _safe_name(name: str) -> str:
    """Make a bounded, portable filename component from a layer name."""
    name = "".join(
        "_"
        if char in '<>:"/\\|?*' or unicodedata.category(char).startswith("C")
        else char
        for char in name
    )
    # Limit bytes, not characters, to leave room for the index and extension
    # on filesystems with a 255-byte component limit.
    return (
        name.encode("utf-8")[:80].decode("utf-8", errors="ignore").strip(" .")
        or "layer"
    )


def _walk_layers(
    parent: PSDImage | Group,
    indices: tuple[int, ...] = (),
    directory: PurePosixPath = PurePosixPath(),
) -> Iterator[tuple[Layer, tuple[int, ...], PurePosixPath]]:
    """Walk the layer tree in storage order, assigning unique relative paths."""
    for index, layer in enumerate(parent):
        path = directory / f"{index:04d}-{_safe_name(layer.name)}"
        position = (*indices, index)
        yield layer, position, path
        if isinstance(layer, Group):
            yield from _walk_layers(layer, position, path)


def _include_layer(layer: Layer) -> bool:
    """Include hidden layers without changing their visibility flags."""
    return True


def _make_plan(
    psd: PSDImage,
    include_hidden: bool,
    include_groups: bool,
    mode: Literal["composite", "raw"],
    full_canvas: bool,
) -> list[tuple[Layer, LayerExportEntry]]:
    """Build an export plan without decoding or rendering layer pixels."""
    plan: list[tuple[Layer, LayerExportEntry]] = []
    for layer, index, path in _walk_layers(psd):
        bbox = layer.bbox
        # A hidden group's ordinary bbox excludes its hidden descendants.
        # Artboards have their own explicit viewport, which must stay intact.
        if (
            include_hidden
            and isinstance(layer, Group)
            and not isinstance(layer, Artboard)
        ):
            bbox = Group.extract_bbox(layer, include_invisible=True)
        viewport = (0, 0, psd.width, psd.height) if full_canvas else bbox
        reason = None
        if not include_hidden and not layer.is_visible():
            reason = "hidden"
        elif isinstance(layer, Group) and not include_groups:
            reason = "group"
        elif isinstance(layer, AdjustmentLayer):
            reason = "adjustment_requires_backdrop"
        elif mode == "raw" and not layer.has_pixels():
            reason = "no_pixels"
        elif viewport[0] >= viewport[2] or viewport[1] >= viewport[3]:
            reason = "empty_bounds"
        entry: LayerExportEntry = {
            "index": list(index),
            "layer_id": layer.layer_id,
            "name": layer.name,
            "kind": layer.kind,
            "visible": layer.visible,
            "effective_visible": layer.is_visible(),
            "bbox": list(bbox),
            "viewport": list(viewport),
            "filename": f"{path.as_posix()}.png" if reason is None else None,
            "status": "planned" if reason is None else "skipped",
            "reason": reason,
            "image_size": None,
        }
        plan.append((layer, entry))
    return plan


def _save_png(image: Image.Image, destination: Path) -> None:
    """Write a new PNG and remove only our own file if encoding fails."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Opening outside the try prevents removing an existing file if the
    # exclusive open fails. A failed encoder must not leave a truncated PNG.
    stream = destination.open("xb")
    try:
        with stream:
            if image.mode == "CMYK":
                with image.convert("RGB") as converted:
                    converted.save(stream, format="PNG")
            else:
                image.save(stream, format="PNG")
    except BaseException:
        destination.unlink()
        raise


def export_layers(
    psd: PSDImage,
    output_dir: str | Path,
    *,
    include_hidden: bool = False,
    include_groups: bool = False,
    mode: Literal["composite", "raw"] = "composite",
    full_canvas: bool = False,
    dry_run: bool = False,
) -> LayerExportReport:
    """
    Export document layers to PNG files and write a JSON manifest.

    Traverse groups recursively, retaining their directory structure. Prefix
    filenames with sibling indices so duplicate, empty, or sanitized names
    cannot collide. By default only visible non-group layers are exported.
    Adjustment layers are listed as skipped because they need a backdrop;
    their effects can be included in an exported group composite.

    Each image uses the existing ``composite()`` or ``topil()`` implementation
    and inherits its rendering, precision, and color-management limitations.
    Composite output includes masks and associated clipping layers. Raw output
    ignores those and uses the stored pixels. CMYK output that remains CMYK
    after ICC handling is converted to RGB with Pillow for PNG compatibility.

    :param psd: The document to export, without modifying its layer tree.
    :param output_dir: A new directory. Its parent must already exist.
        Existing directories, files, and symlinks are rejected.
    :param include_hidden: Also export hidden layers and hidden descendants.
    :param include_groups: Also export a composite for each group or artboard.
    :param mode: ``"composite"`` (default) or ``"raw"`` for stored layer pixels.
    :param full_canvas: Render each image at document size instead of its bounds.
        Only available in composite mode.
    :param dry_run: Return the plan without rendering or writing any files.
    :return: A JSON-compatible report, also written to ``manifest.json`` for
        an actual export. Expected per-layer render and PNG encoding failures
        are recorded as ``error`` entries while other layers continue.
        Directory creation and manifest-write failures raise to the caller.
    :raises ValueError: If the mode is invalid, or raw mode is combined with
        group previews or full-canvas rendering.
    :raises OSError: If the output directory cannot be created or the manifest
        cannot be written. Successfully exported images are retained.

    Example::

        from psd_tools.api.export import export_layers

        report = export_layers(psd, "assets", include_groups=True)
        print(report["counts"])
    """
    if mode not in ("composite", "raw"):
        raise ValueError("mode must be 'composite' or 'raw'")
    if mode == "raw" and (include_groups or full_canvas):
        raise ValueError("raw export does not support group previews or full_canvas")

    plan = _make_plan(psd, include_hidden, include_groups, mode, full_canvas)
    output = Path(output_dir)
    if not dry_run:
        # Exclusive directory creation also refuses dangling symlinks.
        output.mkdir()
        for layer, entry in plan:
            if entry["filename"] is None:
                continue
            image = None
            try:
                if mode == "raw":
                    image = layer.topil()
                else:
                    left, top, right, bottom = entry["viewport"]
                    image = layer.composite(
                        viewport=(left, top, right, bottom),
                        layer_filter=_include_layer if include_hidden else None,
                    )
                if image is None:
                    entry["status"] = "skipped"
                    entry["reason"] = "no_image"
                    continue
                _save_png(image, output / entry["filename"])
                entry["status"] = "exported"
                entry["image_size"] = list(image.size)
            except (ValueError, OSError, ImportError) as error:
                entry["status"] = "error"
                entry["reason"] = f"{type(error).__name__}: {error}"
            finally:
                if image is not None:
                    image.close()

    entries = [entry for _, entry in plan]
    report: LayerExportReport = {
        "schema_version": 1,
        "size": list(psd.size),
        "color_mode": psd.color_mode.name,
        "depth": psd.depth,
        "mode": mode,
        "full_canvas": full_canvas,
        "include_hidden": include_hidden,
        "include_groups": include_groups,
        "counts": {
            status: sum(entry["status"] == status for entry in entries)
            for status in ("planned", "exported", "skipped", "error")
        },
        "layers": entries,
    }
    if not dry_run:
        with (output / "manifest.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    return report
