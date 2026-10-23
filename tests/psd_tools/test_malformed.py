"""Malformed data raises only ValueError or OSError from the calls that read a document.

Byte-mutates each fixture with a seed taken from its name, so a run is
repeatable. Opt in with ``--mutants N`` variants per fixture; the default
skips it.
"""

import contextlib
import io
import os
import random
from collections.abc import Callable

import pytest

from psd_tools import PSDImage
from psd_tools.psd.parse_limits import ParseLimits
from tests.conftest import HAS_COMPOSITE
from tests.psd_tools.utils import all_files

MAX_FIXTURE_BYTES = 500_000
LIMITS = ParseLimits(max_read_bytes=64 << 20, max_total_bytes=256 << 20)
BUDGET = 256 << 20
HEAD_BYTES = 4096

FIXTURES = sorted(f for f in all_files() if os.path.getsize(f) <= MAX_FIXTURE_BYTES)


def mutate(data: bytes, rng: random.Random) -> tuple[bytes, str]:
    kind = rng.choice(["flip", "flip", "head", "truncate"])
    buf = bytearray(data)
    if kind == "truncate":
        cut = rng.randrange(1, len(buf))
        return bytes(buf[:cut]), f"truncate at {cut}"
    changed = []
    span = len(buf) if kind == "flip" else min(len(buf), HEAD_BYTES)
    for offset in rng.sample(range(span), min(span, rng.randint(1, 8))):
        value = (buf[offset] + rng.randrange(1, 256)) % 256
        buf[offset] = value
        changed.append(f"{offset}={value}")
    return bytes(buf), f"{kind} " + ",".join(changed)


def read_everything(data: bytes) -> None:
    try:
        psd = PSDImage.open(
            io.BytesIO(data), max_alloc_bytes=BUDGET, parse_limits=LIMITS
        )
    except (ValueError, OSError):
        return
    calls: list[Callable[[], object]] = [psd.numpy, psd.topil, psd.thumbnail]
    if HAS_COMPOSITE:
        calls.append(lambda: psd.composite(force=True))
    for call in calls:
        with contextlib.suppress(ValueError, OSError):
            call()
    with contextlib.suppress(ValueError, OSError):
        for layer in psd.descendants():
            for layer_call in (layer.numpy, layer.topil):
                with contextlib.suppress(ValueError, OSError):
                    layer_call()


@pytest.mark.parametrize("path", FIXTURES, ids=os.path.basename)
def test_malformed_raises_only_value_or_os_error(
    path: str, request: pytest.FixtureRequest
) -> None:
    count = request.config.getoption("--mutants")
    if not count:
        pytest.skip("pass --mutants N to mutate each fixture N times")
    with open(path, "rb") as f:
        data = f.read()
    rng = random.Random(os.path.basename(path))
    for _ in range(count):
        mutated, description = mutate(data, rng)
        try:
            read_everything(mutated)
        except Exception as e:
            raise AssertionError(
                f"{type(e).__name__} escaped from {os.path.basename(path)}: {description}"
            ) from e
