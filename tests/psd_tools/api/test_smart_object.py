import logging
import sys
from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock

import pytest

from psd_tools.api.psd_image import PSDImage
from psd_tools.api.layers import SmartObjectLayer
from psd_tools.api.smart_object import SmartObject
from psd_tools.constants import LinkedLayerType

from ..utils import full_name

logger = logging.getLogger(__name__)


@pytest.fixture
def embedded_object() -> Iterator[SmartObject]:
    psdimage = PSDImage.open(full_name("placedLayer.psd"))
    layer = psdimage[3]
    assert isinstance(layer, SmartObjectLayer)
    yield layer.smart_object


@pytest.fixture
def external_object() -> Iterator[SmartObject]:
    psdimage = PSDImage.open(full_name("placedLayer.psd"))
    layer = psdimage[1]
    assert isinstance(layer, SmartObjectLayer)
    yield layer.smart_object


@pytest.fixture
def linked_layer_png() -> Iterator[bytes]:
    with open(full_name("linked-layer.png"), "rb") as f:
        yield f.read()


def test_smart_object_data(
    embedded_object: SmartObject, linked_layer_png: bytes, tmp_path: Path
) -> None:
    assert embedded_object.kind in "data"
    assert embedded_object.filename == "linked-layer.png"
    assert embedded_object.filetype == "png"
    assert embedded_object.unique_id == "5a96c404-ab9c-1177-97ef-96ca454b82b7"
    assert embedded_object.is_psd() is False
    assert embedded_object.warp
    assert embedded_object.resolution == 144.0
    assert embedded_object.filesize == 17272
    assert embedded_object.data == linked_layer_png
    with embedded_object.open() as f:
        assert f.read() == linked_layer_png
    tmppath = tmp_path / embedded_object.filename
    embedded_object.save(str(tmppath))


def test_smart_object_external(
    external_object: SmartObject, linked_layer_png: bytes
) -> None:
    assert external_object.kind in "external"
    assert external_object.filename == "linked-layer.png"
    assert external_object.filetype == "png"
    assert external_object.unique_id == "5a96c402-ab9c-1177-97ef-96ca454b82b7"
    assert external_object.is_psd() is False
    assert external_object.warp
    assert external_object.resolution == 144.0
    assert external_object.filesize == 17272
    with external_object.open(full_name("")) as f:
        assert f.read() == linked_layer_png


# ---------------------------------------------------------------------------
# Security tests — GHSA-2rmg-vrx8-9j2f
# ---------------------------------------------------------------------------


def _make_data_smart_object(
    embedded_filename: str, payload: bytes = b"pwned"
) -> SmartObject:
    """Build a SmartObject whose _data mimics a DATA-kind LinkedLayer."""
    data_mock = MagicMock()
    data_mock.kind = LinkedLayerType.DATA
    data_mock.filename = embedded_filename
    data_mock.data = payload

    config_mock = MagicMock()
    config_mock.data = {b"Idnt": MagicMock(value="test-uuid\x00")}

    so = object.__new__(SmartObject)
    so._data = data_mock
    so._config = config_mock
    so._placed_layer = None
    return so


def _make_external_smart_object(
    full_path: str, rel_path: str, embedded_filename: str = "linked.png"
) -> SmartObject:
    """Build a SmartObject whose _data mimics an EXTERNAL-kind LinkedLayer."""
    linked_file = {
        b"fullPath": MagicMock(value=full_path),
        b"relPath": MagicMock(value=rel_path),
    }
    data_mock = MagicMock()
    data_mock.kind = LinkedLayerType.EXTERNAL
    data_mock.filename = embedded_filename
    data_mock.linked_file = linked_file

    config_mock = MagicMock()
    config_mock.data = {b"Idnt": MagicMock(value="test-uuid\x00")}

    so = object.__new__(SmartObject)
    so._data = data_mock
    so._config = config_mock
    so._placed_layer = None
    return so


