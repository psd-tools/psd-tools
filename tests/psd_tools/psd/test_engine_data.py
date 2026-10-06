import os

import pytest

from psd_tools.psd.engine_data import (
    EngineData,
    EngineData2,
    EngineToken,
    Float,
    String,
    Tokenizer,
)

from ..utils import TEST_ROOT, check_read_write


@pytest.mark.parametrize(
    "fixture, length",
    [
        (b"(\xfe\xff0\x00) /1 (\xfe\xff\x001)", 3),
        (b"(\xfe\xff0\x00\\) /1 \\(\xfe\xff\x001)", 1),
        (b"(\xfe\xff) <<", 2),
    ],
)
def test_tokenizer(fixture: bytes, length: int) -> None:
    tokenizer = Tokenizer(fixture)
    tokens = list(tokenizer)
    assert len(tokens) == length


@pytest.mark.parametrize(
    "fixture, token_type",
    [
        (b"(\xfe\xff0\n0\n)", EngineToken.STRING),
    ],
)
def test_tokenizer_item(fixture: bytes, token_type: int) -> None:
    tokenizer = Tokenizer(fixture)
    token, o_token_type = next(tokenizer)
    assert o_token_type == token_type


@pytest.mark.parametrize(
    "data, expected",
    [
        (b"", []),
        (b" \n\t", []),
        (
            b" \t<< /Value [ -12 .5 true false ] >>\x00 \n",
            [
                (b"<<", EngineToken.DICT_START),
                (b"/Value", EngineToken.PROPERTY),
                (b"[", EngineToken.ARRAY_START),
                (b"-12", EngineToken.NUMBER),
                (b".5", EngineToken.NUMBER_WITH_DECIMAL),
                (b"true", EngineToken.BOOLEAN),
                (b"false", EngineToken.BOOLEAN),
                (b"]", EngineToken.ARRAY_END),
                (b">>\x00", EngineToken.DICT_END),
            ],
        ),
        (
            b"/Text (\xfe\xff\x00A\\)\x00B)/Next (\xfe\xff) ",
            [
                (b"/Text", EngineToken.PROPERTY),
                (b"(\xfe\xff\x00A\\)\x00B)", EngineToken.STRING),
                (b"/Next", EngineToken.PROPERTY),
                (b"(\xfe\xff)", EngineToken.STRING),
            ],
        ),
        (b"1", [(b"1", EngineToken.NUMBER)]),
    ],
)
def test_tokenizer_offsets(data, expected) -> None:
    tokenizer = Tokenizer(data)
    assert list(tokenizer) == expected
    assert tokenizer.index == len(data)
    assert len(tokenizer) == 0
    with pytest.raises(StopIteration):
        tokenizer.next()


@pytest.mark.parametrize(
    "suffix, message",
    [(b"(\xfe\xff\x00A", "Invalid token"), (b"?", "Unknown token")],
)
def test_tokenizer_invalid_at_offset(suffix: bytes, message: str) -> None:
    tokenizer = Tokenizer(b"1 " + suffix)
    assert next(tokenizer) == (b"1", EngineToken.NUMBER)
    with pytest.raises(ValueError) as error:
        next(tokenizer)
    assert str(error.value) == "%s: %r" % (message, suffix)


@pytest.mark.parametrize("token", [b"1", b"(\xfe\xff\x00A)"])
def test_tokenizer_copies_only_tokens(token: bytes) -> None:
    class TrackedBytes(bytes):
        copied_bytes = 0

        def __getitem__(self, key):
            value = super().__getitem__(key)
            if isinstance(key, slice):
                self.copied_bytes += len(value)
            return value

    count = 4096
    data = TrackedBytes((token + b" ") * count)
    tokenizer = Tokenizer(data)
    assert sum(1 for _ in tokenizer) == count
    assert data.copied_bytes == len(token) * count


@pytest.mark.parametrize(
    "filename, indent, write",
    [
        ("TySh_1.dat", 0, True),
        ("Txt2_1.dat", None, False),
        ("Txt2_2.dat", None, False),
        ("Txt2_3.dat", None, False),
        ("Txt2_4.dat", None, False),
    ],
)
def test_engine_data(filename: str, indent: str, write: bool) -> None:
    filepath = os.path.join(TEST_ROOT, "engine_data", filename)
    with open(filepath, "rb") as f:
        fixture = f.read()

    engine_data = EngineData.frombytes(fixture)
    output = engine_data.tobytes(indent=indent, write_container=write)
    assert output == fixture


@pytest.mark.parametrize(
    "filename",
    [
        "TySh_2.dat",
    ],
)
def test_engine_data_parse(filename: str) -> None:
    filepath = os.path.join(TEST_ROOT, "engine_data", filename)
    with open(filepath, "rb") as f:
        assert isinstance(EngineData.read(f), EngineData)


@pytest.mark.parametrize(
    "fixture",
    [
        b"0.0",
        b".4",
        b"-.4",
        b"1.0",
        b".00006",
        b"-47.55428",
    ],
)
def test_float(fixture: bytes) -> None:
    check_read_write(Float, fixture)


@pytest.mark.parametrize(
    "fixture",
    [
        b"(\xfe\xff0\x00)",
        b"(\xfe\xff0\x00\\) /1 \\(\xfe\xff\x001)",
        b"(\xfe\xff)",
        b"(\xfe\xffb\x10\\\\1\x00\r)",
    ],
)
def test_string(fixture: bytes) -> None:
    check_read_write(String, fixture)


def test_engine_data_property_without_a_value_raises_value_error() -> None:
    with pytest.raises(ValueError):
        EngineData2.frombytes(b"<< /A")
