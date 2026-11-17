from typing import Any

import pytest

from psd_tools.api.layers import Artboard, ArtboardBackground, Group
from psd_tools.api.psd_image import PSDImage
from psd_tools.constants import ColorMode, Tag
from psd_tools.psd.descriptor import Descriptor, Double, Integer, String

from ..utils import full_name


def _set_background_type(artboard: Artboard, value: object) -> None:
    for key in (Tag.ARTBOARD_DATA1, Tag.ARTBOARD_DATA2, Tag.ARTBOARD_DATA3):
        if key in artboard.tagged_blocks:
            artboard.tagged_blocks.get_data(key)[b"artboardBackgroundType"] = value


def test_artboards_lists_top_level_artboards_in_z_order() -> None:
    psd = PSDImage.open(full_name("artboard-bgcolor.psd"))
    assert [a.name for a in psd.artboards] == ["Artboard 1", "Artboard 2"]
    assert all(isinstance(a, Artboard) for a in psd.artboards)
    assert psd.artboards[0] is psd[0]


def test_artboards_is_empty_without_artboards() -> None:
    assert PSDImage.open(full_name("1layer.psd")).artboards == []


def test_artboards_skips_nested_artboards() -> None:
    psd = PSDImage.open(full_name("artboard.psd"))
    group = Group.new(psd, "outer")
    inner = Artboard._move(Group.new(group, "inner"))
    assert inner in group
    assert inner not in psd.artboards
    assert group not in psd.artboards


def test_background_reads_custom_color() -> None:
    artboard = PSDImage.open(full_name("artboard-bgcolor.psd")).artboards[0]
    bg = artboard.background
    assert bg.kind == "custom"
    assert bg.alpha == 1.0
    assert bg.color is not None
    assert bg.color == pytest.approx((18 / 255, 108 / 255, 200 / 255))
    color, alpha = artboard._artboard_background_defaults()
    assert (bg.color, bg.alpha) == (color, alpha)


def test_background_transparent() -> None:
    artboard = PSDImage.open(full_name("artboard.psd")).artboards[0]
    assert artboard.background == ArtboardBackground("transparent", None, 0.0)


@pytest.mark.parametrize(
    ("bg_type", "kind", "color"),
    [(2, "white", (1.0, 1.0, 1.0)), (3, "black", (0.0, 0.0, 0.0))],
)
@pytest.mark.parametrize("mode", [ColorMode.RGB, ColorMode.CMYK, ColorMode.LAB])
def test_background_white_and_black_ignore_color_mode(
    bg_type: int, kind: str, color: tuple[float, ...], mode: ColorMode
) -> None:
    psd = PSDImage.open(full_name("artboard-bgcolor.psd"))
    _set_background_type(psd.artboards[0], Integer(bg_type))
    psd._record.header.color_mode = mode
    assert psd.artboards[0].background == ArtboardBackground(kind, color, 1.0)  # type: ignore[arg-type]


def test_background_custom_color_survives_a_cmyk_document() -> None:
    psd = PSDImage.open(full_name("artboard-bgcolor.psd"))
    expected = psd.artboards[0].background
    psd._record.header.color_mode = ColorMode.CMYK
    assert psd.artboards[0]._artboard_background_defaults() == (1.0, 0.0)
    assert psd.artboards[0].background == expected


@pytest.mark.parametrize(
    "value",
    [Integer(9), Integer(0), None, Double(2.5), Double(3.9), Double(float("nan"))],
)
def test_background_unknown_type_is_transparent(value: object) -> None:
    artboard = PSDImage.open(full_name("artboard-bgcolor.psd")).artboards[0]
    _set_background_type(artboard, value)
    assert artboard.background == ArtboardBackground("transparent", None, 0.0)


def test_background_incomplete_custom_color_is_transparent() -> None:
    artboard = PSDImage.open(full_name("artboard-bgcolor.psd")).artboards[0]
    for key in (Tag.ARTBOARD_DATA1, Tag.ARTBOARD_DATA2, Tag.ARTBOARD_DATA3):
        if key in artboard.tagged_blocks:
            data = artboard.tagged_blocks.get_data(key)
            del data[b"Clr "]
    assert artboard.background == ArtboardBackground("transparent", None, 0.0)


def test_psd_composite_spans_the_whole_canvas() -> None:
    psd = PSDImage.open(full_name("artboard-bgcolor.psd"))
    assert psd.composite().size == psd.size
    image = psd.artboards[0].composite()
    assert image is not None
    assert image.size == (400, 300)


def _clr(artboard: Artboard) -> Any:
    for key in (Tag.ARTBOARD_DATA1, Tag.ARTBOARD_DATA2, Tag.ARTBOARD_DATA3):
        if key in artboard.tagged_blocks:
            return artboard.tagged_blocks.get_data(key)


@pytest.mark.parametrize(
    "red",
    [
        Double(float("nan")),
        Double(float("inf")),
        Integer(300),
        Integer(-1),
        String("q"),
    ],
)
def test_background_unrepresentable_channel_is_transparent(red: object) -> None:
    artboard = PSDImage.open(full_name("artboard-bgcolor.psd")).artboards[0]
    _clr(artboard)[b"Clr "][b"Rd  "] = red
    assert artboard.background == ArtboardBackground("transparent", None, 0.0)


@pytest.mark.parametrize("missing", [b"Rd  ", b"Grn ", b"Bl  "])
def test_background_missing_channel_is_transparent(missing: bytes) -> None:
    artboard = PSDImage.open(full_name("artboard-bgcolor.psd")).artboards[0]
    del _clr(artboard)[b"Clr "][missing]
    assert artboard.background == ArtboardBackground("transparent", None, 0.0)


def test_background_non_descriptor_color_is_transparent() -> None:
    artboard = PSDImage.open(full_name("artboard-bgcolor.psd")).artboards[0]
    _clr(artboard)[b"Clr "] = Integer(1)
    assert not isinstance(_clr(artboard)[b"Clr "], Descriptor)
    assert artboard.background == ArtboardBackground("transparent", None, 0.0)


def test_background_non_numeric_type_is_transparent() -> None:
    artboard = PSDImage.open(full_name("artboard-bgcolor.psd")).artboards[0]
    _set_background_type(artboard, String("x"))
    assert artboard.background == ArtboardBackground("transparent", None, 0.0)
