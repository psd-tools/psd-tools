"""Regression coverage for descriptor retention and recursive parsing."""

import io
import os
import pickle
import subprocess
import sys

import pytest

from psd_tools import ParseLimitError, ParseLimits, PSDImage
from psd_tools.constants import OSType, Tag
from psd_tools.psd.adjustments import ColorLookup
from psd_tools.psd.bin_utils import pack
from psd_tools.psd.descriptor import (
    _TERMS,
    Descriptor,
    DescriptorBlock,
    DescriptorBlock2,
    Enumerated,
    List,
    ObjectArray,
    Reference,
    read_length_and_key,
    write_length_and_key,
)
from psd_tools.psd.engine_data import Dict as EngineDict, List as EngineList
from psd_tools.psd.header import FileHeader
from psd_tools.psd.parse_limits import parse_container, parse_context
from psd_tools.psd.vector import VectorStrokeContentSetting
from psd_tools.terminology import Klass


def nested_binary(depth: int, containers=(Descriptor,)) -> bytes:
    data = b""
    child_type = None
    for level in reversed(range(depth)):
        cls = containers[level % len(containers)]
        count = int(child_type is not None)
        child = b"" if child_type is None else child_type.value + data
        if issubclass(cls, List):
            data = pack("I", count) + child
        else:
            data = (
                pack("II", 0, 0)
                + Klass.Null.value
                + pack("I", count)
                + (pack("I", 4) + b"test" + child if count else b"")
            )
        child_type = cls.ostype
    return data


@pytest.mark.parametrize(
    "containers", [(Descriptor,), (List,), (Descriptor, List), (List, Descriptor)]
)
def test_binary_exact_depth(containers) -> None:
    cls = containers[0]
    limits = ParseLimits(max_nesting_depth=4)
    cls.frombytes(nested_binary(4, containers), parse_limits=limits)
    with pytest.raises(ParseLimitError, match="max_nesting_depth"):
        cls.frombytes(nested_binary(5, containers), parse_limits=limits)


@pytest.mark.parametrize(
    "cls,prefix",
    [
        (Descriptor, b""),
        (DescriptorBlock, pack("I", 16)),
        (DescriptorBlock2, pack("II", 1, 16)),
        (ObjectArray, pack("I", 1)),
        (List, b""),
        (Reference, b""),
        (ColorLookup, pack("HI", 1, 16)),
        (VectorStrokeContentSetting, pack("4sI", b"SoCo", 1)),
    ],
)
def test_direct_recursive_read_limits_and_reset(cls, prefix) -> None:
    containers = (List,) if issubclass(cls, List) else (Descriptor,)
    cls.read(io.BytesIO(prefix + nested_binary(2, containers)))
    limits = ParseLimits(max_nesting_depth=2)
    for _ in range(2):
        with pytest.raises(ParseLimitError, match="max_nesting_depth"):
            cls.read(
                io.BytesIO(prefix + nested_binary(3, containers)), parse_limits=limits
            )
        cls.read(io.BytesIO(prefix + nested_binary(2, containers)), parse_limits=limits)
    stream = io.BytesIO(prefix + nested_binary(1, containers))
    with pytest.raises(TypeError, match="parse_limits"):
        cls.read(stream, parse_limits=False)
    assert stream.tell() == 0


@pytest.mark.parametrize("cls", [Descriptor, List])
def test_default_limit_precedes_python_recursion_limit(cls) -> None:
    data = nested_binary(1000, (cls,))
    with pytest.raises(ParseLimitError, match="max_nesting_depth"):
        cls.read(io.BytesIO(data))


def test_default_limit_through_psd_open_and_tag_recovery() -> None:
    descriptor = pack("I", 16) + nested_binary(1000)
    tag = b"8BIM" + Tag.COMPOSITOR_INFO.value + pack("I", len(descriptor)) + descriptor
    tag += b"\x00" * (-len(descriptor) % 4)
    layer_mask = pack("II", 0, 0) + tag
    psd = (
        FileHeader(channels=1, width=1, height=1).tobytes()
        + pack("II", 0, 0)
        + pack("I", len(layer_mask))
        + layer_mask
        + pack("H", 0)
        + b"\x00"
    )
    with pytest.raises(ParseLimitError, match="max_nesting_depth"):
        PSDImage.open(io.BytesIO(psd))


