import logging
import os
import tracemalloc
from typing import Sequence

import numpy as np
import pytest

from psd_tools.api import numpy_io, utils
from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import ColorMode, Compression, Resource, Tag
from psd_tools.psd.patterns import (
    Pattern,
    VirtualMemoryArray,
    VirtualMemoryArrayList,
)
from psd_tools.terminology import Key

from ..test_pixel_size import _forge
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
        # Where the mode's constant and the slot layout agree, so a mode-keyed
        # rule and a slot-keyed one give the same count.
        (ColorMode.CMYK, (0, 1, 2, 3, 25), 4),
        # One colour plane and an alpha, under modes whose constant is wider
        # than that. A mode-keyed rule comparing 2 against 3 splits nothing
        # here either, so multichannel is not the only mode that needs the
        # slot layout -- it is just the only one whose constant is
        # unreachable.
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
        # Depth 32 earns its place in this sweep (#738): it is the one branch
        # of `_parse_array` that does no rescaling, so it is the one that can
        # hand back the raw buffer's dtype and mutability.
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
    """What every depth returns, depth 32 included (#738).

    Native ``float32`` and writeable. The other three branches get both for
    free from the ``.astype()`` their rescaling needs; 32-bit data needs no
    rescaling, so handing it back as ``np.frombuffer`` produces it gives a
    read-only view carrying the file's big-endian dtype.
    """
    assert array.dtype == np.float32, array.dtype
    assert array.dtype.byteorder in ("=", "|"), array.dtype.byteorder
    assert array.flags.writeable


@pytest.mark.parametrize("filename", ["transparentbg.psd", "transparentbg.psb"])
def test_numpy_reads_a_32bit_document_with_transparency(filename: str) -> None:
    """``numpy()`` on an ordinary Photoshop file shape (#738).

    ``_remove_background()`` un-premultiplies the merged preview in place, and
    it is reached only for RGB with a transparency channel -- so a read-only
    depth-32 array raises ``assignment destination is read-only`` there and
    nowhere else. These two shipped fixtures are the corpus's cases.
    """
    psd = PSDImage.open(full_name(filename))
    assert (psd.depth, psd.color_mode, psd.channels) == (32, ColorMode.RGB, 4)

    array = psd.numpy()  # raises ValueError where the array is read-only
    _assert_array_contract(array)
    assert array.shape == (psd.height, psd.width, 4)
    assert psd.numpy("color").shape == (psd.height, psd.width, 3)
    assert psd.numpy("shape").shape == (psd.height, psd.width, 1)

    # Not merely non-raising: where the preview is opaque there is nothing to
    # un-premultiply, so the colour has to agree with `topil()`, which reaches
    # the same pixels by the `Image.frombytes` path.
    preview = np.asarray(psd.topil()).astype(np.float32) / 255.0
    opaque = array[:, :, 3] > 0.999
    assert opaque.any()
    assert np.abs(array[:, :, :3][opaque] - preview[:, :, :3][opaque]).max() == 0.0


def test_parse_array_does_not_alias_its_input() -> None:
    """The mutability half, at the unit rather than the document level.

    Writing into what ``_parse_array`` returns must not reach back into the
    caller's buffer. A ``bytearray`` is used because the read-only-ness of the
    ``bytes`` real callers pass would hide an alias: over a mutable buffer
    ``np.frombuffer`` yields a *writeable* view, so the alias is silent
    corruption rather than a raise.
    """
    source = bytearray(np.arange(4, dtype=">f4").tobytes())
    parsed = numpy_io._parse_array(source, 32, 4)
    assert np.array_equal(parsed, np.arange(4, dtype=np.float32))
    parsed[0] = 99.0
    assert bytearray(np.arange(4, dtype=">f4").tobytes()) == source


def _forged_pattern(side: int, compression: Compression) -> Pattern:
    """The fixture's pattern, every written channel re-declared ``side`` square."""
    psd = PSDImage.open(full_name("layers-minimal/pattern-fill.psd"))
    desc = psd[0].tagged_blocks.get_data(Tag.PATTERN_FILL_SETTING)
    pattern = psd._get_pattern(desc[b"Ptrn"][Key.ID].value.rstrip("\x00"))
    assert pattern is not None
    for c in pattern.data.channels:
        if c.is_written:
            c.rectangle = (0, 0, side, side)
            c.compression = compression
            c.data = b"\x00" * (2 * side)
    pattern.data.rectangle = (0, 0, side, side)
    return pattern


def _rle_peak(side: int, planes: int) -> int:
    return numpy_io._layer_read_peak_bytes(
        side, side, 8, planes, numpy_io._DECOMPRESS_PEAK[Compression.RLE]
    )


def test_a_forged_pattern_size_is_checked_before_the_decode() -> None:
    side = 1000
    pattern = _forged_pattern(side, Compression.RLE)
    planes = sum(1 for c in pattern.data.channels if c.is_written)
    peak = _rle_peak(side, planes)

    assert numpy_io.get_pattern(pattern, peak).shape == (side, side, planes)
    with pytest.raises(ValueError, match="over the configured budget"):
        numpy_io.get_pattern(pattern, peak - 1)


