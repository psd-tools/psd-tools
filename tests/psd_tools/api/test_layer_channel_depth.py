"""What a layer's channels are packed as when the API writes them (#867).

Every write path that builds channel data from a PIL image used to take the
depth from the image. A PIL image holds a byte per pixel whatever it describes,
so a 16- or 32-bit document got channels a half or a quarter of the length its
geometry requires, and the layer read back empty -- the sibling defect to #866,
in the layer path rather than the merged image data one.

The same rule reaches three places: ``PixelLayer.frompil()`` and everything
that calls it, ``create_mask()``/``update_mask()`` -- a mask is stored at the
document's depth too, which 24 16-bit and two 32-bit masks in the corpus show
-- and ``_convert_mode()``, which re-encodes a layer moved between documents
and consulted neither the destination's depth nor its file version.

A note on what these assert. ``len(ChannelData.data)`` is the *compressed*
length, so the length tests build their layers with ``Compression.RAW``, where
it is the channel length; under RLE the reader pads every short row back out to
the full row size, which makes a length assertion pass on the unfixed code.
For the same reason the value tests compare whole arrays and use a non-uniform
image at least three pixels wide: an 8-bit row read as 16-bit pairs its own
bytes, so ``0x80, 0x80`` decodes to 0.50196 -- exactly the right answer -- and
the first pixel or two of a flat layer come out correct on the unfixed code.
"""

from typing import Any, Literal

import numpy as np
import pytest
from PIL import Image

import psd_tools.api.numpy_io as numpy_io
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
    empty composites as the backdrop alone -- which is what depth 16 and 32
    did.
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
    """Equal colour mode is not equal packing, which the old guard assumed.

    Both documents are RGB, so ``pil_mode`` matches and the layer used to be
    carried across untouched -- at the source's bytes per sample.
    """
    source = PSDImage.new("RGB", (16, 16), depth=source_depth)
    layer = source.create_pixel_layer(_image(), name="L")
    layer.create_mask(Image.fromarray(MASK, "L"))

    PSDImage.new("RGB", (16, 16), depth=dest_depth).append(layer)

    array = layer.numpy()
    assert array is not None
    np.testing.assert_allclose(array[:, :, :3], COLORS / 255.0, atol=1e-6)
    mask_array = numpy_io.get_layer_data(layer, "mask")
    assert mask_array is not None
    np.testing.assert_allclose(mask_array[:, :, 0], MASK / 255.0, atol=1e-6)
    assert _channel_lengths(layer) == _channel_lengths(layer)  # no empty channel
    assert all(len(channel.data) > 0 for channel in layer._channels)


def test_a_version_only_move_re_encodes_the_channels() -> None:
    """PSD to PSB. An RLE channel's row-length words are two bytes or four."""
    source = PSDImage.new("RGB", (16, 16), depth=8)
    layer = source.create_pixel_layer(_image(), name="L")
    layer.create_mask(Image.fromarray(MASK, "L"))

    destination = PSDImage.open(full_name("2layers.psb"))
    assert destination.version == 2 and source.version == 1
    destination.append(layer)

    array = layer.numpy()
    assert array is not None
    np.testing.assert_allclose(array[:, :, :3], COLORS / 255.0, atol=1e-6)
    mask_array = numpy_io.get_layer_data(layer, "mask")
    assert mask_array is not None
    np.testing.assert_allclose(mask_array[:, :, 0], MASK / 255.0, atol=1e-6)


def test_a_depth_only_move_keeps_the_layer_record() -> None:
    """A guard, not evidence for #867: this passes on the unfixed code too.

    It passed there because the move did nothing at all. It is asserted so
    that re-encoding a depth-only move can never be done by routing it through
    the ``pil_mode`` branch, which rebuilds the record from scratch and drops
    all of this.
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


def test_a_cross_mode_move_still_rebuilds_the_record() -> None:
    """A tripwire for a known defect, not a guarantee anyone wants.

    The ``pil_mode`` branch replaces the layer record, so a move between
    documents of different colour modes loses the layer's opacity, blend mode
    and mask. #867 deliberately does not widen the set of moves that take that
    branch; this pins the behaviour so the fix for it has to come here.
    """
    source = PSDImage.new("RGB", (16, 16), depth=8)
    layer = source.create_pixel_layer(_image(), name="L")
    layer.create_mask(Image.fromarray(MASK, "L"))
    layer.opacity = 77
    layer.blend_mode = BlendMode.MULTIPLY

    PSDImage.new("CMYK", (16, 16), depth=8).append(layer)

    assert layer.opacity == 255
    assert layer.blend_mode == BlendMode.NORMAL
    assert not layer.has_mask()


def test_a_cross_mode_move_into_a_deep_document_uses_that_depth() -> None:
    """The two halves of the rule at once: PIL converts, the header packs."""
    source = PSDImage.new("RGB", (16, 16), depth=8)
    layer = source.create_pixel_layer(_image(), name="L")

    PSDImage.new("CMYK", (16, 16), depth=16).append(layer)

    expected = _row_size(layer.width, 16) * layer.height
    for info, channel in zip(layer._record.channel_info, layer._channels):
        assert len(channel.get_data(layer.width, layer.height, 16)) == expected, info.id
    array = layer.numpy()
    assert array is not None
    assert array.shape[2] == 5  # CMYK plus transparency
    assert float(array[:, :, :4].max()) > 0.0


class TestBitmapDocuments:
    r"""Depth 1, where the encoding's *sense* is under test, not just its length.

    A set bit is black, so a fully opaque transparency channel is a run of
    zeros. No fixture has a depth-1 layer or mask channel and Photoshop does
    not author layers in bitmap mode, so there is no ground truth here. What
    these assert is that the write is the reader's own inverse, which is more
    than the old code managed -- it wrote a 16-byte ``b"\xff"`` transparency
    for a 4x4 layer, four times too long and, read as bits, fully
    *transparent*.
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

    def test_a_bitmap_band_is_not_stored_as_packed_bits_at_depth_8(self) -> None:
        """``PSDImage.new("1", ...)`` builds a BITMAP header at depth *8*.

        Whether that header is right is a separate question. What must hold
        either way is that the channel matches the depth the header declares:
        a "1" band's ``tobytes()`` is bit-packed, which is a byte per pixel
        only by accident and never for a row of more than eight.
        """
        psd = PSDImage.new("1", (20, 3))
        assert psd.color_mode == ColorMode.BITMAP and psd.depth == 8
        layer = psd.create_pixel_layer(
            Image.new("1", (20, 3), 1), name="L", compression=Compression.RAW
        )

        assert _channel_lengths(layer) == [_row_size(20, 8) * 3] * 2


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

    Looking up ``getbands().index("A")`` on one raised ``ValueError``; the
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

    assert [info.id for info in layer._record.channel_info][0] == (
        ChannelID.TRANSPARENCY_MASK
    )
    array = layer.numpy()
    assert array is not None
    np.testing.assert_allclose(array[:, :, 3], 1.0)
