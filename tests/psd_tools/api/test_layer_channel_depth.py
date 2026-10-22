"""What a layer's channels are packed as when the API writes them (#867).

Every write path that builds channel data from a PIL image takes the depth from
the header, never from the image. A PIL image holds a byte per pixel whatever
it describes, so taking the depth from it gives a 16- or 32-bit document
channels a half or a quarter of the length its geometry requires, and the layer
reads back empty -- the sibling defect to #866, in the layer path rather than
the merged image data one.

The same rule reaches three places: ``PixelLayer.frompil()`` and everything
that calls it, ``create_mask()``/``update_mask()`` -- a mask is stored at the
document's depth too, as the corpus's 16- and 32-bit masks show -- and
``_reencode()``, which re-encodes a layer moved between documents and so
has to consult the destination's depth and its file version.

A note on what these assert. ``len(ChannelData.data)`` is the *compressed*
length, so the length tests build their layers with ``Compression.RAW``, where
it is the channel length; under RLE the reader pads every short row back out to
the full row size, so a length assertion cannot see a short channel at all.
For the same reason the value tests compare whole arrays and use a non-uniform
image at least three pixels wide: an 8-bit row read as 16-bit pairs its own
bytes, so ``0x80, 0x80`` decodes to 0.50196 -- exactly the right answer -- and
the first pixel or two of a flat layer read correct however it was packed.
"""

import io
from typing import Any, Literal, cast

import numpy as np
import pytest
from PIL import Image

import psd_tools.api.numpy_io as numpy_io
from psd_tools.api.layers import _reencoded
from psd_tools.api.pil_io import encode_channel, encode_opaque_channel
from psd_tools.api.psd_image import PSDImage
from psd_tools.compression import _row_size
from psd_tools.constants import BlendMode, ChannelID, ColorMode, Compression

from ..utils import full_name

DEPTHS: tuple[Literal[8, 16, 32], ...] = (8, 16, 32)

# Three rows of five, no two pixels alike and nothing on the neutral axis, so
# that a partially decoded channel cannot pass for a decoded one.
COLORS = np.arange(3 * 5 * 3, dtype=np.uint8).reshape(3, 5, 3) * 5 + 3
MASK = np.arange(3 * 5, dtype=np.uint8).reshape(3, 5) * 17 + 1

# A mask of a different size from the layer, and offset from it. A channel is
# decompressed against its own rectangle, and a mask's is not the layer's, so
# a move test whose mask happens to share the layer's rectangle cannot tell a
# geometry lookup that reads the mask's bounds from one that ignores them.
OFFSET_MASK = np.arange(4 * 6, dtype=np.uint8).reshape(4, 6) * 10 + 1
LAYER_TOP, LAYER_LEFT = 2, 1
MASK_TOP, MASK_LEFT = 3, 0


def _image(mode: str = "RGB") -> Image.Image:
    return Image.fromarray(COLORS, "RGB").convert(mode)


def _channel_lengths(layer: Any) -> list[int]:
    return [len(channel.data) for channel in layer._channels]


@pytest.mark.parametrize("depth", DEPTHS)
@pytest.mark.parametrize("mode", ["RGB", "L", "CMYK", "LAB"])
def test_a_new_layers_channels_are_the_documents_length(
    depth: Literal[8, 16, 32], mode: str
) -> None:
    """Every channel occupies the bytes its geometry needs at the header depth."""
    psd = PSDImage.new(mode, (16, 16), depth=depth)
    layer = psd.create_pixel_layer(_image(mode), name="L", compression=Compression.RAW)

    expected = _row_size(layer.width, depth) * layer.height
    assert _channel_lengths(layer) == [expected] * len(layer._channels)


@pytest.mark.parametrize("depth", DEPTHS)
def test_a_new_layer_reads_back_the_image_it_was_given(
    depth: Literal[8, 16, 32],
) -> None:
    """The values are widened, not truncated: 128 is 32896 at depth 16."""
    psd = PSDImage.new("RGB", (16, 16), depth=depth)
    layer = psd.create_pixel_layer(_image(), name="L")

    array = layer.numpy()
    assert array is not None
    np.testing.assert_allclose(array[:, :, :3], COLORS / 255.0, atol=1e-6)
    # The transparency channel the layer was given no alpha for.
    np.testing.assert_allclose(array[:, :, 3], 1.0)


