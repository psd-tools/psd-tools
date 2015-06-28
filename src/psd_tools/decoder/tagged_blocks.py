# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, print_function
import warnings
import io

from psd_tools.constants import TaggedBlock, SectionDivider, BlendMode, SectionDividerSub
from psd_tools.decoder.actions import decode_descriptor, UnknownOSType
from psd_tools.utils import read_fmt, unpack
from psd_tools.decoder import decoders, layer_effects, linked_layer
from psd_tools.reader.layers import Block
from psd_tools.debug import pretty_namedtuple
from psd_tools.exceptions import Error

_tagged_block_decoders, register = decoders.new_registry()

_tagged_block_decoders.update({
    TaggedBlock.BLEND_CLIPPING_ELEMENTS:            decoders.boolean,
    TaggedBlock.BLEND_INTERIOR_ELEMENTS:            decoders.boolean,
    TaggedBlock.KNOCKOUT_SETTING:                   decoders.boolean,
    TaggedBlock.UNICODE_LAYER_NAME:                 decoders.unicode_string,
    TaggedBlock.LAYER_ID:                           decoders.single_value("I"),
    TaggedBlock.FILL_OPACITY:                       decoders.single_value("B"),
    TaggedBlock.EFFECTS_LAYER:                      layer_effects.decode,
    TaggedBlock.OBJECT_BASED_EFFECTS_LAYER_INFO:    layer_effects.decode_object_based,
    TaggedBlock.LINKED_LAYER1:                      linked_layer.decode,
    TaggedBlock.LINKED_LAYER2:                      linked_layer.decode,
    TaggedBlock.LINKED_LAYER3:                      linked_layer.decode
})


SolidColorSettings = pretty_namedtuple('SolidColorSettings', 'version data')
MetadataItem = pretty_namedtuple('MetadataItem', 'key copy_on_sheet_duplication descriptor_version data')
ProtectedSetting = pretty_namedtuple('ProtectedSetting', 'transparency, composite, position')
TypeToolObjectSetting = pretty_namedtuple('TypeToolObjectSetting',
                        'version xx xy yx yy tx ty text_version descriptor1_version text_data '
                        'warp_version descriptor2_version warp_data left top right bottom')
VectorOriginationData = pretty_namedtuple('VectorOriginationData', 'version descriptor_version data')


class Divider(pretty_namedtuple('Divider', 'type blend_mode sub_type')):

    def __repr__(self):
        blend_mode = self.blend_mode
        if blend_mode is not None:
            blend_mode = BlendMode.name_of(blend_mode)

        sub_type = self.sub_type
        if sub_type is not None:
            sub_type = SectionDividerSub.name_of(sub_type)

        return "Divider(type=%s, blend_mode=%s, sub_type=%s)" % (
            SectionDivider.name_of(self.type),
            blend_mode, sub_type
        )

    def _repr_pretty_(self, p, cycle):
        if cycle:
            p.text(repr(self))
        else:
            blend_mode = self.blend_mode
            if blend_mode is not None:
                blend_mode = BlendMode.name_of(blend_mode)

            sub_type = self.sub_type
            if sub_type is not None:
                sub_type = SectionDividerSub.name_of(sub_type)

            p.begin_group(2, 'Divider(')
            p.begin_group(0)

            p.break_()
            p.text("type = %s," % SectionDivider.name_of(self.type))
            p.break_()
            p.text("blend_mode = %s," % blend_mode)
            p.break_()
            p.text("sub_type = %s" % sub_type)

            p.end_group(2)
            p.break_()
            p.end_group(0, ')')


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
    if not TaggedBlock.is_known(block.key):
        warnings.warn("Unknown tagged block (%s)" % block.key)

    decoder = _tagged_block_decoders.get(block.key, lambda data: data)
    return Block(block.key, decoder(block.data))


@register(TaggedBlock.SOLID_COLOR_SHEET_SETTING)
def _decode_soco(data):
    fp = io.BytesIO(data)
    version = read_fmt("I", fp)[0]
    try:
        data = decode_descriptor(None, fp)
        return SolidColorSettings(version, data)
    except UnknownOSType as e:
        warnings.warn("Ignoring solid color tagged block (%s)" % e)
        return data


@register(TaggedBlock.REFERENCE_POINT)
def _decode_reference_point(data):
    return read_fmt("2d", io.BytesIO(data))


@register(TaggedBlock.SHEET_COLOR_SETTING)
def _decode_color_setting(data):
    return read_fmt("4H", io.BytesIO(data))


