import pytest

from psd_tools.api.psd_image import PSDImage
from psd_tools.api.utils import EXPECTED_CHANNELS, get_color_channels
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
