"""
Utility functions for the API layer.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psd_tools.api.protocols import PSDProtocol

from psd_tools.constants import ColorMode, Resource, Tag

# Mapping of expected number of channels for each color mode.
EXPECTED_CHANNELS = {
    ColorMode.BITMAP: 1,
    ColorMode.GRAYSCALE: 1,
    ColorMode.INDEXED: 3,
    ColorMode.RGB: 3,
    ColorMode.CMYK: 4,
    ColorMode.MULTICHANNEL: 64,
    ColorMode.DUOTONE: 2,
    ColorMode.LAB: 3,
}


def has_transparency(psdimage: "PSDProtocol") -> bool:
    """Check if the PSD image has transparency information.

    Args:
        psdimage: The PSD image protocol object
    Returns:
        True if the image has transparency, False otherwise
    """
    keys = (
        Tag.SAVING_MERGED_TRANSPARENCY,
        Tag.SAVING_MERGED_TRANSPARENCY16,
        Tag.SAVING_MERGED_TRANSPARENCY32,
    )
    if psdimage.tagged_blocks and any(key in psdimage.tagged_blocks for key in keys):
        return True
    expected = EXPECTED_CHANNELS.get(psdimage.color_mode)
    if expected is not None and psdimage.channels > expected:
        alpha_ids = psdimage.image_resources.get_data(Resource.ALPHA_IDENTIFIERS)
        if alpha_ids and all(x > 0 for x in alpha_ids):
            return False
        if (
            psdimage._record.layer_and_mask_information.layer_info is not None
            and psdimage._record.layer_and_mask_information.layer_info.layer_count > 0
        ):
            return False
        return True
    return False


def get_transparency_index(psdimage: "PSDProtocol") -> int:
    """Get the index of the transparency channel in the PSD image.

    Args:
        psdimage: The PSD image protocol object
    Returns:
        The index of the transparency channel, or -1 if not found
    """
    alpha_ids = psdimage.image_resources.get_data(Resource.ALPHA_IDENTIFIERS)
    if alpha_ids:
        try:
            offset = alpha_ids.index(0)
            return psdimage.channels - len(alpha_ids) + offset
        except ValueError:
            pass
    return -1  # Assume the last channel is the transparency