@register(TaggedBlock.SECTION_DIVIDER_SETTING)
@register(TaggedBlock.NESTED_SECTION_DIVIDER_SETTING)
def _decode_section_divider(data):
    data_length = len(data)
    blend_mode = None
    sub_type = None

    fp = io.BytesIO(data)
    tp = read_fmt("I", fp)[0]
    if not SectionDivider.is_known(tp):
        warnings.warn("Unknown section divider type (%s)" % tp)

    if data_length >= 12:
        sig = fp.read(4)
        if sig != b'8BIM':
            raise Error("Invalid signature in section divider block (%r)" % sig)

        blend_mode = fp.read(4)
        if not BlendMode.is_known(blend_mode):
            warnings.warn("Unknown section divider blend mode (%s)" % blend_mode)

        if data_length >= 16:
            sub_type = read_fmt("I", fp)[0]
            if not SectionDividerSub.is_known(sub_type):
                warnings.warn("Unknown section divider sub-type (%s)" % sub_type)

    return Divider(tp, blend_mode, sub_type)


@register(TaggedBlock.PLACED_LAYER_DATA)
@register(TaggedBlock.SMART_OBJECT_PLACED_LAYER_DATA)
def _decode_placed_layer(data):
    fp = io.BytesIO(data)
    type, version, descriptorVersion = read_fmt("4s I I", fp)
    descriptor = decode_descriptor(None, fp)
    return descriptor.items


@register(TaggedBlock.METADATA_SETTING)
def _decode_metadata(data):
    fp = io.BytesIO(data)
    items_count = read_fmt("I", fp)[0]
    items = []

    for x in range(items_count):
        sig = fp.read(4)
        if sig != b'8BIM':
            raise Error("Invalid signature in metadata item (%r)" % sig)

        key, copy_on_sheet, data_length = read_fmt("4s ? 3x I", fp)

        data = fp.read(data_length)
        if data_length < 4+12:
            # descr_version is 4 bytes, descriptor is at least 12 bytes,
            # so data can't be a descriptor.
            descr_ver = None
        else:
            # try load data as a descriptor
            fp2 = io.BytesIO(data)
            descr_ver = read_fmt("I", fp2)[0]
            try:
                data = decode_descriptor(None, fp2)
            except UnknownOSType as e:
                # FIXME: can it fail with other exceptions?
                descr_ver = None
                warnings.warn("Can't decode metadata item (%s)" % e)

        items.append(MetadataItem(key, copy_on_sheet, descr_ver, data))

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
    ver, xx, xy, yx, yy, tx, ty, txt_ver, descr1_ver = read_fmt("H 6d H I", fp)

    # This decoder needs to be updated if we have new formats.
    if ver != 1 or txt_ver != 50 or descr1_ver != 16:
        warnings.warn("Ignoring type setting tagged block due to old versions")
        return data

    try:
        text_data = decode_descriptor(None, fp)
    except UnknownOSType as e:
        warnings.warn("Ignoring type setting tagged block (%s)" % e)
        return data

    warp_ver, descr2_ver = read_fmt("H I", fp)
    if warp_ver != 1 or descr2_ver != 16:
        warnings.warn("Ignoring type setting tagged block due to old versions")
        return data

    try:
        warp_data = decode_descriptor(None, fp)
    except UnknownOSType as e:
        warnings.warn("Ignoring type setting tagged block (%s)" % e)
        return data

    left, top, right, bottom = read_fmt("4i", fp)   # wrong info in specs...
    return TypeToolObjectSetting(
        ver, xx, xy, yx, yy, tx, ty, txt_ver, descr1_ver, text_data,
        warp_ver, descr2_ver, warp_data, left, top, right, bottom
    )


@register(TaggedBlock.VECTOR_ORIGINATION_DATA)
def _decode_vector_origination_data(data):
    fp = io.BytesIO(data)
    ver, descr_ver = read_fmt("II", fp)

    # This decoder needs to be updated if we have new formats.
    if ver != 1 and descr_ver != 16:
        warnings.warn("Ignoring vector origination tagged block due to unsupported versions %s %s" % (ver, descr_ver))
        return data

    try:
        vector_origination_data = decode_descriptor(None, fp)
    except UnknownOSType as e:
        warnings.warn("Ignoring vector origination tagged block (%s)" % e)
        return data

    return VectorOriginationData(ver, descr_ver, vector_origination_data)
