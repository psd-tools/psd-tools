import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from psd_tools import PSDImage
from psd_tools.api.export import export_layers
from psd_tools.api.layers import Group, Layer, PixelLayer
from psd_tools.constants import BlendMode

from ..utils import full_name


@pytest.fixture
def document() -> PSDImage:
    psd = PSDImage.new("RGB", (12, 10))
    PixelLayer.frompil(
        Image.new("RGBA", (3, 2), (255, 0, 0, 255)),
        parent=psd,
        name="Red",
        left=1,
        top=2,
    )
    group = Group.new(psd, name="Assets")
    PixelLayer.frompil(
        Image.new("RGBA", (2, 3), (0, 255, 0, 255)),
        parent=group,
        name="Green",
        left=5,
        top=4,
    )
    hidden = Group.new(group, name="Hidden")
    PixelLayer.frompil(
        Image.new("RGBA", (2, 2), (0, 0, 255, 255)),
        parent=hidden,
        name="Blue",
        left=8,
        top=1,
    )
    hidden.visible = False
    return psd


def test_export_layers_hierarchy_manifest_and_pixels(
    document: PSDImage, tmp_path: Path
) -> None:
    output = tmp_path / "assets"
    report = export_layers(document, output)

    assert report == json.loads((output / "manifest.json").read_text())
    assert report["schema_version"] == 1
    assert report["size"] == [12, 10]
    assert report["color_mode"] == "RGB"
    assert report["depth"] == 8
    assert report["counts"] == {"planned": 0, "exported": 2, "skipped": 3, "error": 0}
    assert [entry["index"] for entry in report["layers"]] == [
        [0],
        [1],
        [1, 0],
        [1, 1],
        [1, 1, 0],
    ]
    assert {p.relative_to(output).as_posix() for p in output.rglob("*.png")} == {
        "0000-Red.png",
        "0001-Assets/0000-Green.png",
    }
    red = report["layers"][0]
    assert red["bbox"] == [1, 2, 4, 4]
    assert red["viewport"] == red["bbox"]
    assert red["image_size"] == [3, 2]
    assert red["layer_id"] == document[0].layer_id
    with Image.open(output / "0000-Red.png") as image:
        assert image.size == (3, 2)
        assert image.getpixel((0, 0)) == (255, 0, 0, 255)
    assert report["layers"][1]["reason"] == "group"
    assert report["layers"][-1]["reason"] == "hidden"
    assert report["layers"][-1]["visible"] is True
    assert report["layers"][-1]["effective_visible"] is False


