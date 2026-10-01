"""Regression tests for length-controlled reads and nested section boundaries."""

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from psd_tools import PSDImage
from psd_tools.psd.bin_utils import (
    bounded_reader,
    pack,
    read_be_array,
    read_exact,
    read_length_block,
    read_pascal_string,
    read_unicode_string,
)
from psd_tools.psd.header import FileHeader
from psd_tools.psd.layer_and_mask import (
    ChannelData,
    GlobalLayerMaskInfo,
    LayerAndMaskInformation,
    LayerInfo,
)
from psd_tools.psd.patterns import VirtualMemoryArray
from psd_tools.psd.tagged_blocks import Annotations, TaggedBlock, TaggedBlocks


class RecordingFile(io.FileIO):
    def __init__(self, path: Path):
        super().__init__(path, "rb")
        self.read_sizes: list[int] = []

    def read(self, size: int | None = -1) -> bytes:
        self.read_sizes.append(-1 if size is None else size)
        return super().read(size)


@pytest.mark.parametrize("fmt", ["I", "Q"])
def test_forged_length_rejected_before_file_read(tmp_path: Path, fmt: str) -> None:
    path = tmp_path / "forged.psd"
    path.write_bytes(pack(fmt, 1 << 30))
    with RecordingFile(path) as stream:
        with pytest.raises(OSError):
            read_length_block(stream, fmt=fmt)
        assert max(stream.read_sizes) <= 8


def test_psd_open_rejects_forged_color_length(tmp_path: Path) -> None:
    path = tmp_path / "forged.psd"
    path.write_bytes(FileHeader().tobytes() + pack("I", 1 << 30))
    with RecordingFile(path) as stream:
        with pytest.raises(OSError):
            PSDImage.open(stream)
        assert max(stream.read_sizes) < 100


@pytest.mark.parametrize("size", [-1, 4, 1 << 32])
def test_read_exact_rejects_invalid_size_without_advancing(size: int) -> None:
    stream = io.BytesIO(b"abc")
    with pytest.raises(OSError):
        read_exact(stream, size)
    assert stream.tell() == 0


