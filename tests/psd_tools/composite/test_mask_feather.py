import numpy as np
import pytest

from psd_tools import PSDImage
from psd_tools.composite import feather

from ..utils import full_name

pytest.importorskip("scipy")

# Each fixture is a yellow layer over an opaque cyan background, behind a hard
# 200x150 mask whose feather Photoshop rendered into the file's own preview.
# Over cyan the red channel is the mask's coverage.
CANVAS = (0, 0, 400, 300)
MASK_BOX = (100, 75, 300, 225)
# Eight-bit rounding between Photoshop's blur passes.
PREVIEW_TOLERANCE = 4

FIXTURES = [
    "mask-feather-4",
    "mask-feather-21",
    "mask-feather-48",
    "mask-feather-21-density-50",
    "mask-feather-vector-21",
    "mask-feather-fill-21",
    "mask-feather-fill-selection-21",
]


def _render(name: str, force: bool) -> np.ndarray:
    psd = PSDImage.open(full_name(f"masks/{name}.psd"))
    return np.asarray(
        psd.composite(force=force, ignore_preview=True).convert("RGB"), dtype=float
    )


def _preview(name: str) -> np.ndarray:
    psd = PSDImage.open(full_name(f"masks/{name}.psd"))
    preview = psd.topil()
    assert preview is not None
    return np.asarray(preview.convert("RGB"), dtype=float)


@pytest.mark.parametrize("force", [False, True])
@pytest.mark.parametrize("name", FIXTURES)
def test_feathered_mask_matches_photoshop_preview(name: str, force: bool) -> None:
    np.testing.assert_allclose(
        _render(name, force), _preview(name), atol=PREVIEW_TOLERANCE, rtol=0
    )


@pytest.mark.parametrize(
    "name",
    [
        "mask-feather-vector-21",
        "mask-feather-fill-21",
        "mask-feather-fill-selection-21",
    ],
)
def test_every_mask_kind_renders_the_same_feather(name: str) -> None:
    np.testing.assert_allclose(
        _render(name, True), _render("mask-feather-21", True), atol=1, rtol=0
    )


def test_density_is_applied_after_the_blur() -> None:
    soft = _render("mask-feather-21", True)[:, :, 0] / 255.0
    dense = _render("mask-feather-21-density-50", True)[:, :, 0] / 255.0
    np.testing.assert_allclose(dense, 0.5 + 0.5 * soft, atol=2 / 255.0, rtol=0)


def test_feather_bleeds_past_the_stored_mask_box() -> None:
    red = _render("mask-feather-21", True)[:, :, 0]
    left, top, _, _ = MASK_BOX
    assert red[150, left - 10] > 0.05 * 255
    assert red[top - 10, 200] > 0.05 * 255


def test_mask_made_from_a_vector_and_a_user_mask_keeps_its_hard_edge() -> None:
    # The stored channel is the two together, so neither feather can be told
    # from it, so the layer keeps the hard stored edge.
    red = _render("mask-feather-user-21-vector-10", True)[:, :, 0]
    assert not ((red > 3) & (red < 252)).any()


@pytest.mark.parametrize("value", [None, 0.0, -3.0, float("nan"), float("inf")])
def test_feather_radius_ignores_what_cannot_blur(value: float | None) -> None:
    assert feather.feather_radius(value) == 0.0


def test_feather_radius_is_bounded() -> None:
    assert feather.feather_radius(1e9) == feather.MAX_FEATHER
    assert feather.feather_radius(21.0) == 21.0


@pytest.mark.parametrize("radius", [0.5, 1.0, 4.5, 21.0])
def test_blur_conserves_mass_and_has_the_feather_as_its_deviation(
    radius: float,
) -> None:
    size = 8 * int(np.ceil(radius)) + 1
    box = (0, 0, size, size)
    centre = size // 2
    impulse = np.zeros((1, 1, 1), dtype=np.float32)
    impulse[0, 0, 0] = 1.0
    blurred = feather.blurred_coverage(
        box, (centre, centre, centre + 1, centre + 1), impulse, 0.0, radius
    )[:, :, 0]
    assert blurred.sum() == pytest.approx(1.0, abs=1e-4)
    np.testing.assert_allclose(blurred, blurred[::-1, ::-1], atol=1e-7)
    offsets = np.arange(size) - centre
    variance = (blurred.sum(axis=0) * offsets**2).sum()
    assert np.sqrt(variance) == pytest.approx(radius, rel=1e-3)


def test_blur_does_not_depend_on_the_viewport() -> None:
    values = np.ones((150, 200, 1), dtype=np.float32)
    whole = feather.blurred_coverage(CANVAS, MASK_BOX, values, 0.0, 21.0)
    for viewport in ((120, 90, 260, 200), (0, 0, 60, 60), (90, 70, 110, 80)):
        part = feather.blurred_coverage(viewport, MASK_BOX, values, 0.0, 21.0)
        left, top, right, bottom = viewport
        np.testing.assert_array_equal(part, whole[top:bottom, left:right])


def test_blur_of_a_background_filled_mask_is_unchanged() -> None:
    values = np.ones((10, 10, 1), dtype=np.float32)
    result = feather.blurred_coverage(CANVAS, (5, 5, 15, 15), values, 1.0, 21.0)
    np.testing.assert_array_equal(result, np.ones_like(result))


def test_blur_continues_the_edge_of_its_domain() -> None:
    # A mask the size of the canvas is not blurred toward its background where
    # the canvas ends.
    values = np.zeros((300, 400, 1), dtype=np.float32)
    values[:, :200] = 1.0
    result = feather.blurred_coverage(CANVAS, CANVAS, values, 1.0, 21.0, domain=CANVAS)
    assert result[150, 0, 0] == pytest.approx(1.0, abs=1e-6)
    assert result[150, 399, 0] == pytest.approx(0.0, abs=1e-6)


def test_blur_asks_to_allocate_before_it_does() -> None:
    def refuse(columns: int, rows: int) -> None:
        raise ValueError(f"{columns}x{rows}")

    values = np.ones((150, 200, 1), dtype=np.float32)
    with pytest.raises(ValueError, match="460x360"):
        feather.blurred_coverage(CANVAS, MASK_BOX, values, 0.0, 10.0, check=refuse)


@pytest.mark.parametrize("viewport", [(300, 100, 400, 200), (100, 0, 300, 75)])
def test_viewport_beside_a_feathered_fill_still_shows_its_bleed(
    viewport: tuple[int, int, int, int],
) -> None:
    psd = PSDImage.open(full_name("masks/mask-feather-fill-selection-21.psd"))
    whole = np.asarray(
        psd.composite(force=True, ignore_preview=True).convert("RGB"), dtype=float
    )
    part = np.asarray(
        psd.composite(viewport=viewport, force=True, ignore_preview=True).convert(
            "RGB"
        ),
        dtype=float,
    )
    left, top, right, bottom = viewport
    np.testing.assert_allclose(part, whole[top:bottom, left:right], atol=1, rtol=0)
