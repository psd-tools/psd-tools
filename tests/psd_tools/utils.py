import fnmatch
import io
import logging
import os
from collections.abc import Generator
from typing import Any, TypeVar

from psd_tools.psd.base import BaseElement
from psd_tools.psd.bin_utils import trimmed_repr

T = TypeVar("T", bound=BaseElement)

logging.basicConfig(level=logging.DEBUG)

# Use maccyrillic encoding.
CYRILLIC_FILES = {
    "layer_mask_data.psb",
    "layer_mask_data.psd",
    "layer_params.psb",
    "layer_params.psd",
    "layer_comps.psb",
    "layer_comps.psd",
}

# Unknown encoding.
OTHER_FILES = {
    "advanced-blending.psd",
    "effect-stroke-gradient.psd",
    "layer_effects.psd",
    "patterns.psd",
    "fill_adjustments.psd",
    "blend-and-clipping.psd",
    "clipping-mask2.psd",
}

TEST_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


def find_files(
    pattern: str = "*.ps*", root: str = TEST_ROOT
) -> Generator[str, None, None]:
    for r, _, filenames in os.walk(root):
        for filename in fnmatch.filter(filenames, pattern):
            yield os.path.join(r, filename)


def full_name(filename: str) -> str:
    return os.path.join(TEST_ROOT, "psd_files", filename)


def all_files() -> list[str]:
    return [f for f in find_files() if f.find("third-party-psds") < 0]


def check_write_read(element: T, *args: Any, **kwargs: Any) -> None:
    f = io.BytesIO()
    element.write(f, *args, **kwargs)
    f.seek(0)
    new_element = element.read(f, *args, **kwargs)
    assert element == new_element, f"{element} vs {new_element}"


def check_read_write(cls: type[T], data: bytes, *args: Any, **kwargs: Any) -> None:
    element = cls.frombytes(data, *args, **kwargs)
    new_data = element.tobytes(*args, **kwargs)
    assert data == new_data, f"{trimmed_repr(data)} vs {trimmed_repr(new_data)}"
