import pytest

from psd_tools.api.psd_image import PSDImage
from psd_tools.api.utils import (
    EXPECTED_CHANNELS,
    _validate_color_input,
    color_channels,
    get_color_channels,
)
from psd_tools.constants import ColorMode

from ..utils import full_name


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("colormodes/4x4_1bit_bitmap.psd", 1),
        ("colormodes/4x4_8bit_grayscale.psd", 1),
        ("colormodes/4x4_8bit_rgb.psd", 3),
        ("colormodes/4x4_8bit_rgba.psd", 3),  # the extra channel is alpha
        ("colormodes/4x4_8bit_cmyk.psd", 4),
        ("colormodes/4x4_8bit_lab.psd", 3),
        ("colormodes/4x4_8bit_duotone.psd", 1),  # one stored channel, not two inks
        ("colormodes/4x4_8bit_index_color.psd", 3),  # one channel, palette-expanded
        ("colormodes/4x4_16bit_multichannel.psd", 3),  # whatever the header says
    ],
)
def test_get_color_channels(filename: str, expected: int) -> None:
    psd = PSDImage.open(full_name(filename))
    assert get_color_channels(psd) == expected


def test_get_color_channels_can_differ_from_the_header_either_way() -> None:
    """The header's count is neither an upper nor a lower bound on the canvas.

    This is why ``composite()`` guards its allocation with the wider of the two
    rather than either one alone -- see
    ``test_composite_guard_estimate_covers_a_mode_that_expands`` and
    ``..._takes_the_header_when_it_is_wider``.
    """
    narrower = PSDImage.open(full_name("colormodes/4x4_8bit_index_color.psd"))
    assert narrower.channels == 1 < get_color_channels(narrower) == 3

    wider = PSDImage.open(full_name("colormodes/4x4_8bit_rgba.psd"))
    assert wider.channels == 4 > get_color_channels(wider) == 3


def test_get_color_channels_reads_the_header_only_for_multichannel() -> None:
    """Every other mode's count is fixed by the mode itself.

    Multichannel is the exception because ``EXPECTED_CHANNELS`` reports 64 for
    it -- the format's maximum rather than any file's own count (#720). The
    "only" half of that is carried by the parametrized cases above: the ``rgba``
    row has a header count of 4 and resolves to 3, so a non-multichannel
    document demonstrably ignores its header.
    """
    psd = PSDImage.open(full_name("colormodes/4x4_16bit_multichannel.psd"))
    assert EXPECTED_CHANNELS[ColorMode.MULTICHANNEL] == 64
    assert get_color_channels(psd) == psd.channels == 3

    # A retagged document follows its header rather than the table.
    psd._record.header.channels = 5
    assert get_color_channels(psd) == 5


def test_color_channels_matches_the_document_form() -> None:
    """The header-taking form answers the same question as the document one.

    ``PSDImage.new()`` has to validate a color before a document exists, so the
    rule is reachable from a bare header too (#731).
    """
    for filename in (
        "colormodes/4x4_1bit_bitmap.psd",
        "colormodes/4x4_8bit_rgb.psd",
        "colormodes/4x4_8bit_rgba.psd",
        "colormodes/4x4_8bit_cmyk.psd",
        "colormodes/4x4_8bit_index_color.psd",
        "colormodes/4x4_16bit_multichannel.psd",
    ):
        psd = PSDImage.open(full_name(filename))
        header = psd._record.header
        assert color_channels(header.color_mode, header.channels) == get_color_channels(
            psd
        ), filename


def test_color_channels_tracks_the_header_only_for_multichannel() -> None:
    """A different header count moves the answer for multichannel alone."""
    assert color_channels(ColorMode.MULTICHANNEL, 3) == 3
    assert color_channels(ColorMode.MULTICHANNEL, 7) == 7
    # Every other mode's count is the mode's own, whatever the header says.
    assert color_channels(ColorMode.RGB, 3) == color_channels(ColorMode.RGB, 4) == 3
    assert color_channels(ColorMode.DUOTONE, 1) == 1


def test_validate_color_input_channels_overrides_the_table() -> None:
    """The override is what makes a multichannel sequence expressible.

    Without it the count comes from ``EXPECTED_CHANNELS``, whose multichannel
    entry is 64 -- the format's maximum, not any document's count -- so no
    sequence could satisfy it (#731).
    """
    # The unfixable case the table produces on its own.
    with pytest.raises(ValueError, match="Expected 64 color channel"):
        _validate_color_input((0.1, 0.2, 0.3), 8, ColorMode.MULTICHANNEL)
    # With the real width supplied, the same sequence validates.
    _validate_color_input((0.1, 0.2, 0.3), 8, ColorMode.MULTICHANNEL, 3)
    # And a genuinely wrong width still raises, naming the count it was given.
    with pytest.raises(ValueError, match="Expected 3 color channel"):
        _validate_color_input((0.1, 0.2), 8, ColorMode.MULTICHANNEL, 3)


def test_validate_color_input_leaves_other_modes_alone() -> None:
    """Passing the override changes nothing for a mode the table gets right."""
    _validate_color_input((1.0, 0.5, 0.0), 8, ColorMode.RGB, 3)
    with pytest.raises(ValueError, match="Expected 3 color channel"):
        _validate_color_input((1.0, 0.5), 8, ColorMode.RGB, 3)
    with pytest.raises(ValueError, match="Expected 3 color channel"):
        _validate_color_input((1.0, 0.5), 8, ColorMode.RGB)
