"""A document with unbalanced group dividers or a partial artboard rect opens."""

import io
from typing import Any

import pytest

from psd_tools import PSDImage
from psd_tools.api.layers import Artboard, Group, PixelLayer
from psd_tools.constants import SectionDivider, Tag
from psd_tools.psd import PSD

from ..utils import full_name


def _forge_unbalanced(kind: SectionDivider) -> bytes:
    """Turn the first divider of ``kind`` into an ordinary layer's divider."""
    psd = PSD.read(open(full_name("blend-modes/group-divider-blend-mode.psd"), "rb"))
    for record, _ in psd._iter_layers():
        for key in (Tag.SECTION_DIVIDER_SETTING, Tag.NESTED_SECTION_DIVIDER_SETTING):
            divider = record.tagged_blocks.get_data(key)
            if divider is not None and divider.kind == kind:
                divider.kind = SectionDivider.OTHER
                out = io.BytesIO()
                psd.write(out)
                return out.getvalue()
    raise AssertionError("divider not found")


@pytest.mark.parametrize(
    "kind", [SectionDivider.OPEN_FOLDER, SectionDivider.BOUNDING_SECTION_DIVIDER]
)
def test_an_unbalanced_group_divider_reads_as_a_plain_layer(
    kind: SectionDivider,
) -> None:
    psd = PSDImage.open(io.BytesIO(_forge_unbalanced(kind)))
    layers = list(psd.descendants())
    assert layers
    assert not any(isinstance(layer, Group) for layer in layers)
    assert all(isinstance(layer, PixelLayer) for layer in layers)
    for layer in layers:
        layer.name
        layer.bbox

    out = io.BytesIO()
    psd.save(out)
    reopened = PSDImage.open(io.BytesIO(out.getvalue()))
    assert [x.name for x in reopened.descendants()] == [x.name for x in layers]


def _drop_rect(data: Any) -> None:
    del data[b"artboardRect"]


def _drop_side(data: Any) -> None:
    del data[b"artboardRect"][b"Left"]


def _infinite_side(data: Any) -> None:
    data[b"artboardRect"][b"Left"] = float("inf")


def _text_side(data: Any) -> None:
    data[b"artboardRect"][b"Left"] = "x"


@pytest.mark.parametrize("damage", [_drop_rect, _drop_side, _infinite_side, _text_side])
def test_a_malformed_artboard_rect_raises_value_error(damage: Any) -> None:
    psd = PSDImage.open(full_name("artboard-bgcolor.psd"))
    artboard = next(x for x in psd.descendants() if isinstance(x, Artboard))
    for key in (Tag.ARTBOARD_DATA1, Tag.ARTBOARD_DATA2, Tag.ARTBOARD_DATA3):
        data = artboard._record.tagged_blocks.get_data(key)
        if data is not None:
            damage(data)
    artboard._bbox = None
    with pytest.raises(ValueError):
        artboard.bbox