@pytest.mark.parametrize("depth", DEPTHS)
def test_the_widening_is_the_readers_own_inverse(depth: Literal[8, 16, 32]) -> None:
    """Spelled out once against the stored bytes rather than the decoded array."""
    psd = PSDImage.new("L", (16, 16), depth=depth)
    layer = psd.create_pixel_layer(
        Image.new("L", (4, 1), 128), name="L", compression=Compression.RAW
    )

    stored = layer._channels[1].data
    if depth == 8:
        assert stored == b"\x80" * 4
    elif depth == 16:
        assert stored == b"\x80\x80" * 4  # 128 * 257
    else:
        assert np.frombuffer(stored, ">f4") == pytest.approx([128 / 255.0] * 4)


@pytest.mark.parametrize("depth", DEPTHS)
def test_a_new_mask_is_the_documents_length_and_values(
    depth: Literal[8, 16, 32],
) -> None:
    """A mask is stored at the document's depth, not at a fixed eight bits."""
    psd = PSDImage.new("RGB", (16, 16), depth=depth)
    layer = psd.create_pixel_layer(_image(), name="L", compression=Compression.RAW)
    mask = layer.create_mask(Image.fromarray(MASK, "L"), compression=Compression.RAW)

    assert len(layer._channels[-1].data) == _row_size(mask.width, depth) * mask.height
    array = numpy_io.get_layer_data(layer, "mask")
    assert array is not None
    np.testing.assert_allclose(array[:, :, 0], MASK / 255.0, atol=1e-6)


@pytest.mark.parametrize("depth", DEPTHS)
def test_an_updated_mask_is_the_documents_length_and_values(
    depth: Literal[8, 16, 32],
) -> None:
    psd = PSDImage.new("RGB", (16, 16), depth=depth)
    layer = psd.create_pixel_layer(_image(), name="L")
    layer.create_mask(Image.new("L", (5, 3), 0))
    mask = layer.update_mask(Image.fromarray(MASK, "L"), compression=Compression.RAW)

    assert len(layer._channels[-1].data) == _row_size(mask.width, depth) * mask.height
    array = numpy_io.get_layer_data(layer, "mask")
    assert array is not None
    np.testing.assert_allclose(array[:, :, 0], MASK / 255.0, atol=1e-6)


@pytest.mark.parametrize("depth", DEPTHS)
def test_a_deep_document_composites_its_new_layer_after_a_save(
    depth: Literal[8, 16, 32], tmp_path: Any
) -> None:
    """The end the issue reports from: a saved deep document, reopened.

    The backdrop is white and the layer is not, so a layer that reads back
    empty composites as the backdrop alone.
    """
    pytest.importorskip("scipy")
    psd = PSDImage.new("RGB", (5, 3), color=1.0, depth=depth)
    psd.create_pixel_layer(_image(), name="L")
    path = tmp_path / "deep.psd"
    psd.save(str(path))

    reopened = PSDImage.open(str(path))
    composited = np.asarray(reopened.composite().convert("RGB"), dtype=np.float32)
    np.testing.assert_allclose(composited, COLORS, atol=1.5)


