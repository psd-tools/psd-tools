import struct

import pytest

from psd_tools.psd.parse_limits import ParseLimitError
from psd_tools.psd.vector import Path, ClosedPath, OpenPath

from ..utils import check_read_write


@pytest.mark.parametrize(
    "fixture",
    [
        b"\x00\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x00\x04\x00\x01\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00 \x00\x00\x00X"
        b"\xe8\xf2\x00 \x00\x00\x00tz\xe1\x00 \x00\x00\x00\x90\x0c\xcf\x00\x01"
        b"\x004\xa1w\x00\xa6ff\x00N\x14z\x00\xa6ff\x00g\x87~\x00\xa6ff\x00\x01"
        b"\x00|(\xf5\x00\x90\x0c\xcf\x00|(\xf5\x00tz\xe1\x00|(\xf5\x00X\xe8"
        b"\xf2\x00\x01\x00g\x87~\x00B\x8f\\\x00N\x14z\x00B\x8f\\\x004\xa1w"
        b"\x00B\x8f\\\x00\x00"
    ],
)
def test_path_rw(fixture: bytes) -> None:
    check_read_write(Path, fixture)


def test_subpath_repr() -> None:
    closedpath = ClosedPath()
    assert repr(closedpath) == "ClosedPath(index=0, operation=1)"
    openpath = OpenPath()
    assert repr(openpath) == "OpenPath(index=0, operation=1)"


def test_nested_subpaths_raise_a_parse_limit_error() -> None:
    header = struct.pack(">HhH2I10s", 1, 1, 1, 0, 0, b"\0" * 10)
    payload = (struct.pack(">H", 0) + header) * 500 + b"\0" * 64
    with pytest.raises(ParseLimitError):
        Path.frombytes(payload)
