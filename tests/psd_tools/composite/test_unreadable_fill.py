"""A fill descriptor the compositor cannot read costs that layer, not the document."""

import io
from collections.abc import Callable

import numpy as np
import pytest

from psd_tools import PSDImage
from psd_tools.composite import paint
from psd_tools.constants import Tag
from psd_tools.psd.descriptor import Descriptor, UnitFloat
from psd_tools.terminology import Key, Unit

from ..utils import full_name

pytest.importorskip("scipy")

Mutation = Callable[[Descriptor], None]


def _unknown_color_class(desc: Descriptor) -> None:
    desc[Key.Color].classID = b"XXXX"


def _missing_color_component(desc: Descriptor) -> None:
    del desc[Key.Color][Key.Green]


def _missing_gradient_type(desc: Descriptor) -> None:
    del desc[Key.Type]


def _missing_gradient_form(desc: Descriptor) -> None:
    del desc[Key.Gradient][b"GrdF"]


def _reopened(psd: PSDImage) -> PSDImage:
    buf = io.BytesIO()
    psd.save(buf)
    buf.seek(0)
    return PSDImage.open(buf)


def _forged(layer_name: str, tag: Tag, mutate: Mutation) -> PSDImage:
    psd = PSDImage.open(full_name("adjustment-fillers.psd"))
    layer = next(x for x in psd.descendants() if x.name == layer_name)
    assert not layer.has_pixels()
    mutate(layer._record.tagged_blocks.get_data(tag))
    return _reopened(psd)


FORGED = [
    ("Color Fill 1", Tag.SOLID_COLOR_SHEET_SETTING, _unknown_color_class),
    ("Color Fill 1", Tag.SOLID_COLOR_SHEET_SETTING, _missing_color_component),
    ("Polygon 2", Tag.GRADIENT_FILL_SETTING, _missing_gradient_type),
    ("Polygon 2", Tag.GRADIENT_FILL_SETTING, _missing_gradient_form),
]


@pytest.mark.parametrize(("layer_name", "tag", "mutate"), FORGED)
@pytest.mark.parametrize("force", [False, True])
def test_a_layer_whose_fill_is_unreadable_draws_nothing(
    layer_name: str, tag: Tag, mutate: Mutation, force: bool
) -> None:
    psd = _forged(layer_name, tag, mutate)
    layer = next(x for x in psd.descendants() if x.name == layer_name)
    drawn = layer.composite(force=force)
    assert drawn is not None
    alpha = np.asarray(drawn.getchannel("A"))
    # A layer's own stroke is drawn from the path and survives; the fill's
    # interior is what is lost.
    assert alpha[alpha.shape[0] // 2, alpha.shape[1] // 2] == 0
    assert psd.composite(ignore_preview=True, force=force) is not None


def test_a_stroke_whose_fill_is_unreadable_raises_only_value_error() -> None:
    psd = PSDImage.open(full_name("stroke.psd"))
    layer = next(x for x in psd if x.name == "Shape 1")
    assert layer.stroke is not None
    del layer.stroke._data[b"strokeStyleContent"][Key.Type]
    forged = _reopened(psd)
    with pytest.raises(ValueError):
        forged.composite(ignore_preview=True, force=True)


def test_a_stroke_color_missing_a_component_raises_only_value_error() -> None:
    psd = PSDImage.open(full_name("stroke.psd"))
    layer = next(x for x in psd if x.name == "Rectangle 1")
    assert layer.stroke is not None
    del layer.stroke._data[b"strokeStyleContent"][Key.Color][Key.Green]
    forged = _reopened(psd)
    with pytest.raises(ValueError):
        forged.composite(ignore_preview=True, force=True)


def test_paint_raises_value_error_on_an_unknown_color_class() -> None:
    psd = PSDImage.open(full_name("adjustment-fillers.psd"))
    layer = next(x for x in psd.descendants() if x.name == "Color Fill 1")
    desc = layer._record.tagged_blocks.get_data(Tag.SOLID_COLOR_SHEET_SETTING)
    _unknown_color_class(desc)
    with pytest.raises(ValueError):
        paint.draw_solid_color_fill(layer.bbox, psd.color_mode, desc)


@pytest.mark.parametrize("mutate", [_missing_gradient_type, _missing_gradient_form])
def test_paint_raises_value_error_on_a_gradient_missing_an_enum(
    mutate: Mutation,
) -> None:
    psd = PSDImage.open(full_name("adjustment-fillers.psd"))
    layer = next(x for x in psd.descendants() if x.name == "Polygon 2")
    desc = layer._record.tagged_blocks.get_data(Tag.GRADIENT_FILL_SETTING)
    mutate(desc)
    with pytest.raises(ValueError):
        paint.draw_gradient_fill(layer.bbox, psd.color_mode, desc)


@pytest.mark.parametrize("force", [False, True])
def test_a_fill_layer_over_the_budget_still_raises(force: bool) -> None:
    psd = PSDImage.open(full_name("layers-minimal/pattern-fill.psd"))
    layer = next(
        x
        for x in psd.descendants()
        if x.tagged_blocks.get_data(Tag.PATTERN_FILL_SETTING) is not None
    )
    desc = layer.tagged_blocks.get_data(Tag.PATTERN_FILL_SETTING)
    desc[Key.Scale] = UnitFloat(unit=Unit.Percent, value=1e7)
    forged = _reopened(psd)
    forged_layer = next(x for x in forged.descendants() if x.name == layer.name)
    with pytest.raises(ValueError, match="over the"):
        forged_layer.composite(force=force)


def test_a_stroke_gradient_scaled_to_zero_raises_only_value_error() -> None:
    psd = PSDImage.open(full_name("stroke.psd"))
    layer = next(x for x in psd if x.name == "Shape 1")
    assert layer.stroke is not None
    layer.stroke._data[b"strokeStyleContent"][Key.Scale].value = 0.0
    forged = _reopened(psd)
    with pytest.raises(ValueError):
        forged.composite(ignore_preview=True, force=True)
