# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, print_function
import warnings
import collections
import io

from psd_tools.constants import TaggedBlock, SectionDivider
from psd_tools.decoder.actions import decode_descriptor, UnknownOSType
from psd_tools.utils import read_fmt, read_unicode_string, unpack, debug_view
from psd_tools.decoder import decoders
from psd_tools.reader.layers import Block

_tagged_block_decoders, register = decoders.new_registry()

_tagged_block_decoders.update({
    TaggedBlock.BLEND_CLIPPING_ELEMENTS:    decoders.boolean("I"),
    TaggedBlock.BLEND_INTERIOR_ELEMENTS:    decoders.boolean("I"),
    TaggedBlock.KNOCKOUT_SETTING:           decoders.boolean("I"),
    TaggedBlock.UNICODE_LAYER_NAME:         decoders.unicode_string,
    TaggedBlock.LAYER_ID:                   decoders.single_value("I") # XXX: there are more fields in docs, but they seem to be incorrect
})


SolidColorSettings = collections.namedtuple('SolidColorSettings', 'version data')
MetadataItem = collections.namedtuple('MetadataItem', 'sig key copy_on_sheet_duplication data')
ProtectedSetting = collections.namedtuple('ProtectedSetting', 'transparency, composite, position')
TypeToolObjectSetting = collections.namedtuple('TypeToolObjectSetting',
                        'version xx xy yx yy tx ty text_version descriptor_version1 text_data')
                        #'warp_version descriptor_version2 warp_data'
                        #'left top right bottom')


class Divider(collections.namedtuple('Divider', 'type key')):
    def __repr__(self):
        return "Divider(%r %s, %s)" % (self.type, SectionDivider.name_of(self.type), self.key)

def decode(tagged_blocks):
    """
    Replaces "data" attribute of a blocks from ``tagged_blocks`` list
    with parsed data structure if it is known how to parse it.
    """
    return [parse_tagged_block(block) for block in tagged_blocks]

def parse_tagged_block(block):
    """
    Replaces "data" attribute of a block with parsed data structure
    if it is known how to parse it.
    """
    key = block.key.decode('ascii')
    if not TaggedBlock.is_known(key):
        warnings.warn("Unknown tagged block (%s)" % block.key)

    decoder = _tagged_block_decoders.get(key, lambda data: data)
    return Block(key, decoder(block.data))


@register(TaggedBlock.SOLID_COLOR)
def _decode_soco(data):
    fp = io.BytesIO(data)
    version = read_fmt("I", fp)
    try:
        data = decode_descriptor(None, fp)
        return SolidColorSettings(version, data)
    except UnknownOSType as e:
        warnings.warn("Ignoring solid color tagged block (%s)" % e)


@register(TaggedBlock.REFERENCE_POINT)
def _decode_reference_point(data):
    return read_fmt("2d", io.BytesIO(data))

@register(TaggedBlock.SHEET_COLOR_SETTING)
def _decode_color_setting(data):
    return read_fmt("4H", io.BytesIO(data))

@register(TaggedBlock.SECTION_DIVIDER_SETTING)
def _decode_section_divider(data):
    fp = io.BytesIO(data)
    key = None
    tp = read_fmt("I", fp)[0]
    if not SectionDivider.is_known(tp):
        warnings.warn("Unknown section divider type (%s)" % tp)

    if len(data) == 12:
        sig = fp.read(4)
        if sig != b'8BIM':
            warnings.warn("Invalid signature in section divider block")
        key = fp.read(4).decode('ascii')

    return Divider(tp, key)

@register(TaggedBlock.METADATA_SETTING)
def _decode_metadata(data):
    fp = io.BytesIO(data)
    items_count = read_fmt("I", fp)[0]
    items = []
    for x in range(items_count):
        sig, key, copy_on_sheet, data_length = read_fmt("4s 4s ? 3x I", fp)
        data = fp.read(data_length)
        items.append(MetadataItem(sig, key, copy_on_sheet, data))
    return items

@register(TaggedBlock.PROTECTED_SETTING)
def _decode_protected(data):
    flag = unpack("I", data)[0]
    return ProtectedSetting(
        bool(flag & 1),
        bool(flag & 2),
        bool(flag & 4),
    )

@register(TaggedBlock.LAYER_32)
def _decode_layer32(data):
    from psd_tools.reader import layers
    from psd_tools.decoder.decoder import decode_layers
    fp = io.BytesIO(data)
    layers = layers._read_layers(fp, 'latin1', 32, length=len(data))
    return decode_layers(layers)

@register(TaggedBlock.LAYER_16)
def _decode_layer16(data):
    from psd_tools.reader import layers
    from psd_tools.decoder.decoder import decode_layers
    fp = io.BytesIO(data)
    layers = layers._read_layers(fp, 'latin1', 16, length=len(data))
    return decode_layers(layers)

@register(TaggedBlock.TYPE_TOOL_OBJECT_SETTING)
def _decode_type_tool_object_setting(data):
    fp = io.BytesIO(data)
    ver, xx, xy, yx, yy, tx, ty, txt_ver, desc_ver1 = read_fmt("H 6Q H I", fp)

    # This decoder needs to be updated if we have new formats.
    if ver != 1 or txt_ver != 50 or desc_ver1 != 16:
        warnings.warn("Ignoring type setting tagged block due to old versions")
        return

    try:
        text_data = decode_descriptor(None, fp)
    except UnknownOSType as e:
        warnings.warn("Ignoring type setting tagged block (%s)" % e)
        return

    # XXX: Until Engine Data is parsed properly, the following cannot be parsed.
    # The end of the engine data dictates where this starts.
    return TypeToolObjectSetting(ver, xx, xy, yx, yy, tx, ty, txt_ver, desc_ver1, text_data)

    warp_ver, desc_ver2 = read_fmt("H I", fp)
    if warp_ver != 1 or desc_ver2 != 16:
        warnings.warn("Ignoring type setting tagged block due to old versions")
        return

    try:
        warp_data = decode_descriptor(None, fp)
    except UnknownOSType as e:
        warnings.warn("Ignoring type setting tagged block (%s)" % e)
        return

    left, top, right, bottom = read_fmt("4Q", fp)
    return TypeToolObjectSetting(ver, xx, xy, yx, yy, tx, ty, txt_ver, desc_ver1,
                                 text_data, warp_ver, desc_ver2, warp_data,
                                 left, top, right, bottom)
