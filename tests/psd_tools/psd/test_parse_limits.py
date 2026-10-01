"""Regression coverage for shared structural parsing budgets."""

import io
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from psd_tools import ParseLimitError, ParseLimits, PSDImage
from psd_tools.constants import Tag
from psd_tools.psd import PSD
from psd_tools.psd.bin_utils import is_readable, pack, read_exact, read_fmt
from psd_tools.psd.descriptor import DescriptorBlock, RawData, UnitFloats
from psd_tools.psd.engine_data import EngineData, List as EngineList, Tokenizer
from psd_tools.psd.header import FileHeader
from psd_tools.psd.image_resources import AlphaIdentifiers, SliceV6
from psd_tools.psd.parse_limits import consume_bytes, parse_context
from psd_tools.psd.tagged_blocks import TaggedBlock, TypeToolObjectSetting
from psd_tools.terminology import Unit


def minimal_psd(color: bytes = b"", pixels: bytes = b"\x00") -> bytes:
    return (
        FileHeader(channels=1, width=1, height=1).tobytes()
        + pack("I", len(color))
        + color
        + pack("IIH", 0, 0, 0)
        + pixels
    )


class RecordingFile(io.FileIO):
    def __init__(self, path: Path):
        super().__init__(path, "rb")
        self.read_sizes: list[int] = []

    def read(self, size: int | None = -1) -> bytes:
        self.read_sizes.append(-1 if size is None else size)
        return super().read(size)


@pytest.mark.parametrize("section", ["color", "pixels"])
def test_actual_large_section_rejected_before_read(
    tmp_path: Path, section: str
) -> None:
    path = tmp_path / "large.psd"
    path.write_bytes(minimal_psd(**{section: b"x" * 64}))
    with RecordingFile(path) as stream:
        with pytest.raises(ParseLimitError, match="max_read_bytes"):
            PSDImage.open(stream, parse_limits=ParseLimits(max_read_bytes=32))
        assert max(stream.read_sizes) <= 26


def test_cumulative_sibling_sections_share_budget(tmp_path: Path) -> None:
    path = tmp_path / "siblings.psd"
    path.write_bytes(minimal_psd(color=b"x" * 64, pixels=b"y" * 64))
    with RecordingFile(path) as stream:
        with pytest.raises(ParseLimitError, match="max_total_bytes"):
            PSDImage.open(
                stream,
                parse_limits=ParseLimits(max_read_bytes=64, max_total_bytes=128),
            )
        assert stream.read_sizes.count(64) == 1


@pytest.mark.parametrize("entrypoint", [PSD.read, PSDImage.open])
def test_invalid_limits_rejected_before_read(entrypoint) -> None:
    stream = io.BytesIO(minimal_psd())
    with pytest.raises(TypeError, match="parse_limits"):
        entrypoint(stream, parse_limits=False)
    assert stream.tell() == 0


@pytest.mark.parametrize(
    "field", ["max_read_bytes", "max_total_bytes", "max_objects", "max_nesting_depth"]
)
@pytest.mark.parametrize(
    "value, error",
    [
        (True, TypeError),
        (1.5, TypeError),
        ("5", TypeError),
        (0, ValueError),
        (-1, ValueError),
    ],
)
def test_invalid_limit_settings(field: str, value, error) -> None:
    with pytest.raises(error, match=field):
        ParseLimits(**{field: value})


def test_exact_limits_zero_reads_and_disabled_limits() -> None:
    with parse_context(ParseLimits(max_read_bytes=1, max_total_bytes=1, max_objects=1)):
        assert read_exact(io.BytesIO(), 0) == b""
        assert read_fmt("B", io.BytesIO(b"x")) == (120,)
    limits = ParseLimits(max_read_bytes=None, max_total_bytes=None, max_objects=None)
    assert (
        PSD.frombytes(
            minimal_psd(color=b"x" * 128), parse_limits=limits
        ).color_mode_data.value
        == b"x" * 128
    )


def test_peeks_do_not_spend_bytes_or_objects() -> None:
    stream = io.BytesIO(b"x")
    with parse_context(ParseLimits(max_read_bytes=1, max_total_bytes=1, max_objects=1)):
        for _ in range(10):
            assert is_readable(stream)
            assert not is_readable(stream, 1 << 30)
        assert read_fmt("B", stream) == (120,)


def test_scalar_collection_limited_even_with_small_binary_input() -> None:
    data = pack("6I", *range(6))
    with pytest.raises(ParseLimitError, match="max_objects"):
        AlphaIdentifiers.frombytes(data, parse_limits=ParseLimits(max_objects=5))


