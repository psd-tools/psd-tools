"""
Deprecated module - use psd_tools.psd.bin_utils or psd_tools.registry instead.

This module has been split into:
- psd_tools.psd.bin_utils: Binary processing utilities
- psd_tools.registry: Registry pattern helper

This module will be removed in a future version.
"""

import warnings

# Re-export all binary utilities from bin_utils
from psd_tools.psd.bin_utils import (
    be_array_from_bytes,
    be_array_to_bytes,
    decode_fixed_point_32bit,
    fix_byteorder,
    is_readable,
    pack,
    pad,
    read_be_array,
    read_fmt,
    read_length_block,
    read_padding,
    read_pascal_string,
    read_unicode_string,
    reserve_position,
    trimmed_repr,
    unpack,
    write_be_array,
    write_bytes,
    write_fmt,
    write_length_block,
    write_padding,
    write_pascal_string,
    write_position,
    write_unicode_string,
)

# Re-export registry pattern from registry module
from psd_tools.registry import new_registry

# Issue deprecation warning
warnings.warn(
    "psd_tools.utils is deprecated and will be removed in a future version. "
    "Use 'psd_tools.psd.bin_utils' for binary utilities "
    "or 'psd_tools.registry' for the registry pattern.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    # Binary utilities
    "be_array_from_bytes",
    "be_array_to_bytes",
    "decode_fixed_point_32bit",
    "fix_byteorder",
    "is_readable",
    "pack",
    "pad",
    "read_be_array",
    "read_fmt",
    "read_length_block",
    "read_padding",
    "read_pascal_string",
    "read_unicode_string",
    "reserve_position",
    "trimmed_repr",
    "unpack",
    "write_be_array",
    "write_bytes",
    "write_fmt",
    "write_length_block",
    "write_padding",
    "write_pascal_string",
    "write_position",
    "write_unicode_string",
    # Registry
    "new_registry",
]