def test_read_exact_detects_short_read_after_preflight() -> None:
    class ShortReader(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            return super().read(1)

    with pytest.raises(OSError):
        read_exact(ShortReader(b"abc"), 3)


def test_read_exact_restores_position_when_end_seek_fails() -> None:
    class FailedSeekReader(io.BytesIO):
        def seek(self, offset: int, whence: int = 0) -> int:
            if whence == os.SEEK_END:
                super().seek(0)
                raise OSError("Unavailable end position")
            return super().seek(offset, whence)

    stream = FailedSeekReader(b"abc")
    stream.seek(1)
    with pytest.raises(OSError):
        read_exact(stream, 1)
    assert stream.tell() == 1


def test_bounded_reader_positions_and_nested_sections() -> None:
    stream = io.BytesIO(b"prefixABCDsibling")
    stream.seek(6)
    with bounded_reader(stream, 4) as body:
        assert body.read(100) == b"ABCD"
        assert body.seek(-2, os.SEEK_END) == 8
        with pytest.raises(OSError):
            with bounded_reader(body, 3):
                pytest.fail("Child exceeded parent")
        assert body.tell() == 8
        with bounded_reader(body, 1) as child:
            assert child.read(-1) == b"C"
        assert body.tell() == 9
        for offset, whence in [(5, 0), (1, 2), (-4, 1)]:
            with pytest.raises(OSError):
                body.seek(offset, whence)
        assert body.read() == b"D"
    assert stream.read() == b"sibling"


def test_bounded_reader_skips_remainder_only_on_success() -> None:
    stream = io.BytesIO(b"abcd")
    with pytest.raises(OSError):
        with bounded_reader(stream, 3) as body:
            body.read(1)
            read_exact(body, 3)
    assert stream.tell() == 1
    with bounded_reader(stream, 2):
        pass
    assert stream.tell() == 3


@pytest.mark.parametrize("version, fmt", [(1, "I"), (2, "Q")])
@pytest.mark.parametrize("cls", [LayerAndMaskInformation, LayerInfo])
def test_short_layer_section_cannot_read_sibling(cls, version: int, fmt: str) -> None:
    marker = pack(fmt, 1)
    stream = io.BytesIO(marker + b"\x00" + b"SIBLING")
    with pytest.raises(OSError):
        cls.read(stream, version=version)
    assert stream.tell() == len(marker)
    assert stream.read() == b"\x00SIBLING"


@pytest.mark.parametrize("version, fmt", [(1, "I"), (2, "Q")])
def test_layer_child_length_cannot_exceed_parent(version: int, fmt: str) -> None:
    child = pack(fmt, 8)
    stream = io.BytesIO(pack(fmt, len(child)) + child + b"\x00" * 8)
    with pytest.raises(OSError):
        LayerAndMaskInformation.read(stream, version=version)
    assert stream.tell() == 2 * len(child)


def test_empty_global_mask_roundtrip_without_sibling_bytes() -> None:
    section = LayerAndMaskInformation(
        layer_info=LayerInfo(),
        global_layer_mask_info=GlobalLayerMaskInfo(),
        tagged_blocks=TaggedBlocks(),
    )
    assert LayerAndMaskInformation.frombytes(section.tobytes()) == section


def test_global_tags_without_mask_length_marker() -> None:
    tags = TaggedBlocks()
    tags[b"zzzz"] = TaggedBlock(key=b"zzzz", data=b"abcd")
    section = LayerAndMaskInformation(layer_info=LayerInfo(), tagged_blocks=tags)
    assert LayerAndMaskInformation.frombytes(section.tobytes()) == section


@pytest.mark.parametrize("length", [1, 22])
def test_pattern_channel_rejects_header_underflow(length: int) -> None:
    stream = io.BytesIO(pack("II", 1, length) + b"NEXT_CHANNEL")
    with pytest.raises(OSError):
        VirtualMemoryArray.read(stream)
    assert stream.tell() == 8
    assert stream.read() == b"NEXT_CHANNEL"


def test_pattern_channel_rejects_truncated_payload() -> None:
    stream = io.BytesIO(pack("III4IHB", 1, 24, 8, 0, 0, 1, 1, 8, 0))
    with pytest.raises(OSError):
        VirtualMemoryArray.read(stream)
    assert stream.tell() == 8


@pytest.mark.parametrize("payload_length, parent_length", [(8, 12), (1, 13)])
def test_tagged_block_payload_and_padding_stay_in_parent(
    payload_length: int, parent_length: int
) -> None:
    stream = io.BytesIO(b"8BIMzzzz" + pack("I", payload_length) + b"a" * 8)
    with pytest.raises(OSError):
        TaggedBlocks.read(stream, padding=4, end_pos=parent_length)
    assert stream.tell() <= parent_length


@pytest.mark.parametrize(
    "reader, data",
    [
        (read_unicode_string, pack("I", 100) + b"\x00a"),
        (read_pascal_string, b"\x05abc"),
        (lambda f: read_be_array("H", 2, f), b"\x00\x01"),
        (lambda f: ChannelData.read(f, length=100), b"\x00\x00a"),
        (Annotations.read, pack("2HII", 2, 1, 1, 3)),
        (Annotations.read, pack("2HII", 2, 1, 1, 100)),
    ],
)
def test_truncated_sized_reads(reader, data: bytes) -> None:
    with pytest.raises(OSError):
        reader(io.BytesIO(data))


def test_validation_survives_optimized_python() -> None:
    script = """
import io
from psd_tools.psd.bin_utils import pack, read_pascal_string
from psd_tools.psd.layer_and_mask import LayerInfo
for reader, data in [(LayerInfo.read, pack('I', 1) + b'\\0SIBLING'),
                     (read_pascal_string, b'\\x05abc')]:
    try:
        reader(io.BytesIO(data))
    except OSError:
        continue
    raise RuntimeError('Malformed section accepted under -O')
"""
    subprocess.run([sys.executable, "-O", "-c", script], check=True)