def test_dynamic_float_array_rejected_before_payload_read() -> None:
    class RecordingBytes(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            if size is not None and size > 8:
                pytest.fail("Float payload was read before the object count check")
            return super().read(size)

    stream = RecordingBytes(
        pack("4sI", Unit.Pixels.value, 64) + pack("64d", *range(64))
    )
    with pytest.raises(ParseLimitError, match="max_objects"):
        with parse_context(ParseLimits(max_objects=32)):
            UnitFloats.read(stream)
    assert stream.tell() == 8


def test_engine_objects_share_root_budget() -> None:
    with pytest.raises(ParseLimitError, match="max_objects"):
        EngineList.frombytes(
            b"[ true true true true true ]", parse_limits=ParseLimits(max_objects=4)
        )


@pytest.mark.parametrize(
    "cls, data",
    [(EngineList, b"[ " + b" " * 64 + b"]"), (EngineData, b"<< " + b" " * 64 + b">>")],
)
@pytest.mark.parametrize("tokenized", [False, True])
@pytest.mark.parametrize("limit", ["max_read_bytes", "max_total_bytes"])
def test_engine_input_bytes_and_tokenizers_share_byte_limits(
    cls, data: bytes, tokenized: bool, limit: str
) -> None:
    source = Tokenizer(data) if tokenized else data
    with pytest.raises(ParseLimitError, match=limit):
        cls.frombytes(source, parse_limits=ParseLimits(**{limit: 8}))
    if isinstance(source, Tokenizer):
        assert source.index == 0


def test_nested_frombytes_cannot_reset_byte_budget() -> None:
    block = TaggedBlock(key=Tag.BLEND_FILL_OPACITY, data=b"\x0a").tobytes()
    with pytest.raises(ParseLimitError, match="max_total_bytes"):
        TaggedBlock.frombytes(
            block, parse_limits=ParseLimits(max_total_bytes=2 * len(block))
        )


def test_tagged_block_recovery_propagates_object_limit() -> None:
    block = TaggedBlock(key=Tag.BLEND_FILL_OPACITY, data=b"\x0a").tobytes()
    with pytest.raises(ParseLimitError, match="max_objects"):
        TaggedBlock.frombytes(block, parse_limits=ParseLimits(max_objects=4))


def test_engine_recovery_propagates_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    block = TypeToolObjectSetting(text_version=50, text_data=DescriptorBlock())
    block.text_data[b"EngineData"] = RawData(b"true")
    error = ParseLimitError("engine limit")

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(EngineData, "frombytes", fail)
    with pytest.raises(ParseLimitError, match="engine limit"):
        TypeToolObjectSetting.read(io.BytesIO(block.tobytes()))


def test_optional_slice_descriptor_propagates_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = SliceV6().tobytes() + pack("I", 16)

    def fail(*args, **kwargs):
        raise ParseLimitError("slice limit")

    monkeypatch.setattr(DescriptorBlock, "read", fail)
    with pytest.raises(ParseLimitError, match="slice limit"):
        SliceV6.frombytes(data)


def test_budget_reset_after_success_and_failure() -> None:
    limited = ParseLimits(max_total_bytes=32)
    for _ in range(2):
        with pytest.raises(ParseLimitError):
            PSD.frombytes(minimal_psd(), parse_limits=limited)
        assert PSD.frombytes(minimal_psd()).image_data.data == b"\x00"


def test_nested_context_cannot_relax_limits_or_hide_exhaustion() -> None:
    with pytest.raises(ParseLimitError, match="max_total_bytes"):
        with parse_context(ParseLimits(max_total_bytes=5)):
            consume_bytes(3)
            try:
                with parse_context(ParseLimits(max_total_bytes=None)):
                    consume_bytes(3)
            except ParseLimitError:
                pass


def test_concurrent_root_parses_have_separate_budgets() -> None:
    barrier = Barrier(2)

    def parse() -> bytes:
        with parse_context(ParseLimits(max_total_bytes=1)):
            barrier.wait(timeout=10)
            return read_exact(io.BytesIO(b"x"), 1)

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(lambda _: parse(), range(2))) == [b"x", b"x"]


def test_parse_limit_survives_optimized_python() -> None:
    script = """
from psd_tools import ParseLimits, ParseLimitError
from psd_tools.psd.engine_data import List
try:
    List.frombytes(b'[ true true true true ]', parse_limits=ParseLimits(max_objects=2))
except ParseLimitError:
    pass
else:
    raise RuntimeError('Parse limit was disabled under -O')
"""
    subprocess.run(
        [sys.executable, "-O", "-c", script], check=True, env=os.environ.copy()
    )
