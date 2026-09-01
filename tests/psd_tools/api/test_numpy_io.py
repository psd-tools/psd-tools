import logging
import os
from typing import Sequence

import numpy as np
import pytest

from psd_tools.api import numpy_io
from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import ColorMode, Compression
from psd_tools.psd.patterns import (
    Pattern,
    VirtualMemoryArray,
    VirtualMemoryArrayList,
)

from ..utils import TEST_ROOT, full_name

logger = logging.getLogger(__name__)


@pytest.mark.parametrize("filename", ["Patt_1.dat", "Patt_2.dat"])
def test_get_pattern(filename: str) -> None:
    filepath = os.path.join(TEST_ROOT, "tagged_blocks", filename)
    with open(filepath, "rb") as f:
        pattern = Pattern.read(f)

    assert isinstance(numpy_io.get_pattern(pattern), np.ndarray)


def _slotted_pattern(color_mode: ColorMode, written: Sequence[int], slots: int = 26):
    """A pattern whose *written* slots hold a 1x1 plane and the rest nothing."""
    channels = [VirtualMemoryArray(is_written=0) for _ in range(slots)]
    for index in written:
        channels[index] = VirtualMemoryArray(
            is_written=1,
            depth=8,
            rectangle=(0, 0, 1, 1),
            pixel_depth=8,
            compression=Compression.RAW,
            data=b"\xff",
        )
    return Pattern(
        image_mode=color_mode,
        point=(1, 1),
        data=VirtualMemoryArrayList(rectangle=(0, 0, 1, 1), channels=channels),
    )


@pytest.mark.parametrize(
    ("color_mode", "written", "expected"),
    [
        # The three layouts Photoshop 2026 ships in Presets/Patterns/*.pat.
        (ColorMode.RGB, (0, 1, 2), 3),
        (ColorMode.RGB, (0, 1, 2, 25), 3),
        (ColorMode.GRAYSCALE, (0,), 1),
        # The same layouts under multichannel, whose count no constant fixes:
        # its EXPECTED_CHANNELS entry is the format's 64-channel maximum, so a
        # mode-keyed split could never fire at all (#741).
        (ColorMode.MULTICHANNEL, (0, 1, 2), 3),
        (ColorMode.MULTICHANNEL, (0, 1, 2, 25), 3),
        (ColorMode.MULTICHANNEL, (0, 25), 1),
        # Where the mode's constant and the slot layout agree, so the count is
        # what it always was -- these pin that the rule change moved nothing.
        (ColorMode.CMYK, (0, 1, 2, 3, 25), 4),
        # One colour plane and an alpha, under modes whose constant is wider
        # than that. The mode-keyed rule compared 2 against 3 and split
        # nothing here too, so multichannel was not the only mode carrying the
        # bug -- it is just the only one whose constant can never be reached.
        (ColorMode.RGB, (0, 25), 1),
        (ColorMode.INDEXED, (0, 25), 1),
    ],
)
def test_get_pattern_color_channels(
    color_mode: ColorMode, written: tuple, expected: int
) -> None:
    """The color count is the written slots in the color region, mode aside.

    ``len(channels) - 2`` slots are color -- 24 as Photoshop writes them,
    regardless of how many the pattern uses -- and the last of the remaining
    two carries transparency.
    """
    pattern = _slotted_pattern(color_mode, written)

    count = numpy_io.get_pattern_color_channels(pattern)

    assert count == expected
    # What the callers do with the count: everything past it is taken as the
    # alpha in one slice, so the split has to leave one trailing plane or none.
    # A count that stranded a color plane on the far side would pass the
    # equality above and still hand the canvas a plane of the wrong kind.
    assert numpy_io.get_pattern(pattern).shape[2] - count in (0, 1)


@pytest.mark.parametrize("written", [(25,), (24, 25)])
def test_get_pattern_color_channels_degrades_without_a_color_slot(
    written: tuple,
) -> None:
    """Nothing in the color slots says nothing about where the boundary is.

    Rather than split at zero and hand back an empty color array, take every
    written plane as color: a pattern rendered without its alpha is worth more
    than one that cannot be read at all.
    """
    pattern = _slotted_pattern(ColorMode.MULTICHANNEL, written)

    count = numpy_io.get_pattern_color_channels(pattern)

    assert count == len(written)
    assert count == numpy_io.get_pattern(pattern).shape[2]