@pytest.mark.parametrize(
    "source_depth, dest_depth", [(8, 16), (16, 8), (16, 32), (32, 16), (8, 32)]
)
def test_a_depth_only_move_re_encodes_the_channels(
    source_depth: Literal[8, 16, 32], dest_depth: Literal[8, 16, 32]
) -> None:
    """Equal colour mode is not equal packing.

    Both documents are RGB, so ``pil_mode`` matches; carrying the layer across
    on that alone would leave it at the source's bytes per sample.

    The mask is deliberately a different size from the layer and at a
    different origin, so that the geometry each channel is repacked against
    has to come from that channel's own rectangle.
    """
    source = PSDImage.new("RGB", (16, 16), depth=source_depth)
    layer = source.create_pixel_layer(
        _image(), name="L", top=LAYER_TOP, left=LAYER_LEFT
    )
    layer.create_mask(Image.fromarray(OFFSET_MASK, "L"), top=MASK_TOP, left=MASK_LEFT)

    PSDImage.new("RGB", (16, 16), depth=dest_depth).append(layer)

    array = layer.numpy()
    assert array is not None
    np.testing.assert_allclose(array[:, :, :3], COLORS / 255.0, atol=1e-6)
    mask_array = numpy_io.get_layer_data(layer, "mask")
    assert mask_array is not None
    assert mask_array.shape == (*OFFSET_MASK.shape, 1)
    np.testing.assert_allclose(mask_array[:, :, 0], OFFSET_MASK / 255.0, atol=1e-6)
    assert all(len(channel.data) > 0 for channel in layer._channels)


def test_a_version_only_move_re_encodes_the_channels() -> None:
    """PSD to PSB. An RLE channel's row-length words are two bytes or four."""
    source = PSDImage.new("RGB", (16, 16), depth=8)
    layer = source.create_pixel_layer(
        _image(), name="L", top=LAYER_TOP, left=LAYER_LEFT
    )
    layer.create_mask(Image.fromarray(OFFSET_MASK, "L"), top=MASK_TOP, left=MASK_LEFT)

    destination = PSDImage.open(full_name("2layers.psb"))
    assert destination.version == 2 and source.version == 1
    destination.append(layer)

    array = layer.numpy()
    assert array is not None
    np.testing.assert_allclose(array[:, :, :3], COLORS / 255.0, atol=1e-6)
    mask_array = numpy_io.get_layer_data(layer, "mask")
    assert mask_array is not None
    assert mask_array.shape == (*OFFSET_MASK.shape, 1)
    np.testing.assert_allclose(mask_array[:, :, 0], OFFSET_MASK / 255.0, atol=1e-6)


def _decode_mask_channels(
    layer: Any, depth: Literal[1, 8, 16, 32], version: int
) -> dict[int, np.ndarray]:
    """Both mask channels, each read against its own rectangle.

    Spelled out here rather than taken from ``Layer._channel_geometry``, which
    is the thing under test, and not from ``get_layer_data``, which reads one
    of the two and picks which by ``has_real()``.
    """
    mask = layer._record.mask_data
    rectangles = {
        ChannelID.USER_LAYER_MASK: (mask.left, mask.top, mask.right, mask.bottom),
        ChannelID.REAL_USER_LAYER_MASK: (
            mask.real_left,
            mask.real_top,
            mask.real_right,
            mask.real_bottom,
        ),
    }
    decoded = {}
    for info, channel in zip(layer._record.channel_info, layer._channels, strict=True):
        if info.id not in rectangles:
            continue
        left, top, right, bottom = rectangles[info.id]
        width, height = right - left, bottom - top
        raw = channel.get_data(width, height, depth, version)
        decoded[info.id] = numpy_io._parse_array(raw, depth, width).reshape(
            height, width
        )
    return decoded


def test_a_depth_only_move_re_encodes_a_real_mask_channel() -> None:
    """A real mask's rectangle is not the user mask's, and both are stored.

    ``mask-density-layervectormask.psd`` is the corpus's case: its layers
    carry a ``REAL_USER_LAYER_MASK`` 32x8 next to a ``USER_LAYER_MASK``
    18x10. A repack that reads either channel against the other's rectangle
    gets a different number of rows.
    """
    psd = PSDImage.open(full_name("mask-density-layervectormask.psd"))
    layer = next(item for item in psd.descendants() if item.name == "Layer 1")
    mask = layer._record.mask_data
    assert mask is not None
    real = (mask.real_left, mask.real_top, mask.real_right, mask.real_bottom)
    assert None not in real
    assert (mask.right - mask.left, mask.bottom - mask.top) != (
        cast(int, real[2]) - cast(int, real[0]),
        cast(int, real[3]) - cast(int, real[1]),
    )
    before = _decode_mask_channels(layer, 8, 1)
    assert set(before) == {
        ChannelID.USER_LAYER_MASK,
        ChannelID.REAL_USER_LAYER_MASK,
    }

    PSDImage.new("RGB", (32, 32), depth=16).append(layer)

    after = _decode_mask_channels(layer, 16, 1)
    assert set(after) == set(before)
    for channel_id, expected in before.items():
        np.testing.assert_allclose(after[channel_id], expected, atol=1e-6)


