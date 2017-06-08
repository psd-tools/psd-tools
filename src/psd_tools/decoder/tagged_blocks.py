# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, print_function
import warnings
import collections
import io

from psd_tools.constants import TaggedBlock, SectionDivider, PathResource
from psd_tools.decoder.actions import decode_descriptor, UnknownOSType
from psd_tools.utils import read_fmt, unpack
from psd_tools.decoder import decoders, layer_effects
from psd_tools.reader.layers import Block
from psd_tools.debug import pretty_namedtuple
from psd_tools.decoder import engine_data

_tagged_block_decoders, register = decoders.new_registry()

_tagged_block_decoders.update({
    TaggedBlock.BLEND_CLIPPING_ELEMENTS:            decoders.boolean("I"),
    TaggedBlock.BLEND_INTERIOR_ELEMENTS:            decoders.boolean("I"),
    TaggedBlock.BLEND_FILL_OPACITY:                 decoders.single_value("4B"),
    TaggedBlock.KNOCKOUT_SETTING:                   decoders.boolean("I"),
    TaggedBlock.UNICODE_LAYER_NAME:                 decoders.unicode_string,
    TaggedBlock.LAYER_ID:                           decoders.single_value("I"), # XXX: there are more fields in docs, but they seem to be incorrect
    TaggedBlock.EFFECTS_LAYER:                      layer_effects.decode,
    TaggedBlock.OBJECT_BASED_EFFECTS_LAYER_INFO:    layer_effects.decode_object_based,
    TaggedBlock.OBJECT_BASED_EFFECTS_LAYER_INFO_V0: layer_effects.decode_object_based,
    TaggedBlock.OBJECT_BASED_EFFECTS_LAYER_INFO_V1: layer_effects.decode_object_based
})


SolidColorSettings = pretty_namedtuple('SolidColorSettings', 'version data')
BrightnessContrast = pretty_namedtuple('BrightnessContrast',
                                       'brightness contrast mean lab')
LevelsSettings = pretty_namedtuple('LevelsSettings', 'version data')
LevelRecord = pretty_namedtuple('LevelRecord', 'input_floor input_ceiling '
    'output_floor output_ceiling gamma')
CurvesSettings = pretty_namedtuple(
    'CurvesSettings', 'version count data extra')
CurvesExtraMarker = pretty_namedtuple(
    'CurvesExtraMarker', 'tag version count data')
CurveData = pretty_namedtuple('CurveData', 'channel points')
Exposure = pretty_namedtuple('Exposure', 'version exposure offset gamma')
Vibrance = pretty_namedtuple('Vibrance', 'descriptor_version descriptor')
HueSaturation = pretty_namedtuple(
    'HueSaturation', 'version enable_colorization colorization master items')
HueSaturationData = pretty_namedtuple('HueSaturationData', 'range settings')
ExportData = pretty_namedtuple('ExportData', 'version data')
MetadataItem = pretty_namedtuple('MetadataItem', 'key copy_on_sheet_duplication descriptor_version data')
ProtectedSetting = pretty_namedtuple('ProtectedSetting', 'transparency, composite, position')
TypeToolObjectSetting = pretty_namedtuple('TypeToolObjectSetting',
                        'version xx xy yx yy tx ty text_version descriptor1_version text_data '
                        'warp_version descriptor2_version warp_data left top right bottom')
VectorOriginationData = pretty_namedtuple('VectorOriginationData', 'version descriptor_version data')
VectorMaskSetting = pretty_namedtuple(
    'VectorMaskSetting','version invert not_link disable path')


class Divider(collections.namedtuple('Divider', 'block type key')):
    def __repr__(self):
        return "Divider(%s %r %s, %s)" % (
            self.block, self.type, SectionDivider.name_of(self.type), self.key)


def decode(tagged_blocks, version):
    """
    Replaces "data" attribute of a blocks from ``tagged_blocks`` list
    with parsed data structure if it is known how to parse it.
    """
    return [parse_tagged_block(block, version) for block in tagged_blocks]


def parse_tagged_block(block, version=1, **kwargs):
    """
    Replaces "data" attribute of a block with parsed data structure
    if it is known how to parse it.
    """
    if not TaggedBlock.is_known(block.key):
        warnings.warn("Unknown tagged block (%s)" % block.key)

    decoder = _tagged_block_decoders.get(block.key, lambda data, **kwargs: data)
    return Block(block.key, decoder(block.data, version=version))


def _decode_descriptor_block(data, kls):
    if isinstance(data, bytes):
        fp = io.BytesIO(data)
    version = read_fmt("I", fp)[0]

    try:
        return kls(version, decode_descriptor(None, fp))
    except UnknownOSType as e:
        warnings.warn("Ignoring tagged block %s" % e)
        return data


@register(TaggedBlock.SOLID_COLOR_SHEET_SETTING)
def _decode_soco(data, **kwargs):
    fp = io.BytesIO(data)
    version = read_fmt("I", fp)[0]
    try:
        data = decode_descriptor(None, fp)
        return SolidColorSettings(version, data)
    except UnknownOSType as e:
        warnings.warn("Ignoring solid color tagged block (%s)" % e)
        return data


