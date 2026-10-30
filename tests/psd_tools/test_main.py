import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from psd_tools import PSDImage
from psd_tools.__main__ import main, parse_args
from psd_tools.api.layers import Layer, PixelLayer

from .utils import full_name

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "argv",
    [
        ["export", full_name("layers/pixel-layer.psd")],
        ["export", full_name("layers/pixel-layer.psd[0]"), "--verbose"],
        ["show", full_name("layers/pixel-layer.psd")],
        ["debug", full_name("layers/pixel-layer.psd")],
        ["-h"],
        ["--version"],
    ],
)
def test_main(argv: list[str], tmpdir: Any) -> None:
    if argv[0] == "export":
        argv.append(tmpdir.join("output.png").strpath)

    with pytest.raises(SystemExit):
        main(argv)
        sys.exit()


def test_export_layers_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = full_name("layers/pixel-layer.psd")
    output = tmp_path / "assets"
    assert main(["export-layers", source, str(output), "--raw"]) == 0
    report = json.loads((output / "manifest.json").read_text())
    assert report["counts"]["exported"] > 0
    assert report["counts"]["error"] == 0
    assert "Exported" in capsys.readouterr().out
    assert list(output.rglob("*.png"))


def test_export_layers_dry_run_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "assets"
    assert (
        main(
            [
                "export-layers",
                full_name("group.psd"),
                str(output),
                "--dry-run",
                "--include-hidden",
                "--include-groups",
                "--full-canvas",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["counts"]["planned"] > 0
    assert report["include_hidden"] is True
    assert report["include_groups"] is True
    assert report["full_canvas"] is True
    assert not output.exists()


@pytest.mark.parametrize("extra", [["--include-groups"], ["--full-canvas"]])
def test_export_layers_cli_rejects_incompatible_options(extra: list[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        parse_args(["export-layers", "missing.psd", "out", "--raw", *extra])
    assert caught.value.code == 2


def test_export_layers_cli_help_does_not_open_document(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["export-layers", "--help"])
    assert caught.value.code == 0
    help_text = capsys.readouterr().out
    for option in [
        "--dry-run",
        "--raw",
        "--full-canvas",
        "--include-hidden",
        "--include-groups",
    ]:
        assert option in help_text


def test_export_layers_cli_reports_open_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    output = tmp_path / "assets"
    assert main(["export-layers", str(tmp_path / "missing.psd"), str(output)]) == 1
    assert "Batch export failed" in caplog.text
    assert not output.exists()


def test_export_layers_cli_refuses_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "assets"
    output.mkdir()
    sentinel = output / "keep"
    sentinel.write_text("unchanged")
    assert main(["export-layers", full_name("1layer.psd"), str(output)]) == 1
    assert sentinel.read_text() == "unchanged"
    assert list(output.iterdir()) == [sentinel]


def test_export_layers_cli_partial_failure_returns_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def missing_renderer(*args: Any, **kwargs: Any) -> None:
        raise ImportError("missing composite dependency")

    monkeypatch.setattr(Layer, "composite", missing_renderer)
    output = tmp_path / "assets"
    assert main(["export-layers", full_name("1layer.psd"), str(output)]) == 1
    report = json.loads((output / "manifest.json").read_text())
    assert report["counts"]["error"] > 0
    assert "failed" in capsys.readouterr().out


def test_export_layers_cli_full_canvas(tmp_path: Path) -> None:
    source = tmp_path / "source.psd"
    psd = PSDImage.new("RGB", (8, 6))
    PixelLayer.frompil(Image.new("RGB", (2, 2), "red"), psd, top=1, left=3)
    psd.save(source)
    output = tmp_path / "assets"
    assert main(["export-layers", str(source), str(output), "--full-canvas"]) == 0
    with Image.open(next(output.glob("*.png"))) as image:
        assert image.size == (8, 6)
        assert image.getpixel((3, 1)) == (255, 0, 0, 255)
        assert image.getchannel("A").getpixel((0, 0)) == 0


def test_module_entry_point_propagates_export_failure(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "psd_tools",
            "export-layers",
            str(tmp_path / "missing.psd"),
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Batch export failed" in result.stderr
    assert "Traceback" not in result.stderr


def test_module_entry_point_emits_complete_dry_run_json(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "psd_tools",
            "export-layers",
            full_name("group.psd"),
            str(tmp_path / "out"),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["schema_version"] == 1
    assert not (tmp_path / "out").exists()
