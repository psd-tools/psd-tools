"""``Layer.copy_to()``: cross-document transfer is a copy (#999)."""

import io
from copy import deepcopy

import numpy as np
import pytest
from PIL import Image

from psd_tools.api.layers import Group, PixelLayer
from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import Resource, Tag

from ..utils import full_name

COLORS = np.arange(3 * 5 * 3, dtype=np.uint8).reshape(3, 5, 3) * 5 + 3


def _source() -> tuple[PSDImage, PixelLayer]:
    psd = PSDImage.new("RGB", (16, 16))
    layer = psd.create_pixel_layer(Image.fromarray(COLORS, "RGB"), name="L")
    return psd, layer


def _ids(psd: PSDImage) -> list[int]:
    return [
        layer._record.tagged_blocks.get_data(Tag.LAYER_ID)
        for layer in psd.descendants()
    ]


def test_copy_leaves_the_source_and_its_document_intact() -> None:
    source, layer = _source()
    before = layer.numpy()
    record, channels = deepcopy(layer._record), deepcopy(layer._channels)
    ids = _ids(source)
    dest = PSDImage.new("RGB", (16, 16))

    copy = layer.copy_to(dest)

    assert copy is not layer
    assert list(dest) == [copy]
    assert list(source) == [layer]
    assert layer.parent is source and layer._psd is source
    assert layer._record.channel_info == record.channel_info
    assert [c.data for c in layer._channels] == [c.data for c in channels]
    assert _ids(source) == ids
    assert copy._psd is dest and copy.parent is dest
    np.testing.assert_array_equal(copy.numpy(), before)
    np.testing.assert_array_equal(layer.numpy(), before)


def test_copy_issues_ids_unused_in_the_destination() -> None:
    _, layer = _source()
    dest = PSDImage.open(full_name("layers/pixel-layer.psd"))
    used = set(_ids(dest))
    assert used and None not in used

    copy = layer.copy_to(dest)

    assert copy.layer_id not in used
    assert len(set(_ids(dest))) == len(used) + 1
    seed = dest.image_resources.get_data(Resource.IDS_SEED_NUMBER)
    assert seed >= copy.layer_id
    dest.save(io.BytesIO())


def test_copy_into_the_same_document_is_a_duplicate() -> None:
    psd, layer = _source()
    group = psd.create_group(name="G")

    copy = layer.copy_to(group)

    assert list(group) == [copy]
    assert layer.parent is psd
    assert copy.layer_id != layer.layer_id


def test_copy_of_a_group_copies_descendants() -> None:
    source, layer = _source()
    group = source.create_group([layer], name="G")
    dest = PSDImage.new("RGB", (16, 16))

    copy = group.copy_to(dest)

    assert isinstance(copy, Group)
    assert [child.name for child in copy] == ["L"]
    assert copy[0] is not layer
    assert copy[0]._psd is dest and copy[0].parent is copy
    assert copy.layer_id != copy[0].layer_id
    assert list(source) == [group] and list(group) == [layer]
    np.testing.assert_array_equal(copy[0].numpy(), layer.numpy())


def test_copy_converts_the_copy_only() -> None:
    _, layer = _source()
    before = layer.numpy()
    channels = [info.id for info in layer._record.channel_info]
    dest = PSDImage.new("CMYK", (16, 16), depth=16)

    copy = layer.copy_to(dest)

    array = copy.numpy()
    assert array is not None and array.shape[2] == 5
    assert [info.id for info in layer._record.channel_info] == channels
    np.testing.assert_array_equal(layer.numpy(), before)
    dest.save(io.BytesIO())


def test_copy_narrowing_32bit_tone_maps_like_topil() -> None:
    source = PSDImage.open(full_name("32bit5x5.psd"))
    layer = next(layer for layer in source.descendants() if layer.kind == "pixel")
    image = layer.topil()
    assert image is not None
    dest = PSDImage.open(full_name("layers/pixel-layer.psd"))
    expected = np.asarray(image.convert(dest.pil_mode), np.float32) / 255
    stored = layer.numpy()

    copy = layer.copy_to(dest)

    array = copy.numpy()
    assert array is not None
    np.testing.assert_allclose(array, expected[:, :, : array.shape[2]], atol=1e-6)
    np.testing.assert_array_equal(layer.numpy(), stored)


