"""
Smart object module.
"""

import contextlib
import io
import logging
import os
from typing import IO, Iterator

from psd_tools.api.protocols import LayerProtocol
from psd_tools.constants import Tag

logger = logging.getLogger(__name__)

# (prefix_bytes, filetype_string) — ordered so longer/more-specific prefixes
# come first (8BPS+version before bare 8BPS would collide; PSD/PSB checked
# as 6-byte prefixes including the version field).
_MAGIC_TABLE: tuple[tuple[bytes, str], ...] = (
    (b"8BPS\x00\x01", "8bps"),  # PSD  (version 1)
    (b"8BPS\x00\x02", "8bpb"),  # PSB  (version 2)
    (b"%PDF-", "pdf"),
    (b"\x89PNG", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF8", "gif"),
    (b"II*\x00", "tiff"),  # TIFF little-endian
    (b"MM\x00*", "tiff"),  # TIFF big-endian
    (b"PK\x03\x04", "zip"),  # ZIP / ZIP-based AI
    (b"BM", "bmp"),
)
_MAGIC_PREFIX_LEN = max(len(p) for p, _ in _MAGIC_TABLE)


def _detect_filetype_from_magic(data: bytes) -> str | None:
    """Return a filetype string inferred from *data* magic bytes, or ``None``."""
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    prefix = data[:_MAGIC_PREFIX_LEN]
    for magic, result in _MAGIC_TABLE:
        if prefix[: len(magic)] == magic:
            return result
    return None


def _is_inside(parent: str, child: str) -> bool:
    """Return True if child is inside parent (or equal to it)."""
    parent = os.path.normcase(parent)
    child = os.path.normcase(child)
    try:
        return os.path.commonpath([parent, child]) == parent
    except ValueError:
        # commonpath raises ValueError on Windows when paths span different drives
        return False


class SmartObject:
    """
    Smart object that represents embedded or external file.

    Smart objects are attached to
    :py:class:`~psd_tools.api.layers.SmartObjectLayer`.
    """

    def __init__(self, layer: LayerProtocol):
        self._config = None
        for key in (Tag.SMART_OBJECT_LAYER_DATA1, Tag.SMART_OBJECT_LAYER_DATA2):
            if key in layer.tagged_blocks:
                self._config = layer.tagged_blocks.get_data(key)
                break

        self._placed_layer = None
        for key in (Tag.PLACED_LAYER1, Tag.PLACED_LAYER2):
            if key in layer.tagged_blocks:
                self._placed_layer = layer.tagged_blocks.get_data(key)
                break

        self._data = None
        if layer._psd is not None and layer._psd.tagged_blocks is not None:
            for key in (
                Tag.LINKED_LAYER1,
                Tag.LINKED_LAYER2,
                Tag.LINKED_LAYER3,
                Tag.LINKED_LAYER_EXTERNAL,
            ):
                if key in layer._psd.tagged_blocks:
                    data = layer._psd.tagged_blocks.get_data(key)
                    for item in data:
                        if item.uuid == self.unique_id:
                            self._data = item
                            break
                    if self._data:
                        break

    @property
    def kind(self) -> str:
        """Kind of the link, 'data', 'alias', or 'external'."""
        if self._data is None:
            raise ValueError("Smart object data not found")
        return self._data.kind.name.lower()

    @property
    def filename(self) -> str:
        """Original file name of the object."""
        if self._data is None:
            raise ValueError("Smart object data not found")
        return self._data.filename.strip("\x00")

    @contextlib.contextmanager
    def open(
        self, external_dir: str | os.PathLike | None = None
    ) -> Iterator[IO[bytes]]:
        """
        Open the smart object as binary IO.

        :param external_dir: Directory to resolve external paths against.
            When provided, a ``fullPath`` that resolves outside this directory is
            silently ignored and ``relPath`` is tried instead. A ``relPath`` that
            resolves outside this directory raises :py:exc:`ValueError`.
            Strongly recommended when processing untrusted PSD files.

        Example::

            with layer.smart_object.open() as f:
                data = f.read()
        """
        if self._data is None:
            raise ValueError("Smart object data not found")
        if self.kind == "data":
            with io.BytesIO(self._data.data) as f:
                yield f
        elif self.kind == "external":
            filepath = self._data.linked_file[b"fullPath"].value
            filepath = filepath.replace("\x00", "").replace("file://", "")
            if external_dir is not None:
                safe_dir = os.path.realpath(external_dir)
                resolved = os.path.realpath(filepath)
                if not _is_inside(safe_dir, resolved):
                    # fullPath escapes external_dir — fall through to relPath
                    filepath = ""
            if not filepath or not os.path.exists(filepath):
                relpath = self._data.linked_file[b"relPath"].value
                relpath = relpath.replace("\x00", "")
                if external_dir is not None:
                    safe_dir = os.path.realpath(external_dir)
                    filepath = os.path.realpath(os.path.join(safe_dir, relpath))
                    if not _is_inside(safe_dir, filepath):
                        raise ValueError(
                            f"External smart object path escapes external_dir: {relpath!r}"
                        )
                else:
                    filepath = relpath
                if not os.path.exists(filepath):
                    raise FileNotFoundError(f"Smart object file not found: {filepath}")
            with open(filepath, "rb") as f:
                yield f
        else:
            raise NotImplementedError("alias is not supported.")

    @property
    def data(self) -> bytes:
        """Embedded file content as bytes.

        For ``kind == 'data'`` this returns the bytes stored in the PSD without
        any filesystem access.  For ``kind == 'external'`` this calls
        :py:meth:`open` with no ``external_dir`` argument, which trusts
        ``fullPath`` from the PSD verbatim.  Prefer :py:meth:`open` with an
        explicit ``external_dir`` when processing untrusted files.
        """
        if self._data is None:
            raise ValueError("Smart object data not found")
        if self.kind == "data":
            return self._data.data
        else:
            with self.open() as f:
                return f.read()

    @property
    def unique_id(self) -> str:
        """UUID of the object."""
        if self._config is None:
            raise ValueError("Smart object config not found")
        return self._config.data.get(b"Idnt").value.strip("\x00")

    @property
    def filesize(self) -> int:
        """File size of the object."""
        if self._data is None:
            raise ValueError("Smart object data not found")
        if self.kind == "data":
            return len(self._data.data)
        return self._data.filesize

    @property
    def filetype(self) -> str | None:
        """4-byte file-type code stored in the PSD, lowercased and stripped.

        Returns ``None`` when the field is absent or blank (e.g. some
        Adobe Illustrator smart objects store four spaces instead of a real
        type code).  Use :py:attr:`detected_filetype` for a best-effort
        guess that falls back to the filename extension and magic bytes.
        """
        if self._data is None:
            raise ValueError("Smart object data not found")
        raw = self._data.filetype.lower().strip().decode("ascii")
        return raw if raw else None

    @property
    def detected_filetype(self) -> str | None:
        """Best-effort file type, falling back when :py:attr:`filetype` is ``None``.

        Resolution order:

        1. :py:attr:`filetype` — the value stored in the PSD.
        2. Extension taken from :py:attr:`filename` (lower-cased, dot stripped).
        3. Magic-byte sniffing of the first few embedded bytes
           (only for ``kind == 'data'``; external objects are not read from
           disk to keep this property side-effect-free).

        .. warning::
            Steps 2 and 3 are heuristic.  Do not use the result for
            security-sensitive decisions (e.g. deciding whether to execute
            content or trust a type boundary).
        """
        ft = self.filetype
        if ft is not None:
            return ft

        # Extension from the embedded filename (safe: no filesystem access)
        clean = self._data.filename.replace("\x00", "").strip() if self._data else ""
        _, ext = os.path.splitext(clean)
        suffix = ext.lstrip(".").lower()
        if suffix:
            return suffix

        # Magic bytes — only for embedded (data-kind) objects
        if self._data is not None and self.kind == "data":
            raw_data = self._data.data
            if raw_data:
                return _detect_filetype_from_magic(raw_data)

        return None

    def is_psd(self) -> bool:
        """Return True if the file is embedded PSD/PSB.

        Checks the stored :py:attr:`filetype` first; if that is ``None``
        (blank field), falls back to inspecting the first four magic bytes of
        the embedded data.  The filename extension is intentionally *not* used
        as a fallback to avoid misclassifying non-PSD files named ``*.psd``.
        """
        ft = self.filetype
        if ft in ("8bpb", "8bps"):
            return True
        if self._data is not None and self.kind == "data":
            raw_data = self._data.data
            if raw_data and len(raw_data) >= 4:
                return raw_data[:4] == b"8BPS"
        return False

    @property
    def warp(self) -> object | None:
        """Warp parameters."""
        if self._config is None:
            raise ValueError("Smart object config not found")
        return self._config.data.get(b"warp")

    @property
    def resolution(self) -> float:
        """Resolution of the object."""
        if self._config is None:
            raise ValueError("Smart object config not found")
        return self._config.data.get(b"Rslt").value

    @property
    def transform_box(
        self,
    ) -> tuple[float, float, float, float, float, float, float, float] | None:
        """
        A tuple representing the coordinates of the smart objects's transformed box. This box is the result of one or more transformations such as scaling, rotation, translation, or skewing to the original bounding box of the smart object.

        The format of the tuple is as follows:
        (x1, y1, x2, y2, x3, y3, x4, y4)

        Where 1 is top left corner, 2 is top right, 3 is bottom right and 4 is bottom left.
        """
        if self._placed_layer and hasattr(self._placed_layer, "transform"):
            return self._placed_layer.transform
        else:
            return None

    def save(
        self,
        filename: str | os.PathLike | None = None,
        directory: str | os.PathLike | None = None,
        external_dir: str | os.PathLike | None = None,
    ) -> None:
        """
        Save the smart object to a file.

        :param filename: Explicit destination path. When provided it is used
            as-is and ``directory`` is ignored.
        :param directory: Output directory used when ``filename`` is ``None``.
            Defaults to the current working directory. The embedded basename is
            written inside this directory; path-traversal sequences in the
            embedded name are stripped automatically.
        :param external_dir: Passed to :py:meth:`open` when the smart object
            kind is ``'external'``. Constrains which paths on disk may be read.
            Strongly recommended when processing untrusted PSD files.
        :raises ValueError: If the embedded name contains no safe basename,
            resolves outside ``directory``, or (for external kind) the source
            path escapes ``external_dir``.
        """
        if filename is None:
            basename = os.path.basename(self.filename)
            if not basename or basename == ".":
                raise ValueError(
                    f"Embedded smart object filename has no safe basename: {self.filename!r}"
                )
            outdir = os.path.realpath(
                directory if directory is not None else os.getcwd()
            )
            resolved = os.path.realpath(os.path.join(outdir, basename))
            if not _is_inside(outdir, resolved):
                raise ValueError(
                    f"Embedded filename resolves outside target directory: {self.filename!r}"
                )
            filename = resolved
        if self.kind == "external":
            with self.open(external_dir=external_dir) as f:
                content = f.read()
        else:
            content = self.data
        with open(filename, "wb") as f:
            f.write(content)

    def __repr__(self) -> str:
        return "SmartObject(%r kind=%r type=%r detected=%r size=%s)" % (
            self.filename,
            self.kind,
            self.filetype,
            self.detected_filetype,
            self.filesize,
        )