def test_a_cross_mode_move_re_encodes_at_the_destinations_version() -> None:
    """The other half of the version rule, on the branch PIL drives.

    A grayscale v1 document into an RGB v2 one: the colour mode differs, so
    the layer is re-rendered through PIL -- and that render has to be written
    with the *destination* file's version, or two-byte row counts land in a
    file whose reader takes four.
    """
    source = PSDImage.new("L", (16, 16), depth=8)
    layer = source.create_pixel_layer(_image("L"), name="L")
    expected = np.asarray(_image("L"), dtype=np.float32) / 255.0

    destination = PSDImage.open(full_name("2layers.psb"))
    assert destination.version == 2 and source.version == 1
    assert destination.pil_mode != source.pil_mode
    destination.append(layer)

    array = layer.numpy()
    assert array is not None
    for plane in range(3):
        np.testing.assert_allclose(array[:, :, plane], expected, atol=1e-6)


def test_a_depth_only_move_keeps_the_layer_record() -> None:
    """A guard, not evidence for #867.

    Nothing here distinguishes a re-encoded move from one that leaves the
    channels alone. It is asserted so that re-encoding a depth-only move can
    never be done by routing it through the ``pil_mode`` branch, which
    rebuilds the record from scratch and drops all of this.
    """
    source = PSDImage.new("RGB", (16, 16), depth=8)
    layer = source.create_pixel_layer(_image(), name="L")
    layer.create_mask(Image.fromarray(MASK, "L"))
    layer.opacity = 77
    layer.blend_mode = BlendMode.MULTIPLY

    PSDImage.new("RGB", (16, 16), depth=16).append(layer)

    assert layer.opacity == 77
    assert layer.blend_mode == BlendMode.MULTIPLY
    assert layer.has_mask()


@pytest.mark.parametrize("dest_depth", [8, 16])
def test_a_cross_mode_move_keeps_the_layer_record(dest_depth: Literal[8, 16]) -> None:
    source = PSDImage.new("RGB", (16, 16), depth=8)
    layer = source.create_pixel_layer(_image(), name="L")
    layer.create_mask(Image.fromarray(MASK, "L"))
    layer.opacity = 77
    layer.blend_mode = BlendMode.MULTIPLY

    PSDImage.new("CMYK", (16, 16), depth=dest_depth).append(layer)

    assert layer.opacity == 77
    assert layer.blend_mode == BlendMode.MULTIPLY
    assert layer.has_mask()
    ids = [info.id for info in layer._record.channel_info]
    assert ids == [-1, 0, 1, 2, 3, -2]
    assert layer.mask is not None
    mask = layer.mask.topil()
    assert mask is not None
    np.testing.assert_array_equal(np.asarray(mask), MASK)


@pytest.mark.parametrize("mode", ["RGB", "CMYK"])
def test_a_mask_read_before_a_move_still_edits_the_record(mode: str) -> None:
    source = PSDImage.new("RGB", (16, 16), depth=8)
    layer = source.create_pixel_layer(_image(), name="L")
    layer.create_mask(Image.fromarray(MASK, "L"))
    assert layer.mask is not None

    PSDImage.new(cast(Any, mode), (16, 16), depth=16).append(layer)
    layer.mask.disabled = True

    assert layer._record.mask_data is not None
    assert layer._record.mask_data.flags.mask_disabled