class TestSaveSecurity:
    """SmartObject.save() must not write outside the target directory."""

    def test_safe_basename_writes_inside_directory(self, tmp_path: Path) -> None:
        so = _make_data_smart_object("photo.png", b"data")
        so.save(directory=str(tmp_path))
        assert (tmp_path / "photo.png").read_bytes() == b"data"

    def test_traversal_basename_is_stripped(self, tmp_path: Path) -> None:
        """../../escape.bin should write as escape.bin inside tmp_path."""
        so = _make_data_smart_object("../../escape.bin", b"data")
        so.save(directory=str(tmp_path))
        assert (tmp_path / "escape.bin").read_bytes() == b"data"
        # nothing escaped
        assert not (tmp_path.parent.parent / "escape.bin").exists()

    def test_absolute_embedded_path_is_stripped(self, tmp_path: Path) -> None:
        """An absolute embedded path is reduced to its basename inside directory."""
        # Use a sentinel file outside tmp_path as the "absolute" target — hermetic,
        # no system file reads, works in sandboxed CI.
        sentinel = tmp_path.parent / "sentinel.bin"
        sentinel.write_bytes(b"original")
        try:
            so = _make_data_smart_object(str(sentinel), b"data")
            so.save(directory=str(tmp_path))
            # basename of sentinel is written inside tmp_path
            assert (tmp_path / "sentinel.bin").read_bytes() == b"data"
            # the original file outside tmp_path is untouched
            assert sentinel.read_bytes() == b"original"
        finally:
            sentinel.unlink(missing_ok=True)

    def test_empty_basename_raises(self, tmp_path: Path) -> None:
        """A name that has no basename (e.g. trailing slash) must raise."""
        so = _make_data_smart_object("../../", b"data")
        with pytest.raises(ValueError, match="no safe basename"):
            so.save(directory=str(tmp_path))

    def test_explicit_filename_bypasses_sanitization(self, tmp_path: Path) -> None:
        """When caller provides explicit filename, it is used as-is."""
        dest = tmp_path / "explicit.bin"
        so = _make_data_smart_object("../../evil.bin", b"data")
        so.save(filename=str(dest))
        assert dest.read_bytes() == b"data"

    def test_default_directory_is_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        so = _make_data_smart_object("output.bin", b"data")
        so.save()
        assert (tmp_path / "output.bin").read_bytes() == b"data"

    def test_dot_basename_raises_value_error(self, tmp_path: Path) -> None:
        """filename='.' must raise ValueError, not IsADirectoryError."""
        so = _make_data_smart_object(".", b"data")
        with pytest.raises(ValueError, match="no safe basename"):
            so.save(directory=str(tmp_path))

    def test_external_save_malicious_fullpath_with_external_dir_raises(
        self, tmp_path: Path
    ) -> None:
        """Malicious fullPath outside external_dir must not be read."""
        system_file = (
            "/etc/hosts"
            if sys.platform != "win32"
            else "C:\\Windows\\System32\\drivers\\etc\\hosts"
        )
        if not Path(system_file).exists():
            pytest.skip(f"{system_file} not available on this system")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        so = _make_external_smart_object(system_file, "benign.png", "benign.png")
        # fullPath escapes external_dir; relPath doesn't exist → should not write
        with pytest.raises((ValueError, FileNotFoundError)):
            so.save(directory=str(out_dir), external_dir=str(out_dir))
        assert list(out_dir.iterdir()) == []

    def test_external_save_with_matching_external_dir_succeeds(
        self, tmp_path: Path
    ) -> None:
        """External save works when source is inside external_dir."""
        source_dir = tmp_path / "sources"
        source_dir.mkdir()
        (source_dir / "asset.png").write_bytes(b"asset-bytes")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        so = _make_external_smart_object(
            str(source_dir / "asset.png"), "asset.png", "asset.png"
        )
        so.save(directory=str(out_dir), external_dir=str(source_dir))
        assert (out_dir / "asset.png").read_bytes() == b"asset-bytes"


class TestOpenSecurity:
    """SmartObject.open() external kind must not read outside external_dir."""

    def test_relative_path_inside_external_dir(self, tmp_path: Path) -> None:
        target = tmp_path / "asset.png"
        target.write_bytes(b"asset")
        so = _make_external_smart_object("", "asset.png")
        with so.open(external_dir=str(tmp_path)) as f:
            assert f.read() == b"asset"

    def test_relpath_traversal_raises(self, tmp_path: Path) -> None:
        so = _make_external_smart_object("", "../../etc/passwd")
        with pytest.raises(ValueError, match="escapes external_dir"):
            with so.open(external_dir=str(tmp_path)) as f:
                f.read()

    def test_fullpath_outside_external_dir_falls_back_to_relpath(
        self, tmp_path: Path
    ) -> None:
        """fullPath outside external_dir is ignored; relPath inside is used."""
        target = tmp_path / "asset.png"
        target.write_bytes(b"asset")
        so = _make_external_smart_object("/etc/passwd", "asset.png")
        with so.open(external_dir=str(tmp_path)) as f:
            assert f.read() == b"asset"
