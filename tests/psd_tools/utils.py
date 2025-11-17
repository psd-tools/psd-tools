import fnmatch
import logging
import os
import tempfile
from typing import Any, Generator, List, Type, TypeVar

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


def all_files() -> List[str]:
    return [f for f in find_files() if f.find("third-party-psds") < 0]


def check_write_read(element: T, *args: Any, **kwargs: Any) -> None:
    with tempfile.TemporaryFile() as f:
        element.write(f, *args, **kwargs)
        f.flush()
        f.seek(0)
        new_element = element.read(f, *args, **kwargs)
    assert element == new_element, "%s vs %s" % (element, new_element)


def check_read_write(cls: Type[T], data: bytes, *args: Any, **kwargs: Any) -> None:
    element = cls.frombytes(data, *args, **kwargs)
    new_data = element.tobytes(*args, **kwargs)
    assert data == new_data, "%s vs %s" % (trimmed_repr(data), trimmed_repr(new_data))