def test_reencoded_leaves_its_arguments_alone() -> None:
    source = PSDImage.new("RGB", (16, 16), depth=8)
    layer = source.create_pixel_layer(_image(), name="L")
    layer.create_mask(Image.fromarray(MASK, "L"))
    record, channels = layer._record, layer._channels
    before = (record.channel_info[:], [c.data for c in channels])
    dest = PSDImage.new("CMYK", (16, 16), depth=16)._record.header

    new_record, new_channels = _reencoded(
        record, channels, source._record.header, dest, _image().convert("CMYK")
    )

    assert new_record is not record
    assert new_channels is not channels
    assert (record.channel_info, [c.data for c in channels]) == before
    assert [info.id for info in record.channel_info] == [-1, 0, 1, 2, -2]
    assert [info.id for info in new_record.channel_info] == [-1, 0, 1, 2, 3, -2]


def test_a_cross_mode_move_into_a_deep_document_uses_that_depth() -> None:
    """The two halves of the rule at once: PIL converts, the header packs."""
    source = PSDImage.new("RGB", (16, 16), depth=8)
    layer = source.create_pixel_layer(_image(), name="L")

    PSDImage.new("CMYK", (16, 16), depth=16).append(layer)

    expected = _row_size(layer.width, 16) * layer.height
    for info, channel in zip(layer._record.channel_info, layer._channels, strict=True):
        assert len(channel.get_data(layer.width, layer.height, 16)) == expected, info.id
    array = layer.numpy()
    assert array is not None
    assert array.shape[2] == 5  # CMYK plus transparency
    # A layer created in the CMYK document directly is the oracle for what a
    # moved one must read back as, inversion included.
    direct = PSDImage.new("CMYK", (16, 16), depth=16).create_pixel_layer(_image())
    ink = direct.numpy()
    assert ink is not None
    np.testing.assert_allclose(array[:, :, :4], ink[:, :, :4], atol=1e-4)
    np.testing.assert_allclose(array[:, :, 4], 1.0)


class TestBitmapDocuments:
    r"""Depth 1, where the encoding's *sense* is under test, not just its length.

    A set bit is black, so a fully opaque transparency channel is a run of
    zeros. No fixture has a depth-1 layer or mask channel and Photoshop does
    not author layers in bitmap mode, so there is no ground truth here. What
    these assert is that the write is the reader's own inverse. A 16-byte
    ``b"\xff"`` transparency for a 4x4 layer is four times too long and, read
    as bits, fully *transparent*.
    """

    def test_a_1bit_layer_is_one_bit_per_pixel_and_opaque(self) -> None:
        psd = PSDImage.open(full_name("colormodes/4x4_1bit_bitmap.psd"))
        assert psd.depth == 1
        layer = psd.create_pixel_layer(
            Image.new("1", (4, 4), 1), name="L", compression=Compression.RAW
        )

        assert _channel_lengths(layer) == [_row_size(4, 1) * 4] * 2
        array = layer.numpy()
        assert array is not None
        np.testing.assert_allclose(array, 1.0)

    def test_zip_with_prediction_is_downgraded_at_depth_1(self) -> None:
        """``encode_prediction`` has no depth-1 branch; plain ZIP is stored."""
        psd = PSDImage.open(full_name("colormodes/4x4_1bit_bitmap.psd"))
        layer = psd.create_pixel_layer(
            Image.new("1", (4, 4), 1),
            name="L",
            compression=Compression.ZIP_WITH_PREDICTION,
        )

        assert all(c.compression == Compression.ZIP for c in layer._channels)
        array = layer.numpy()
        assert array is not None
        np.testing.assert_allclose(array, 1.0)

    def test_a_bitmap_band_is_stored_as_packed_bits_at_depth_1(self) -> None:
        """``PSDImage.new("1", ...)`` builds a BITMAP header at depth *1*.

        What this pins is that the channel matches the depth the header
        declares: a "1" band's ``tobytes()`` is bit-packed, which is a byte per
        pixel only by accident and never for a row of more than eight.
        """
        psd = PSDImage.new("1", (20, 3))
        assert psd.color_mode == ColorMode.BITMAP and psd.depth == 1
        layer = psd.create_pixel_layer(
            Image.new("1", (20, 3), 1), name="L", compression=Compression.RAW
        )

        assert _channel_lengths(layer) == [_row_size(20, 1) * 3] * 2


