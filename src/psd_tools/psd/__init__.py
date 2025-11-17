"""
Low-level API that translates binary data to Python structure.

All the data structure in this subpackage inherits from one of the object
defined in :py:mod:`psd_tools.psd.base` module.
"""

# Main PSD document class
from .document import PSD as PSD

# Layer and mask structures
from .layer_and_mask import (
    ChannelImageData as ChannelImageData,
    GlobalLayerMaskInfo as GlobalLayerMaskInfo,
    LayerInfo as LayerInfo,
    LayerRecords as LayerRecords,
    TaggedBlocks as TaggedBlocks,
)

__all__ = [
    "PSD",
    "LayerInfo",
    "LayerRecords",
    "ChannelImageData",
    "TaggedBlocks",
    "GlobalLayerMaskInfo",
]
