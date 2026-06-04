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
    embedded_filename: str,
    payload: bytes = b"pwned",
    filetype: bytes = b"    ",
) -> SmartObject:
    """Build a SmartObject whose _data mimics a DATA-kind LinkedLayer."""
    data_mock = MagicMock()
    data_mock.kind = LinkedLayerType.DATA
    data_mock.filename = embedded_filename
    data_mock.data = payload
    data_mock.filetype = filetype

    config_mock = MagicMock()
    config_mock.data = {b"Idnt": MagicMock(value="test-uuid\x00")}

    so = object.__new__(SmartObject)
    so._data = data_mock
    so._config = config_mock
    so._placed_layer = None
    return so


def _make_external_smart_object(
    full_path: str,
    rel_path: str,
    embedded_filename: str = "linked.png",
    filetype: bytes = b"    ",
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
    data_mock.filetype = filetype

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
        """../../escape.bin should write as escape.bin inside out_dir, not escape."""
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        so = _make_data_smart_object("../../escape.bin", b"data")
        so.save(directory=str(out_dir))
        assert (out_dir / "escape.bin").read_bytes() == b"data"
        # nothing escaped to the parent directories within tmp_path
        assert not (tmp_path / "escape.bin").exists()

    def test_absolute_embedded_path_is_stripped(self, tmp_path: Path) -> None:
        """An absolute embedded path is reduced to its basename inside out_dir."""
        # Keep sentinel and output dir both inside tmp_path to avoid parallel
        # test interference when writing to shared parent directories.
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        sentinel = source_dir / "sentinel.bin"
        sentinel.write_bytes(b"original")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        so = _make_data_smart_object(str(sentinel), b"data")
        so.save(directory=str(out_dir))
        # basename of sentinel is written inside out_dir
        assert (out_dir / "sentinel.bin").read_bytes() == b"data"
        # the original file is untouched
        assert sentinel.read_bytes() == b"original"

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
        # fullPath escapes external_dir so it is ignored; relPath "benign.png"
        # does not exist inside out_dir → FileNotFoundError
        with pytest.raises(FileNotFoundError):
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


# ---------------------------------------------------------------------------
# filetype / detected_filetype / is_psd tests — Issue #599
# ---------------------------------------------------------------------------


class TestFiletypeBlank:
    """filetype returns None for blank stored field; detected_filetype falls back."""

    def test_filetype_returns_none_when_blank(self) -> None:
        so = _make_data_smart_object("foo.pdf", b"%PDF-1.5 rest", filetype=b"    ")
        assert so.filetype is None

    def test_filetype_returns_value_when_present(self) -> None:
        so = _make_data_smart_object("foo.png", b"\x89PNG\r\n\x1a\n", filetype=b"PNG ")
        assert so.filetype == "png"

    # --- detected_filetype: stored value wins ---

    def test_detected_uses_stored_filetype_when_present(self) -> None:
        so = _make_data_smart_object("foo.pdf", b"\x89PNG\r\n\x1a\n", filetype=b"PNG ")
        # stored type is "png" even though filename says .pdf
        assert so.detected_filetype == "png"

    # --- detected_filetype: filename extension fallback ---

    def test_detected_falls_back_to_extension(self) -> None:
        so = _make_data_smart_object(
            "document.pdf", b"not-a-real-pdf", filetype=b"    "
        )
        assert so.detected_filetype == "pdf"

    def test_detected_extension_strips_null_bytes(self) -> None:
        so = _make_data_smart_object("image.png\x00", b"garbage", filetype=b"    ")
        assert so.detected_filetype == "png"

    def test_detected_trailing_dot_falls_through_to_magic(self) -> None:
        # "foo." yields ext="." which strips to "" — must not return ""
        so = _make_data_smart_object("foo.", b"%PDF-1.5 body", filetype=b"    ")
        assert so.detected_filetype == "pdf"

    def test_detected_psd_extension_returns_psd_not_8bps(self) -> None:
        # extension path returns the extension string; magic path returns the code.
        # Documented: detected_filetype is raw-code-oriented (stored value) but
        # extension-as-is for the filename fallback.
        so = _make_data_smart_object("file.psd", b"\x00\x01\x02\x03", filetype=b"    ")
        assert so.detected_filetype == "psd"

    # --- detected_filetype: magic bytes fallback ---

    def test_detected_magic_pdf(self) -> None:
        so = _make_data_smart_object("unknown", b"%PDF-1.5 body", filetype=b"    ")
        assert so.detected_filetype == "pdf"

    def test_detected_magic_png(self) -> None:
        so = _make_data_smart_object(
            "unknown", b"\x89PNG\r\n\x1a\ndata", filetype=b"    "
        )
        assert so.detected_filetype == "png"

    def test_detected_magic_jpeg(self) -> None:
        so = _make_data_smart_object(
            "unknown", b"\xff\xd8\xff\xe0data", filetype=b"    "
        )
        assert so.detected_filetype == "jpg"

    def test_detected_magic_gif(self) -> None:
        so = _make_data_smart_object("unknown", b"GIF89a data", filetype=b"    ")
        assert so.detected_filetype == "gif"

    def test_detected_magic_tiff_le(self) -> None:
        so = _make_data_smart_object("unknown", b"II*\x00data", filetype=b"    ")
        assert so.detected_filetype == "tiff"

    def test_detected_magic_tiff_be(self) -> None:
        so = _make_data_smart_object("unknown", b"MM\x00*data", filetype=b"    ")
        assert so.detected_filetype == "tiff"

    def test_detected_magic_webp(self) -> None:
        so = _make_data_smart_object(
            "unknown", b"RIFFxxxxWEBPVP8 data", filetype=b"    "
        )
        assert so.detected_filetype == "webp"

    def test_detected_magic_zip(self) -> None:
        so = _make_data_smart_object("unknown", b"PK\x03\x04data", filetype=b"    ")
        assert so.detected_filetype == "zip"

    def test_detected_magic_bmp(self) -> None:
        so = _make_data_smart_object("unknown", b"BMdata", filetype=b"    ")
        assert so.detected_filetype == "bmp"

    def test_detected_magic_psd_version1(self) -> None:
        so = _make_data_smart_object("unknown", b"8BPS\x00\x01rest", filetype=b"    ")
        assert so.detected_filetype == "8bps"

    def test_detected_magic_psb_version2(self) -> None:
        so = _make_data_smart_object("unknown", b"8BPS\x00\x02rest", filetype=b"    ")
        assert so.detected_filetype == "8bpb"

    def test_detected_returns_none_when_all_fallbacks_fail(self) -> None:
        so = _make_data_smart_object("unknown", b"\x00\x01\x02\x03", filetype=b"    ")
        assert so.detected_filetype is None

    # --- non-SVG XML must not be misdetected ---

    def test_xml_not_detected_as_svg(self) -> None:
        so = _make_data_smart_object(
            "data.xml", b"<?xml version='1.0'?><root/>", filetype=b"    "
        )
        # extension fallback kicks in first: "xml", not "svg"
        assert so.detected_filetype == "xml"

    def test_generic_xml_magic_no_extension_returns_none(self) -> None:
        # No extension, and magic bytes don't match anything in the table
        so = _make_data_smart_object(
            "unknown", b"<?xml version='1.0'?><root/>", filetype=b"    "
        )
        assert so.detected_filetype is None

    # --- is_psd ---

    def test_is_psd_true_via_stored_filetype(self) -> None:
        so = _make_data_smart_object("f.psd", b"8BPS\x00\x01rest", filetype=b"8BPS")
        assert so.is_psd() is True

    def test_is_psd_true_via_stored_filetype_psb(self) -> None:
        so = _make_data_smart_object("f.psb", b"8BPS\x00\x02rest", filetype=b"8BPB")
        assert so.is_psd() is True

    def test_is_psd_true_via_magic_when_filetype_blank(self) -> None:
        so = _make_data_smart_object("f.psd", b"8BPS\x00\x01rest", filetype=b"    ")
        assert so.is_psd() is True

    def test_is_psd_false_for_pdf_named_psd(self) -> None:
        # Extension is intentionally NOT used by is_psd()
        so = _make_data_smart_object("trick.psd", b"%PDF-1.5", filetype=b"    ")
        assert so.is_psd() is False

    def test_is_psd_false_for_png(self) -> None:
        so = _make_data_smart_object(
            "f.png", b"\x89PNG\r\n\x1a\ndata", filetype=b"    "
        )
        assert so.is_psd() is False

    # --- external kind: no filesystem access in detected_filetype ---

    def test_detected_external_uses_extension_not_magic(self, tmp_path: Path) -> None:
        so = _make_external_smart_object(
            "", "asset.png", embedded_filename="asset.pdf", filetype=b"    "
        )
        # Extension from embedded_filename wins; magic bytes NOT read from disk
        assert so.detected_filetype == "pdf"

    def test_detected_external_no_filesystem_read(self, tmp_path: Path) -> None:
        """detected_filetype for external kind must not touch the filesystem."""
        sentinel = tmp_path / "asset.png"
        sentinel.write_bytes(b"\x89PNG\r\n\x1a\ndata")
        so = _make_external_smart_object(
            str(sentinel), "asset.png", embedded_filename="no-ext", filetype=b"    "
        )
        # No extension, no filesystem read → None
        assert so.detected_filetype is None

    # --- __repr__ shows both raw and detected ---

    def test_repr_shows_type_none_and_detected(self) -> None:
        so = _make_data_smart_object("foo.pdf", b"%PDF-1.5", filetype=b"    ")
        r = repr(so)
        assert "type=None" in r
        assert "detected='pdf'" in r

    def test_repr_shows_stored_type_when_present(self) -> None:
        so = _make_data_smart_object("foo.png", b"\x89PNG\r\n\x1a\n", filetype=b"PNG ")
        r = repr(so)
        assert "type='png'" in r
        assert "detected='png'" in r