class TestEncoders:
    """The two packers, against the reader they have to invert."""

    @pytest.mark.parametrize("depth", [1, 8, 16, 32])
    def test_encode_channel_inverts_parse_array(self, depth: int) -> None:
        band = Image.fromarray(MASK, "L")
        if depth == 1:
            band = band.point(lambda value: 255 if value > 128 else 0).convert("L")

        encoded = encode_channel(band, depth)  # type: ignore[arg-type]
        parsed = numpy_io._parse_array(encoded, depth, band.width)  # type: ignore[arg-type]

        expected = np.asarray(band, dtype=np.float32).ravel() / 255.0
        np.testing.assert_allclose(parsed, expected, atol=1e-6)

    @pytest.mark.parametrize("depth", [1, 8, 16, 32])
    def test_an_opaque_channel_reads_back_opaque(self, depth: int) -> None:
        encoded = encode_opaque_channel(5, 3, depth)  # type: ignore[arg-type]

        assert len(encoded) == _row_size(5, depth) * 3
        parsed = numpy_io._parse_array(encoded, depth, 5)  # type: ignore[arg-type]
        np.testing.assert_allclose(parsed, 1.0)

    @pytest.mark.parametrize("depth", [16, 32])
    def test_palette_indices_are_refused_below_their_own_depth(
        self, depth: int
    ) -> None:
        """Converting a "P" band through its palette would discard the indices."""
        band = Image.new("P", (4, 4)).getchannel(0)

        with pytest.raises(ValueError, match="palette indices"):
            encode_channel(band, depth)  # type: ignore[arg-type]

    def test_palette_indices_pass_through_at_depth_8(self) -> None:
        image = Image.fromarray(COLORS, "RGB").convert("P")
        band = image.getchannel(0)

        assert encode_channel(band, 8) == band.tobytes()


def test_a_palette_image_carrying_transparency_info_is_not_indexed_for_alpha() -> None:
    """``has_transparency_data`` is true of a "P" image with no "A" band.

    Looking up ``getbands().index("A")`` on one raises ``ValueError``; the
    transparency is carried as a mask instead, as it is for any other image
    whose alpha the document's mode cannot hold.
    """
    image = Image.fromarray(COLORS, "RGB").convert("RGBA")
    image.putalpha(Image.fromarray(MASK, "L"))
    palettized = image.convert("P", palette=Image.Palette.ADAPTIVE)
    palettized.info["transparency"] = 0
    assert palettized.has_transparency_data
    assert "A" not in palettized.getbands()

    psd = PSDImage.new("RGB", (16, 16))
    layer = psd.create_pixel_layer(palettized, name="L")

    assert next(info.id for info in layer._record.channel_info) == (
        ChannelID.TRANSPARENCY_MASK
    )
    array = layer.numpy()
    assert array is not None
    np.testing.assert_allclose(array[:, :, 3], 1.0)


@pytest.mark.parametrize(
    ("source_file", "dest_file"),
    [
        ("layers/pixel-layer.psd", "16bit5x5.psd"),
        ("16bit5x5.psd", "layers/pixel-layer.psd"),
    ],
)
def test_a_move_between_documents_that_differ_only_in_alpha_is_exact(
    source_file: str, dest_file: str
) -> None:
    """The documents' merged-image alpha is not the layer's packing (#872)."""
    source = PSDImage.open(full_name(source_file))
    destination = PSDImage.open(full_name(dest_file))
    assert source.color_mode == destination.color_mode
    assert source.pil_mode != destination.pil_mode
    layer = next(layer for layer in source.descendants() if layer.kind == "pixel")
    before = layer.numpy()
    channels = len(layer._channels)
    assert before is not None

    destination.append(layer)

    after = layer.numpy()
    assert after is not None
    assert len(layer._channels) == channels
    # Narrowing to 8 bits rounds to the nearest of 255 steps.
    np.testing.assert_allclose(after, before, atol=0.5 / 255 + 1e-6)