@pytest.mark.parametrize(
    "cls,data,depth",
    [(EngineDict, b"<< /x << >> >>", 2), (EngineList, b"[ [ 1 ] ]", 3)],
)
def test_engine_container_exact_depth(cls, data, depth) -> None:
    cls.frombytes(data, parse_limits=ParseLimits(max_nesting_depth=depth))
    with pytest.raises(ParseLimitError, match="max_nesting_depth"):
        cls.frombytes(data, parse_limits=ParseLimits(max_nesting_depth=depth - 1))


@pytest.mark.parametrize(
    "cls,data",
    [
        (EngineDict, b"<< /x " * 1000 + b"<< >>" + b" >>" * 1000),
        (EngineList, b"[ " * 1000 + b"1" + b" ]" * 1000),
    ],
)
def test_engine_default_limit_precedes_recursion_limit(cls, data) -> None:
    with pytest.raises(ParseLimitError, match="max_nesting_depth"):
        cls.frombytes(data)


def test_shared_depth_nested_bytes_and_latched_error() -> None:
    with pytest.raises(ParseLimitError, match="max_nesting_depth"):
        with parse_context(ParseLimits(max_nesting_depth=2)):
            with parse_container():
                try:
                    EngineDict.frombytes(
                        b"<< /x << >> >>",
                        parse_limits=ParseLimits(max_nesting_depth=None),
                    )
                except ParseLimitError:
                    pass


def test_depth_unwinds_after_non_limit_failure() -> None:
    with parse_context(ParseLimits(max_nesting_depth=1)):
        with pytest.raises(OSError):
            Descriptor.read(io.BytesIO(b""))
        Descriptor.frombytes(nested_binary(1))


def test_disabled_depth_and_siblings() -> None:
    Descriptor.frombytes(
        nested_binary(70), parse_limits=ParseLimits(max_nesting_depth=None)
    )
    data = pack("I", 3) + (OSType.DESCRIPTOR.value + nested_binary(1)) * 3
    List.frombytes(data, parse_limits=ParseLimits(max_nesting_depth=2))


def test_unknown_terms_are_not_retained_or_cross_contaminated() -> None:
    before = frozenset(_TERMS)
    for value in range(256):
        key = b"\xff" + value.to_bytes(3, "big")
        assert key not in _TERMS
        parsed = read_length_and_key(io.BytesIO(pack("I", 0) + key))
        assert parsed == key and isinstance(parsed, bytes)
        stream = io.BytesIO()
        write_length_and_key(stream, key)
        assert stream.getvalue() == pack("I", 4) + key
        stream = io.BytesIO()
        write_length_and_key(stream, parsed)
        assert stream.getvalue() == pack("I", 0) + key
    assert _TERMS == before
    assert isinstance(_TERMS, frozenset)


def test_unknown_class_and_item_keys_roundtrip_locally() -> None:
    key = b"\xffkey"
    data = (
        pack("II", 0, 0)
        + key
        + pack("II", 1, 0)
        + key
        + OSType.INTEGER.value
        + pack("i", 42)
    )
    parsed = Descriptor.frombytes(data)
    assert parsed.classID == key and parsed[key] == 42
    assert parsed.tobytes() == data
    assert pickle.loads(pickle.dumps(parsed)).tobytes() == data
    explicit = pack("II", 0, 4) + key + pack("I", 0)
    assert Descriptor.frombytes(explicit).tobytes() == explicit
    assert parsed.tobytes() == data


def test_unknown_scalar_ids_roundtrip_and_known_terms() -> None:
    data = pack("I", 0) + b"\xfftyp" + pack("I", 0) + b"\xffenu"
    assert Enumerated.frombytes(data).tobytes() == data
    stream = io.BytesIO()
    write_length_and_key(stream, Klass.Null.value)
    assert stream.getvalue() == pack("I", 0) + Klass.Null.value


def test_nesting_limit_under_optimized_python() -> None:
    script = """
from psd_tools import ParseLimits, ParseLimitError
from psd_tools.psd.engine_data import Dict
try:
    Dict.frombytes(b'<< /x << >> >>', parse_limits=ParseLimits(max_nesting_depth=1))
except ParseLimitError:
    pass
else:
    raise RuntimeError('Nesting limit was disabled under -O')
"""
    subprocess.run(
        [sys.executable, "-O", "-c", script], check=True, env=os.environ.copy()
    )