@pytest.mark.parametrize(
    "colormode, depth",
    [
        ("bitmap", 1),
        ("cmyk", 8),
        ("duotone", 8),
        ("grayscale", 8),
        ("index_color", 8),
        ("rgb", 8),
        ("rgba", 8),
        ("lab", 8),
        ("multichannel", 16),
        # Depth 32 was missing from this sweep, which is part of why #738 stood:
        # it is the one branch of `_parse_array` that does no rescaling, so it
        # is the one that returned the raw buffer's dtype and mutability.
        ("grayscale", 32),
        ("rgb", 32),
    ],
)
def test_numpy_colormodes(colormode: str, depth: int) -> None:
    filename = "colormodes/4x4_%gbit_%s.psd" % (depth, colormode)
    psd = PSDImage.open(full_name(filename))
    array = psd.numpy()
    assert isinstance(array, np.ndarray)
    _assert_array_contract(array)
    for layer in psd:
        layer_array = layer.numpy()
        assert isinstance(layer_array, (np.ndarray, type(None)))
        if layer_array is not None:
            _assert_array_contract(layer_array)


def _assert_array_contract(array: np.ndarray) -> None:
    """What every depth returns, which depth 32 alone did not (#738).

    Native ``float32`` and writeable. The other three branches get both for
    free from the ``.astype()`` their rescaling needs; 32-bit data needs no
    rescaling, so it was handed back as ``np.frombuffer`` produced it -- a
    read-only view carrying the file's big-endian dtype.
    """
    assert array.dtype == np.float32, array.dtype
    assert array.dtype.byteorder in ("=", "|"), array.dtype.byteorder
    assert array.flags.writeable


@pytest.mark.parametrize("filename", ["transparentbg.psd", "transparentbg.psb"])
def test_numpy_reads_a_32bit_document_with_transparency(filename: str) -> None:
    """``numpy()`` raised on an ordinary Photoshop file shape (#738).

    ``_remove_background()`` un-premultiplies the merged preview in place, and
    it is reached only for RGB with a transparency channel -- so depth 32's
    read-only array raised ``assignment destination is read-only`` there and
    nowhere else. These two fixtures have shipped all along and reproduce it;
    the issue was filed believing none did.
    """
    psd = PSDImage.open(full_name(filename))
    assert (psd.depth, psd.color_mode, psd.channels) == (32, ColorMode.RGB, 4)

    array = psd.numpy()  # would raise ValueError
    _assert_array_contract(array)
    assert array.shape == (psd.height, psd.width, 4)
    assert psd.numpy("color").shape == (psd.height, psd.width, 3)
    assert psd.numpy("shape").shape == (psd.height, psd.width, 1)

    # Not merely non-raising: where the preview is opaque there is nothing to
    # un-premultiply, so the colour has to agree with `topil()` -- which took
    # the `Image.frombytes` path and worked throughout.
    preview = np.asarray(psd.topil()).astype(np.float32) / 255.0
    opaque = array[:, :, 3] > 0.999
    assert opaque.any()
    assert np.abs(array[:, :, :3][opaque] - preview[:, :, :3][opaque]).max() == 0.0


def test_parse_array_does_not_alias_its_input() -> None:
    """The mutability half, at the unit rather than the document level.

    Writing into what ``_parse_array`` returns must not reach back into the
    caller's buffer. A ``bytearray`` is used because the read-only-ness of the
    ``bytes`` the real callers pass is what masked this: over a mutable buffer
    ``np.frombuffer`` yields a *writeable* view, so the alias would be silent
    corruption rather than a raise.
    """
    source = bytearray(np.arange(4, dtype=">f4").tobytes())
    parsed = numpy_io._parse_array(source, 32, 4)
    assert np.array_equal(parsed, np.arange(4, dtype=np.float32))
    parsed[0] = 99.0
    assert bytearray(np.arange(4, dtype=">f4").tobytes()) == source