def test_narrowing_a_32bit_layer_still_tone_maps() -> None:
    """32-bit to 8-bit stays on the render route, which tone-maps like Photoshop."""
    source = PSDImage.open(full_name("32bit5x5.psd"))
    destination = PSDImage.open(full_name("layers/pixel-layer.psd"))
    assert source.pil_mode != destination.pil_mode
    layer = next(layer for layer in source.descendants() if layer.kind == "pixel")
    image = layer.topil()
    assert image is not None
    expected = np.asarray(image.convert(destination.pil_mode), np.float32) / 255

    destination.append(layer)

    array = layer.numpy()
    assert array is not None
    np.testing.assert_allclose(array, expected[:, :, : array.shape[2]], atol=1e-6)


@pytest.mark.parametrize("name", ["TEXT", "Color Fill 1", "Polygon 1"])
@pytest.mark.parametrize(
    "mode, depth, count", [("CMYK", 8, 4), ("L", 8, 1), ("RGB", 16, 3)]
)
def test_a_non_pixel_layer_move_re_encodes_its_channels(
    name: str, mode: str, depth: Literal[8, 16], count: int
) -> None:
    source = PSDImage.open(full_name("adjustment-fillers.psd"))
    layer = next(layer for layer in source.descendants() if layer.name == name)
    had_pixels = layer.has_pixels()
    opacity, blend, tags = layer.opacity, layer.blend_mode, len(layer.tagged_blocks)

    dest = PSDImage.new(mode, (source.width, source.height), depth=depth)
    dest.append(layer)

    ids = [info.id for info in layer._record.channel_info]
    assert [i for i in ids if i >= 0] == list(range(count))
    assert (layer.opacity, layer.blend_mode) == (opacity, blend)
    assert len(layer.tagged_blocks) == tags
    assert layer.has_pixels() == had_pixels
    if had_pixels:
        array = layer.numpy("color")
        assert array is not None
        assert array.shape[2] == count


def test_a_text_layer_keeps_its_pixels_across_a_depth_move() -> None:
    source = PSDImage.open(full_name("adjustment-fillers.psd"))
    layer = next(layer for layer in source.descendants() if layer.name == "TEXT")
    before = layer.numpy("color")
    assert before is not None

    PSDImage.new("RGB", (source.width, source.height), depth=16).append(layer)

    after = layer.numpy("color")
    assert after is not None
    np.testing.assert_allclose(after, before, atol=1e-6)


def test_a_group_mask_survives_a_depth_move() -> None:
    source = PSDImage.open(full_name("masks3.psd"))
    group = next(layer for layer in source.descendants() if layer.name == "Group 1")
    assert group.mask is not None
    before = group.mask.topil()
    assert before is not None

    dest = PSDImage.new("RGB", (source.width, source.height), depth=16)
    dest.append(group)
    dest.save(io.BytesIO())

    assert group.mask is not None
    after = group.mask.topil()
    assert after is not None
    np.testing.assert_array_equal(np.asarray(after), np.asarray(before))


@pytest.mark.parametrize("method", ["append", "extend", "insert"])
@pytest.mark.parametrize("mode", ["L", "CMYK"])
def test_a_failed_cross_document_move_changes_neither_document(
    method: str, mode: str
) -> None:
    source = PSDImage.open(full_name("descriptors/lab-color-swatches.psd"))
    pixel = next(layer for layer in source if layer.kind == "pixel")
    group = source.create_group([pixel], name="group")
    empty = source.create_group(name="empty")
    tops = list(source)
    dest = PSDImage.new(mode, source.size)
    kept = [info.id for info in empty._record.channel_info]

    with pytest.raises(ValueError, match="LAB"):
        if method == "insert":
            dest.insert(0, group)
        elif method == "append":
            dest.append(group)
        else:
            dest.extend([empty, group])

    assert len(dest) == 0
    assert list(source) == tops
    assert list(group) == [pixel]
    assert (pixel.parent, group.parent, empty.parent) == (group, source, source)
    assert pixel._psd is group._psd is empty._psd is source
    assert [info.id for info in empty._record.channel_info] == kept