def test_dry_run_never_renders_or_writes(
    document: PSDImage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected(*args: Any, **kwargs: Any) -> None:
        pytest.fail("dry run decoded or rendered pixels")

    monkeypatch.setattr(Layer, "composite", unexpected)
    monkeypatch.setattr(Group, "composite", unexpected)
    monkeypatch.setattr(Layer, "topil", unexpected)
    output = tmp_path / "missing-parent" / "assets"
    report = export_layers(document, output, dry_run=True, include_groups=True)
    assert report["counts"] == {"planned": 3, "exported": 0, "skipped": 2, "error": 0}
    assert not output.parent.exists()
    assert all(entry["image_size"] is None for entry in report["layers"])
    assert json.loads(json.dumps(report)) == report
    raw = export_layers(document, output, mode="raw", dry_run=True)
    assert raw["counts"]["planned"] == 2


def test_plan_filenames_match_export(document: PSDImage, tmp_path: Path) -> None:
    output = tmp_path / "assets"
    planned = export_layers(document, output, dry_run=True)
    actual = export_layers(document, output)
    assert [entry["filename"] for entry in planned["layers"]] == [
        entry["filename"] for entry in actual["layers"]
    ]


def test_include_hidden_and_groups_preserves_visibility(
    document: PSDImage, tmp_path: Path
) -> None:
    original = [(layer.name, layer.visible) for layer in document.descendants()]
    # Prime group caches while the nested group is hidden.
    assert document[1].bbox == (5, 4, 7, 7)
    output = tmp_path / "assets"
    report = export_layers(document, output, include_hidden=True, include_groups=True)
    assert report["counts"]["exported"] == 5
    assert report["counts"]["error"] == 0
    assert [(layer.name, layer.visible) for layer in document.descendants()] == original
    assert report["layers"][1]["viewport"] == [5, 1, 10, 7]
    assert report["layers"][3]["viewport"] == [8, 1, 10, 3]
    with Image.open(output / "0001-Assets/0001-Hidden.png") as image:
        assert image.size == (2, 2)
        assert image.getpixel((0, 0)) == (0, 0, 255, 255)
    with Image.open(output / "0001-Assets.png") as image:
        assert image.size == (5, 6)
        assert image.getpixel((3, 0)) == (0, 0, 255, 255)


def test_group_previews_keep_hidden_children_hidden(
    document: PSDImage, tmp_path: Path
) -> None:
    report = export_layers(document, tmp_path / "assets", include_groups=True)
    assert report["counts"]["exported"] == 3
    with Image.open(tmp_path / "assets/0001-Assets.png") as image:
        assert image.size == (2, 3)
        assert image.getpixel((0, 0)) == (0, 255, 0, 255)


def test_hidden_isolated_groups_keep_their_contents(
    document: PSDImage, tmp_path: Path
) -> None:
    group = document[1]
    assert isinstance(group, Group)
    group.blend_mode = BlendMode.NORMAL
    group[1].blend_mode = BlendMode.NORMAL
    report = export_layers(
        document, tmp_path / "assets", include_hidden=True, include_groups=True
    )
    assert report["counts"]["error"] == 0
    with Image.open(tmp_path / "assets/0001-Assets.png") as image:
        assert image.getpixel((3, 0)) == (0, 0, 255, 255)
    with Image.open(tmp_path / "assets/0001-Assets/0001-Hidden.png") as image:
        assert image.getpixel((0, 0)) == (0, 0, 255, 255)


def test_artboard_plan_keeps_explicit_bounds(tmp_path: Path) -> None:
    psd = PSDImage.open(full_name("artboard.psd"))
    report = export_layers(
        psd, tmp_path / "assets", include_groups=True, include_hidden=True, dry_run=True
    )
    artboards = [entry for entry in report["layers"] if entry["kind"] == "artboard"]
    assert artboards
    for entry in artboards:
        layer: Any = psd
        for index in entry["index"]:
            layer = layer[index]
        assert entry["viewport"] == list(layer.bbox)
        assert entry["status"] == "planned"


def test_raw_export_does_not_invoke_compositor(
    document: PSDImage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def render(*args: Any, **kwargs: Any) -> None:
        pytest.fail("raw export invoked the compositor")

    monkeypatch.setattr(Layer, "composite", render)
    report = export_layers(document, tmp_path / "raw", mode="raw")
    assert report["counts"]["exported"] == 2


def test_full_canvas_positions_and_off_canvas_clipping(tmp_path: Path) -> None:
    psd = PSDImage.new("RGB", (6, 5))
    PixelLayer.frompil(Image.new("RGBA", (3, 3), "red"), psd, left=-1, top=2)
    PixelLayer.frompil(Image.new("RGBA", (2, 2), "blue"), psd, left=10, top=10)
    output = tmp_path / "canvas"
    report = export_layers(psd, output, full_canvas=True)
    assert report["counts"]["exported"] == 2
    for entry in report["layers"]:
        assert entry["viewport"] == [0, 0, 6, 5]
        assert entry["image_size"] == [6, 5]
    with Image.open(output / str(report["layers"][0]["filename"])) as image:
        assert image.getpixel((0, 2)) == (255, 0, 0, 255)
        assert image.getpixel((1, 4)) == (255, 0, 0, 255)
        assert image.getchannel("A").getpixel((2, 2)) == 0
    with Image.open(output / str(report["layers"][1]["filename"])) as image:
        assert image.getchannel("A").getbbox() is None


def test_raw_exports_stored_pixels_without_opacity(
    document: PSDImage, tmp_path: Path
) -> None:
    document[0].opacity = 64
    output = tmp_path / "raw"
    report = export_layers(document, output, mode="raw", include_hidden=True)
    assert report["mode"] == "raw"
    assert report["counts"]["exported"] == 3
    with Image.open(output / "0000-Red.png") as image:
        assert image.getpixel((0, 0)) == (255, 0, 0, 255)
    composite = export_layers(document, tmp_path / "composite")
    assert composite["counts"]["error"] == 0
    with Image.open(tmp_path / "composite/0000-Red.png") as image:
        assert image.getchannel("A").getpixel((0, 0)) == 64


@pytest.mark.parametrize("mode", ["raw", "composite"])
def test_cmyk_png_conversion(tmp_path: Path, mode: Any) -> None:
    psd = PSDImage.new("CMYK", (2, 2))
    PixelLayer.frompil(Image.new("CMYK", (2, 2), (0, 255, 255, 0)), psd)
    report = export_layers(psd, tmp_path / "assets", mode=mode)
    assert report["counts"]["exported"] == 1
    with Image.open(
        tmp_path / "assets" / str(report["layers"][0]["filename"])
    ) as image:
        assert image.mode == "RGB"
        assert image.getpixel((0, 0)) == (255, 0, 0)


def test_empty_groups_and_adjustments_have_explicit_skip_reasons(
    tmp_path: Path,
) -> None:
    psd = PSDImage.open(full_name("layers/brightness-contrast.psd"))
    Group.new(psd, name="Empty")
    output = tmp_path / "assets"
    report = export_layers(psd, output, include_groups=True)
    assert report["layers"][0]["reason"] == "adjustment_requires_backdrop"
    assert report["layers"][-1]["reason"] == "empty_bounds"
    assert report["counts"]["error"] == 0


def test_empty_document_still_writes_manifest(tmp_path: Path) -> None:
    report = export_layers(PSDImage.new("RGB", (4, 4)), tmp_path / "empty")
    assert report["layers"] == []
    assert all(count == 0 for count in report["counts"].values())
    assert list((tmp_path / "empty").iterdir()) == [tmp_path / "empty/manifest.json"]


def test_names_are_safe_unique_and_preserved_in_manifest(tmp_path: Path) -> None:
    names = [
        "same",
        "same",
        "a/b",
        "a\\b",
        "../../escape",
        "/absolute",
        "C:\\outside",
        "CON",
        "NUL",
        "",
        ".",
        "..",
        "quote:<name>|?*",
        "line\n\x00\x1bname",
        "文件名😀",
        "long" * 60,
        "长" * 100,
        "\ud800",
    ]
    psd = PSDImage.new("RGB", (1, 1))
    for name in names:
        layer = PixelLayer.frompil(Image.new("RGB", (1, 1), "red"), psd)
        layer.name = name
    output = tmp_path / "assets"
    report = export_layers(psd, output, mode="raw")
    assert report["counts"]["exported"] == len(names)
    assert [entry["name"] for entry in report["layers"]] == names
    files = list(output.glob("*.png"))
    assert len(files) == len(names)
    assert len({path.name.casefold() for path in files}) == len(names)
    for path in files:
        assert len(path.name.encode("utf-8")) <= 89
        assert not any(char in path.name for char in '<>:"/\\|?*\n\x00\x1b')
    assert sorted(tmp_path.iterdir()) == [output]
    assert (
        json.loads((output / "manifest.json").read_text())["layers"] == report["layers"]
    )


@pytest.mark.parametrize("existing", ["directory", "file", "symlink", "dangling"])
def test_existing_output_is_never_overwritten(
    document: PSDImage, tmp_path: Path, existing: str
) -> None:
    output = tmp_path / "assets"
    if existing == "directory":
        output.mkdir()
        (output / "keep").write_text("unchanged")
    elif existing == "file":
        output.write_text("unchanged")
    else:
        target = tmp_path / "target"
        if existing == "symlink":
            target.mkdir()
        try:
            output.symlink_to(target, target_is_directory=True)
        except OSError:
            pytest.skip("symlinks are not supported")
    with pytest.raises(FileExistsError):
        export_layers(document, output)
    if existing == "directory":
        assert (output / "keep").read_text() == "unchanged"
        assert list(output.iterdir()) == [output / "keep"]
    elif existing == "file":
        assert output.read_text() == "unchanged"
    else:
        assert output.is_symlink()


def test_missing_output_parent_is_reported(document: PSDImage, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        export_layers(document, tmp_path / "missing/assets")
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize(
    "error",
    [ValueError("bad pixels"), OSError("bad data"), ImportError("missing renderer")],
)
def test_render_failures_are_recorded_and_other_layers_continue(
    document: PSDImage,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    original = Layer.composite

    def render(layer: Layer, **kwargs: Any) -> Image.Image | None:
        if layer.name == "Red":
            raise error
        return original(layer, **kwargs)

    monkeypatch.setattr(Layer, "composite", render)
    report = export_layers(document, tmp_path / "assets")
    assert report["counts"]["error"] == 1
    assert report["counts"]["exported"] == 1
    assert report["layers"][0]["reason"] == f"{type(error).__name__}: {error}"
    assert not (tmp_path / "assets/0000-Red.png").exists()
    assert (tmp_path / "assets/0001-Assets/0000-Green.png").exists()
    assert json.loads((tmp_path / "assets/manifest.json").read_text()) == report


def test_none_image_is_skipped(
    document: PSDImage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Layer, "topil", lambda *args, **kwargs: None)
    report = export_layers(document, tmp_path / "assets", mode="raw")
    assert report["counts"]["exported"] == 0
    assert report["layers"][0]["status"] == "skipped"
    assert report["layers"][0]["reason"] == "no_image"


def test_failed_png_is_removed_and_image_is_closed(
    document: PSDImage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    images: list[Image.Image] = []

    def render(*args: Any, **kwargs: Any) -> Image.Image:
        image = Image.new("RGBA", (1, 1))
        images.append(image)
        return image

    def save(image: Image.Image, fp: Any, **kwargs: Any) -> None:
        fp.write(b"incomplete PNG")
        raise OSError("encoder failure")

    monkeypatch.setattr(Layer, "composite", render)
    monkeypatch.setattr(Image.Image, "save", save)
    report = export_layers(document, tmp_path / "assets")
    assert report["counts"]["error"] == 2
    assert not list((tmp_path / "assets").rglob("*.png"))
    for image in images:
        with pytest.raises(ValueError, match="closed"):
            image.getpixel((0, 0))


def test_exclusive_png_open_does_not_remove_a_conflicting_file(
    document: PSDImage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "assets"
    original = Layer.composite

    def render(layer: Layer, **kwargs: Any) -> Image.Image | None:
        if layer.name == "Red":
            (output / "0000-Red.png").write_bytes(b"external file")
        return original(layer, **kwargs)

    monkeypatch.setattr(Layer, "composite", render)
    report = export_layers(document, output)
    assert report["counts"]["error"] == 1
    assert (output / "0000-Red.png").read_bytes() == b"external file"


def test_programming_errors_are_not_silently_degraded(
    document: PSDImage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def render(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("unexpected invariant")

    monkeypatch.setattr(Layer, "composite", render)
    with pytest.raises(AssertionError, match="unexpected invariant"):
        export_layers(document, tmp_path / "assets")


def test_manifest_failure_preserves_successful_images(
    document: PSDImage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = Path.open

    def open_file(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path.name == "manifest.json":
            raise OSError("manifest write failed")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_file)
    with pytest.raises(OSError, match="manifest write failed"):
        export_layers(document, tmp_path / "assets")
    assert len(list((tmp_path / "assets").rglob("*.png"))) == 2


@pytest.mark.parametrize(
    "options",
    [
        {"mode": "invalid"},
        {"mode": "raw", "include_groups": True},
        {"mode": "raw", "full_canvas": True},
    ],
)
def test_invalid_options_fail_before_writing(
    document: PSDImage, tmp_path: Path, options: Any
) -> None:
    with pytest.raises(ValueError):
        export_layers(document, tmp_path / "assets", **options)
    assert not (tmp_path / "assets").exists()


@pytest.mark.parametrize(
    "filename", ["1layer.psd", "1layer.psb", "group.psd", "hidden-layer.psd"]
)
def test_real_documents_are_not_modified(tmp_path: Path, filename: str) -> None:
    psd = PSDImage.open(full_name(filename))
    original = psd._record.tobytes()
    report = export_layers(psd, tmp_path / "assets", mode="raw", include_hidden=True)
    assert report["counts"]["error"] == 0
    assert report["counts"]["exported"] > 0
    assert psd._record.tobytes() == original
    assert not psd.is_updated()