def test_copy_narrowing_32bit_tone_maps_when_the_pil_modes_match() -> None:
    source = PSDImage.open(full_name("32bit5x5.psd"))
    layer = next(layer for layer in source.descendants() if layer.kind == "pixel")
    dest = PSDImage.new("RGB", (5, 5))
    assert source.pil_mode == dest.pil_mode
    image = layer.topil()
    assert image is not None

    result = layer.copy_to(dest).topil()

    assert result is not None
    np.testing.assert_array_equal(
        np.asarray(result.convert(dest.pil_mode)),
        np.asarray(image.convert(dest.pil_mode)),
    )


def test_chained_copy_keeps_every_document_independent() -> None:
    a, layer = _source()
    b = PSDImage.new("RGB", (16, 16), depth=16)
    c = PSDImage.new("RGB", (16, 16))

    in_b = layer.copy_to(b)
    in_c = in_b.copy_to(c)

    assert len({id(layer), id(in_b), id(in_c)}) == 3
    assert [len(d) for d in (a, b, c)] == [1, 1, 1]
    expected, actual = layer.numpy(), in_c.numpy()
    assert expected is not None and actual is not None
    np.testing.assert_allclose(actual, expected, atol=0.5 / 255 + 1e-6)
    for doc in (a, b, c):
        doc.save(io.BytesIO())


@pytest.mark.parametrize(
    ("index", "expected"),
    [(None, "top"), (0, "bottom"), (-1, "top"), (1, "middle")],
)
def test_copy_position(index: int | None, expected: str) -> None:
    _, layer = _source()
    dest = PSDImage.new("RGB", (16, 16))
    for name in ("x", "y"):
        dest.create_pixel_layer(Image.new("RGB", (2, 2)), name=name)

    copy = layer.copy_to(dest, index=index)

    position = {"bottom": 0, "middle": 1, "top": 2}[expected]
    assert dest[position] is copy


def test_copy_rejects_bad_arguments_before_changing_anything() -> None:
    _, layer = _source()
    dest = PSDImage.new("RGB", (16, 16))
    removed = dest.create_group(name="removed")
    dest.remove(removed)

    with pytest.raises(TypeError):
        layer.copy_to(object())  # type: ignore[arg-type]
    with pytest.raises(IndexError):
        layer.copy_to(dest, index=2)
    with pytest.raises(ValueError, match="removed"):
        layer.copy_to(removed)
    assert len(dest) == 0


def test_copy_of_an_artboard_only_goes_to_the_root() -> None:
    source = PSDImage.open(full_name("artboard.psd"))
    artboard = next(layer for layer in source if layer.kind == "artboard")
    dest = PSDImage.new("RGB", (16, 16))
    group = dest.create_group(name="G")

    with pytest.raises(ValueError, match="artboard"):
        artboard.copy_to(group)
    assert len(group) == 0
    assert artboard.copy_to(dest).parent is dest


def test_failed_conversion_leaves_the_destination_untouched() -> None:
    source = PSDImage.open(full_name("descriptors/lab-color-swatches.psd"))
    pixel = next(layer for layer in source if layer.kind == "pixel")
    dest = PSDImage.new("CMYK", source.size)
    seed = dest.image_resources.get_data(Resource.IDS_SEED_NUMBER)

    with pytest.raises(ValueError, match="LAB"):
        pixel.copy_to(dest)

    assert len(dest) == 0
    assert dest.image_resources.get_data(Resource.IDS_SEED_NUMBER) == seed


@pytest.mark.parametrize("name", ["0layers.psd", "0layers_tblocks.psd", "history.psd"])
def test_copy_into_a_document_without_layers_survives_a_save(name: str) -> None:
    _, layer = _source()
    dest = PSDImage.open(full_name(name))
    assert len(list(dest.descendants())) == 0

    copy = layer.copy_to(dest)

    buffer = io.BytesIO()
    dest.save(buffer)
    buffer.seek(0)
    (reopened,) = PSDImage.open(buffer).descendants()
    assert (reopened.name, reopened.bbox) == (copy.name, copy.bbox)
    np.testing.assert_array_equal(reopened.numpy(), copy.numpy())
    assert reopened.layer_id == copy.layer_id


@pytest.mark.parametrize(
    "name",
    [
        "colormodes/4x4_1bit_bitmap.psd",
        "colormodes/4x4_8bit_index_color.psd",
        "colormodes/4x4_16bit_multichannel.psd",
    ],
)
def test_copy_into_a_mode_without_layers_is_rejected(name: str) -> None:
    _, layer = _source()
    dest = PSDImage.open(full_name(name))

    with pytest.raises(ValueError, match="cannot hold layers"):
        layer.copy_to(dest)

    assert len(dest) == 0