def test_a_forged_pattern_axis_past_the_limit_is_rejected() -> None:
    pattern = _forged_pattern(utils.MAX_DIMENSION_PSD + 1, Compression.RLE)
    with pytest.raises(ValueError, match="per axis"):
        numpy_io.get_pattern(pattern)


def test_the_pattern_estimate_covers_the_decode_peak() -> None:
    side = 1000
    pattern = _forged_pattern(side, Compression.RLE)
    planes = sum(1 for c in pattern.data.channels if c.is_written)
    tracemalloc.start()
    try:
        numpy_io.get_pattern(pattern)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # Fixed interpreter-side objects are not modelled, as for layer reads.
    assert peak <= _rle_peak(side, planes) + 65536


def test_a_pattern_whose_depths_disagree_is_rejected_before_the_decode() -> None:
    pattern = _forged_pattern(1000, Compression.RLE)
    (first,) = [c for c in pattern.data.channels if c.is_written][:1]
    first.depth = 32
    with pytest.raises(ValueError, match="disagrees"):
        numpy_io.get_pattern(pattern)


@pytest.mark.parametrize("size", [9, 10])
def test_a_short_color_table_is_a_value_error(size: int) -> None:
    """A truncated table is rejected with a catchable error, not an IndexError."""
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_index_color.psd"))
    psd._record.color_mode_data.value = psd._record.color_mode_data.value[:size]

    for read in (psd.numpy, psd.topil, psd.composite):
        with pytest.raises(ValueError, match="Color table"):
            read()


def test_an_overlong_color_table_reads_the_first_256_entries() -> None:
    """Planes are 256 bytes apart whatever follows them; trailing bytes are ignored."""
    psd = PSDImage.open(full_name("colormodes/4x4_8bit_index_color.psd"))
    table = bytes(range(256)) + bytes(range(255, -1, -1)) + bytes([7] * 256)
    psd._record.color_mode_data.value = table
    expected = psd.numpy()

    psd._record.color_mode_data.value = table + b"\x01\x02\x03"
    assert np.array_equal(psd.numpy(), expected)


@pytest.mark.composite
def test_numpy_unmattes_a_grayscale_preview_like_the_rgb_one() -> None:
    """``GRAYSCALE`` previews are stored over white and read back through it.

    Photoshop composites the merged preview over white for a grayscale document
    the way it does for RGB, so a read that keeps the stored plane returns that
    composite rather than the layer colour. ``composite()`` is the independent
    answer for what that colour is, and the PIL path has to land on it too.
    """
    from psd_tools.composite import composite  # noqa: PLC0415

    psd = PSDImage.open(full_name("gray0.psd"))
    array = psd.numpy()
    assert array is not None
    color, _, alpha = composite(psd)
    a = alpha[:, :, 0]
    partial = (a > 0.1) & (a < 0.9)
    assert partial.sum() > 1000

    assert np.abs(array[:, :, 0][partial] - color[:, :, 0][partial]).mean() < 0.01

    image = psd.topil()
    assert image is not None
    preview = np.asarray(image).astype(np.float32) / 255.0
    assert np.abs(preview[:, :, 0][partial] - color[:, :, 0][partial]).mean() < 0.02


@pytest.mark.composite
def test_a_grayscale_preview_without_a_profile_is_unmatted_as_la() -> None:
    """The ``LA`` branch of the removal, which no shipped fixture reaches.

    ``gray0.psd`` carries a profile, so ``post_process()`` converts its preview
    to RGB and ``_remove_white_background()`` arrives at an ``RGBA`` image.
    Without one that conversion never happens and the preview stays ``LA``, which
    the removal has to undo the white background of just the same (#868).
    """
    from psd_tools.composite import composite  # noqa: PLC0415

    psd = PSDImage.open(full_name("gray0.psd"))
    del psd._record.image_resources[Resource.ICC_PROFILE]
    image = psd.topil()
    assert image is not None
    assert image.mode == "LA"

    color, _, alpha = composite(psd)
    a = alpha[:, :, 0]
    partial = (a > 0.1) & (a < 0.9)
    preview = np.asarray(image).astype(np.float32) / 255.0
    assert np.abs(preview[:, :, 0][partial] - color[:, :, 0][partial]).mean() < 0.01


def test_a_duotone_preview_is_not_unmatted_as_la() -> None:
    """Duotone shares PIL's ``LA`` mode without sharing the convention.

    No duotone document with transparency is shipped, so nothing settles whether
    Photoshop stores one over white. The read is left as it stands rather than
    guessed at, which keeps ``topil()`` and ``numpy()`` on the same plane -- the
    two go on being read the same way, which is the whole of the fix (#868).
    """
    psd = _forge(4, 4, 2, 8, ColorMode.DUOTONE)
    assert utils.has_transparency(psd)
    image = psd.topil()
    assert image is not None
    assert image.mode == "LA"

    array = psd.numpy()
    assert array is not None
    preview = np.asarray(image).astype(np.float32) / 255.0
    assert np.abs(preview[:, :, 0] - array[:, :, 0]).max() < 1 / 255