@register(TaggedBlock.BRIGHTNESS_AND_CONTRAST)
def _decode_brightness_and_contrast(data, **kwargs):
    return BrightnessContrast(*read_fmt("3H B", io.BytesIO(data)))


@register(TaggedBlock.LEVELS)
def _decode_levels(data, **kwargs):
    fp = io.BytesIO(data)
    version = read_fmt("H", fp)[0]
    level_records = []
    for i in range(29):
        input_f, input_c, output_f, output_c, gamma = read_fmt("5H", fp)
        level_records.append(LevelRecord(
            input_f, input_c, output_f, output_c, gamma / 100.0))
    return LevelsSettings(version, level_records)


@register(TaggedBlock.CURVES)
def _decode_curves(data, **kwargs):
    fp = io.BytesIO(data)
    padding, version, count = read_fmt("B H I", fp)  # Documentation wrong.
    if version not in (1, 4):
        warnings.warn("Invalid curves version {}".format(version))
        return data
    if version == 1:
        count = bin(count).count('1')  # Bitmap = channel index?

    items = []
    for i in range(count):
        point_count = read_fmt("H", fp)[0]
        points = [read_fmt("2H", fp) for c in range(point_count)]
        items.append(CurveData(None, points))
    extra = None
    if version == 1:
        tag, version_, count_ = read_fmt("4s H I", fp)
        extra_items = []
        for i in range(count_):
            channel_index, point_count = read_fmt("2H", fp)
            points = [read_fmt("2H", fp) for c in range(point_count)]
            extra_items.append(CurveData(channel_index, points))
        extra = CurvesExtraMarker(tag, version_, count_, extra_items)
    return CurvesSettings(version, count, items, extra)


@register(TaggedBlock.EXPOSURE)
def _decode_exposure(data, **kwargs):
    return Exposure(*read_fmt("H 3f", io.BytesIO(data)))


@register(TaggedBlock.VIBRANCE)
def _decode_vibrance(data, **kwargs):
    return _decode_descriptor_block(data, Vibrance)


@register(TaggedBlock.HUE_SATURATION_4)
@register(TaggedBlock.HUE_SATURATION_5)
def _decode_hue_saturation(data, **kwargs):
    fp = io.BytesIO(data)
    version, enable_colorization, _ = read_fmt('H 2B', fp)
    if version != 2:
        warnings.warn("Invalid Hue/saturation version {}".format(version))
        return data
    colorization = read_fmt('3h', fp)
    master = read_fmt('3h', fp)
    items = []
    for i in range(6):
        range_values = read_fmt('4h', fp)
        settings_values = read_fmt('3h', fp)
        items.append(HueSaturationData(range_values, settings_values))
    return HueSaturation(version, enable_colorization, colorization, master,
                         items)


@register(TaggedBlock.EXPORT_DATA)
def _decode_extd(data, **kwargs):
    fp = io.BytesIO(data)
    version = read_fmt("I", fp)[0]
    try:
        data = decode_descriptor(None, fp)
        return ExportData(version, data)
    except UnknownOSType as e:
        warnings.warn("Ignoring extd tagged block (%s)" % e)
        return data


@register(TaggedBlock.REFERENCE_POINT)
def _decode_reference_point(data, **kwargs):
    return read_fmt("2d", io.BytesIO(data))


@register(TaggedBlock.SHEET_COLOR_SETTING)
def _decode_color_setting(data, **kwargs):
    return read_fmt("4H", io.BytesIO(data))


@register(TaggedBlock.SECTION_DIVIDER_SETTING)
def _decode_section_divider(data, **kwargs):
    tp, key = _decode_divider(data)
    return Divider(TaggedBlock.SECTION_DIVIDER_SETTING, tp, key)


@register(TaggedBlock.NESTED_SECTION_DIVIDER_SETTING)
def _decode_section_divider(data, **kwargs):
    tp, key = _decode_divider(data)
    return Divider(TaggedBlock.NESTED_SECTION_DIVIDER_SETTING, tp, key)


def _decode_divider(data):
    fp = io.BytesIO(data)
    key = None
    tp = read_fmt("I", fp)[0]
    if not SectionDivider.is_known(tp):
        warnings.warn("Unknown section divider type (%s)" % tp)

    if len(data) == 12:
        sig = fp.read(4)
        if sig != b'8BIM':
            warnings.warn("Invalid signature in section divider block")
        key = fp.read(4)

    return tp, key

@register(TaggedBlock.PLACED_LAYER_DATA)
@register(TaggedBlock.SMART_OBJECT_PLACED_LAYER_DATA)
def _decode_placed_layer(data, **kwargs):
    fp = io.BytesIO(data)
    type, version, descriptorVersion = read_fmt("4s I I", fp)
    descriptor = decode_descriptor(None, fp)
    return descriptor.items

@register(TaggedBlock.METADATA_SETTING)
def _decode_metadata(data, **kwargs):
    fp = io.BytesIO(data)
    items_count = read_fmt("I", fp)[0]
    items = []

    for x in range(items_count):
        sig = fp.read(4)
        if sig != b'8BIM':
            warnings.warn("Invalid signature in metadata item (%s)" % sig)

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
def _decode_protected(data, **kwargs):
    flag = unpack("I", data)[0]
    return ProtectedSetting(
        bool(flag & 1),
        bool(flag & 2),
        bool(flag & 4),
    )


@register(TaggedBlock.LAYER_32)
def _decode_layer32(data, version=1, **kwargs):
    from psd_tools.reader import layers
    from psd_tools.decoder.decoder import decode_layers
    fp = io.BytesIO(data)
    layers = layers._read_layers(fp, 'latin1', 32, length=len(data), version=version)
    return decode_layers(layers, version)


@register(TaggedBlock.LAYER_16)
def _decode_layer16(data, version=1, **kwargs):
    from psd_tools.reader import layers
    from psd_tools.decoder.decoder import decode_layers
    fp = io.BytesIO(data)
    layers = layers._read_layers(fp, 'latin1', 16, length=len(data), version=version)
    return decode_layers(layers, version)


@register(TaggedBlock.TYPE_TOOL_OBJECT_SETTING)
def _decode_type_tool_object_setting(data, **kwargs):
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

    # Decode EngineData here.
    for index in range(len(text_data.items)):
        item = text_data.items[index]
        if item[0] == b'EngineData':
            text_data.items[index] = (b'EngineData', engine_data.decode(item[1].value))

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


@register(TaggedBlock.TEXT_ENGINE_DATA)
def _decode_text_engine_data(data, **kwargs):
    return engine_data.decode(data)


@register(TaggedBlock.VECTOR_ORIGINATION_DATA)
def _decode_vector_origination_data(data, **kwargs):
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


@register(TaggedBlock.VECTOR_MASK_SETTING1)
@register(TaggedBlock.VECTOR_MASK_SETTING2)
def _decode_vector_mask_setting1(data, **kwargs):
    fp = io.BytesIO(data)
    ver, flags = read_fmt("II", fp)

    # This decoder needs to be updated if we have new formats.
    if ver != 3:
        warnings.warn("Ignoring vector mask setting1 tagged block due to "
                      "unsupported version %s" % (ver))
        return data

    # Path points are 8 bits + 24 bits fixed points. Convert to float here.
    def _decode_fixed_point(fixed_point):
        return tuple(x / 0x01000000 for x in fixed_point)

    path = []
    path_rec = (len(data) - 8) // 26
    while path_rec > 0:
        selector, = read_fmt("H", fp)
        record = {"selector": selector}
        if selector in (PathResource.CLOSED_SUBPATH_LENGTH_RECORD,
                PathResource.OPEN_SUBPATH_LENGTH_RECORD):
            record["num_knot_records"], = read_fmt("H", fp)
            fp.seek(22, io.SEEK_CUR)
        elif selector in (
                PathResource.CLOSED_SUBPATH_BEZIER_KNOT_LINKED,
                PathResource.CLOSED_SUBPATH_BEZIER_KNOT_UNLINKED,
                PathResource.OPEN_SUBPATH_BEZIER_KNOT_LINKED,
                PathResource.OPEN_SUBPATH_BEZIER_KNOT_UNLINKED):
            record["control_preceding_knot"] = _decode_fixed_point(
                read_fmt("2i", fp))
            record["anchor"] = _decode_fixed_point(read_fmt("2i", fp))
            record["control_leaving_knot"] = _decode_fixed_point(
                read_fmt("2i", fp))
        elif selector == PathResource.PATH_FILL_RULE_RECORD:
            fp.seek(24, io.SEEK_CUR)
        elif selector == PathResource.CLIPBOARD_RECORD:
            record["top"], record["left"], record["bottom"], record["right"],
            record["resolution"] = _decode_fixed_point(read_fmt("5i", fp))
            fp.seek(4, io.SEEK_CUR)
        elif selector == PathResource.INITIAL_FILL_RULE_RECORD:
            record["initial_fill_rule"], = read_fmt("H", fp)
            fp.seek(22, io.SEEK_CUR)
        else:
            warnings.warn("Unknown path record found %s" % (selector))
        path.append(record)
        path_rec -= 1

    return VectorMaskSetting(
        ver, (0x01 & flags) > 0, (0x02 & flags) > 0, (0x04 & flags) > 0, path)


@register(TaggedBlock.LINKED_LAYER1)
@register(TaggedBlock.LINKED_LAYER2)
@register(TaggedBlock.LINKED_LAYER3)
@register(TaggedBlock.LINKED_LAYER_EXTERNAL)
def _decode_linked_layer(data, **kwargs):
    from psd_tools.decoder.linked_layer import decode
    return decode(data)


@register(TaggedBlock.CHANNEL_BLENDING_RESTRICTIONS_SETTING)
def _decode_channel_blending_restrictions_setting(data, **kwargs):
    # Data contains color channels to restrict.
    restrictions = [False, False, False]
    fp = io.BytesIO(data)
    while fp.tell() < len(data):
        channel = read_fmt("I", fp)[0]
        restrictions[channel] = True
    return restrictions
