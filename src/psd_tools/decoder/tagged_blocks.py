# -*- coding: utf-8 -*-
"""
Module for decoding tagged blocks.

Tagged blocks are key-value configuration for individual layers or for a
photoshop document. The keys are specified by
:py:class:`~psd_tools.constants.TaggedBlock`.
"""
from __future__ import absolute_import, unicode_literals, print_function
import warnings
import collections
import io

from psd_tools.constants import TaggedBlock, SectionDivider, ColorMode
from psd_tools.decoder.actions import (
    decode_descriptor, UnknownOSType, RawData
)
from psd_tools.utils import (
    read_fmt, unpack, read_unicode_string, read_pascal_string
)
from psd_tools.decoder import decoders, layer_effects
from psd_tools.decoder.color import decode_color
from psd_tools.decoder.path import decode_path_resource
from psd_tools.reader.layers import Block
from psd_tools.debug import pretty_namedtuple
from psd_tools.decoder import engine_data

_tagged_block_decoders, register = decoders.new_registry()

_tagged_block_decoders.update({
    TaggedBlock.BLEND_CLIPPING_ELEMENTS: decoders.boolean("I"),
    TaggedBlock.BLEND_INTERIOR_ELEMENTS: decoders.boolean("I"),
    TaggedBlock.BLEND_FILL_OPACITY: decoders.single_value("4B"),
    TaggedBlock.KNOCKOUT_SETTING: decoders.boolean("I"),
    TaggedBlock.UNICODE_LAYER_NAME: decoders.unicode_string,
    # XXX: there are more fields in docs, but they seem to be incorrect
    TaggedBlock.LAYER_ID: decoders.single_value("I"),
    TaggedBlock.EFFECTS_LAYER: layer_effects.decode,
    TaggedBlock.OBJECT_BASED_EFFECTS_LAYER_INFO:
        layer_effects.decode_object_based,
    TaggedBlock.OBJECT_BASED_EFFECTS_LAYER_INFO_V0:
        layer_effects.decode_object_based,
    TaggedBlock.OBJECT_BASED_EFFECTS_LAYER_INFO_V1:
        layer_effects.decode_object_based,
    TaggedBlock.USING_ALIGNED_RENDERING: decoders.boolean("I"),
    TaggedBlock.LAYER_VERSION: decoders.single_value("I"),
    TaggedBlock.TRANSPARENCY_SHAPES_LAYER: decoders.single_value("4B"),
    TaggedBlock.LAYER_MASK_AS_GLOBAL_MASK: decoders.single_value("4B"),
    TaggedBlock.VECTOR_MASK_AS_GLOBAL_MASK: decoders.single_value("4B"),
})


class SolidColorSetting(pretty_namedtuple(
    'SolidColorSetting',
    'version data'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: data
    """


class PatternFillSetting(pretty_namedtuple(
    'PatternFillSetting',
    'version data'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: data
    """


class GradientFillSetting(pretty_namedtuple(
    'GradientFillSetting',
    'version data'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: data
    """


class BrightnessContrast(pretty_namedtuple(
    'BrightnessContrast',
    'brightness contrast mean lab'
)):
    """
    .. py:attribute:: brightness
    .. py:attribute:: contrast
    .. py:attribute:: mean
    .. py:attribute:: lab
    """


class LevelsSettings(pretty_namedtuple('LevelsSettings', 'version data')):
    """
    .. py:attribute:: version
    .. py:attribute:: data
    """


class LevelRecord(pretty_namedtuple(
    'LevelRecord',
    'input_floor input_ceiling output_floor output_ceiling gamma'
)):
    """
    .. py:attribute:: input_floor
    .. py:attribute:: input_ceiling
    .. py:attribute:: output_floor
    .. py:attribute:: output_ceiling
    .. py:attribute:: gamma
    """


class CurvesSettings(pretty_namedtuple(
    'CurvesSettings',
    'version count data extra'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: count
    .. py:attribute:: data
    .. py:attribute:: extra
    """


class CurvesExtraMarker(pretty_namedtuple(
    'CurvesExtraMarker',
    'tag version count data'
)):
    """
    .. py:attribute:: tag
    .. py:attribute:: version
    .. py:attribute:: count
    .. py:attribute:: data
    """


class CurveData(pretty_namedtuple('CurveData', 'channel points')):
    """
    .. py:attribute:: channel
    .. py:attribute:: points
    """


class Exposure(pretty_namedtuple(
    'Exposure',
    'version exposure offset gamma'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: exposure
    .. py:attribute:: offset
    .. py:attribute:: gamma
    """


class Vibrance(pretty_namedtuple(
    'Vibrance',
    'descriptor_version descriptor'
)):
    """
    .. py:attribute:: descriptor_version
    .. py:attribute:: descriptor
    """


class HueSaturation(pretty_namedtuple(
    'HueSaturation',
    'version enable_colorization colorization master items'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: enable_colorization
    .. py:attribute:: colorization
    .. py:attribute:: master
    .. py:attribute:: items
    """


class HueSaturationData(pretty_namedtuple(
    'HueSaturationData',
    'range settings'
)):
    """
    .. py:attribute:: range
    .. py:attribute:: settings
    """


class ColorBalance(pretty_namedtuple(
    'ColorBalance',
    'shadows midtones highlights preserve_luminosity'
)):
    """
    .. py:attribute:: shadows
    .. py:attribute:: midtones
    .. py:attribute:: highlights
    .. py:attribute:: preserve_luminosity
    """


class BlackWhite(pretty_namedtuple(
    'BlackWhite',
    'descriptor_version descriptor'
)):
    """
    .. py:attribute:: descriptor_version
    .. py:attribute:: descriptor
    """


class PhotoFilter(pretty_namedtuple(
    'PhotoFilter',
    'version xyz color_space color_components density preserve_luminosity'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: xyz
    .. py:attribute:: color_space
    .. py:attribute:: color_components
    .. py:attribute:: density
    .. py:attribute:: preserve_luminosity
    """


class ChannelMixer(pretty_namedtuple(
    'ChannelMixer',
    'version monochrome mixer_settings'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: monochrome
    .. py:attribute:: mixer_settings
    """


class ColorLookup(pretty_namedtuple(
    'ColorLookup',
    'version descriptor_version descriptor'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: descriptor_version
    .. py:attribute:: descriptor
    """


class Invert(pretty_namedtuple('Invert', '')):
    """
    """


class Posterize(pretty_namedtuple('Posterize', 'value')):
    """
    .. py:attribute:: value
    """


class Threshold(pretty_namedtuple('Threshold', 'value')):
    """
    .. py:attribute:: value
    """


class SelectiveColor(pretty_namedtuple(
    'SelectiveColor',
    'version method items'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: method
    .. py:attribute:: items
    """


class Pattern(pretty_namedtuple(
    'Pattern',
    'version image_mode point name pattern_id color_table data'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: image_mode
    .. py:attribute:: point
    .. py:attribute:: name
    .. py:attribute:: pattern_id
    .. py:attribute:: color_table data
    """


class VirtualMemoryArrayList(pretty_namedtuple(
    'VirtualMemoryArrayList',
    'version rectangle channels'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: rectangle
    .. py:attribute:: channels
    """


class VirtualMemoryArray(pretty_namedtuple(
    'VirtualMemoryArray',
    'is_written depth rectangle pixel_depth compression data'
)):
    """
    .. py:attribute:: is_written
    .. py:attribute:: depth
    .. py:attribute:: rectangle
    .. py:attribute:: pixel_depth
    .. py:attribute:: compression data
    """


class GradientSettings(pretty_namedtuple(
    'GradientSettings',
    'version reversed dithered name color_stops transparency_stops expansion '
    'interpolation length mode random_seed show_transparency '
    'use_vector_color roughness color_model min_color max_color'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: reversed
    .. py:attribute:: dithered
    .. py:attribute:: name
    .. py:attribute:: color_stops
    .. py:attribute:: transparency_stops
    .. py:attribute:: expansion
    .. py:attribute:: interpolation
    .. py:attribute:: length
    .. py:attribute:: mode
    .. py:attribute:: random_seed
    .. py:attribute:: show_transparency
    .. py:attribute:: use_vector_color
    .. py:attribute:: roughness
    .. py:attribute:: color_model
    .. py:attribute:: min_color
    .. py:attribute:: max_color
    """


class ColorStop(pretty_namedtuple(
    'ColorStop',
    'location midpoint mode color'
)):
    """
    .. py:attribute:: location
    .. py:attribute:: midpoint
    .. py:attribute:: mode
    .. py:attribute:: color
    """


class TransparencyStop(pretty_namedtuple(
    'TransparencyStop',
    'location midpoint opacity expansion interpolation length mode'
)):
    """
    .. py:attribute:: location
    .. py:attribute:: midpoint
    .. py:attribute:: opacity
    .. py:attribute:: expansion
    .. py:attribute:: interpolation
    .. py:attribute:: length
    .. py:attribute:: mode
    """


class ExportSetting(pretty_namedtuple('ExportSetting', 'version data')):
    """
    .. py:attribute:: version
    .. py:attribute:: data
    """


class VectorStrokeSetting(pretty_namedtuple(
    'VectorStrokeSetting',
    'version data'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: data
    """


class VectorStrokeContentSetting(pretty_namedtuple(
    'VectorStrokeContentSetting',
    'key version data'
)):
    """
    .. py:attribute:: key
    .. py:attribute:: version
    .. py:attribute:: data
    """


class MetadataItem(pretty_namedtuple(
    'MetadataItem',
    'key copy_on_sheet_duplication descriptor_version data'
)):
    """
    .. py:attribute:: key
    .. py:attribute:: copy_on_sheet_duplication
    .. py:attribute:: descriptor_version
    .. py:attribute:: data
    """


class ProtectedSetting(pretty_namedtuple(
    'ProtectedSetting',
    'transparency composite position'
)):
    """
    .. py:attribute:: transparency
    .. py:attribute:: composite
    .. py:attribute:: position
    """


class TypeToolObjectSetting(pretty_namedtuple(
    'TypeToolObjectSetting',
    'version xx xy yx yy tx ty text_version descriptor1_version text_data '
    'warp_version descriptor2_version warp_data left top right bottom'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: xx
    .. py:attribute:: xy
    .. py:attribute:: yx
    .. py:attribute:: yy
    .. py:attribute:: tx
    .. py:attribute:: ty
    .. py:attribute:: text_version
    .. py:attribute:: descriptor1_version
    .. py:attribute:: text_data
    .. py:attribute:: warp_version
    .. py:attribute:: descriptor2_version
    .. py:attribute:: warp_data
    .. py:attribute:: left
    .. py:attribute:: top
    .. py:attribute:: right
    .. py:attribute:: bottom
    """


class ContentGeneratorExtraData(pretty_namedtuple(
    'ContentGeneratorExtraData',
    'descriptor_version descriptor'
)):
    """
    .. py:attribute:: descriptor_version
    .. py:attribute:: descriptor
    """


class UnicodePathName(pretty_namedtuple(
    'UnicodePathName',
    'descriptor_version descriptor'
)):
    """
    .. py:attribute:: descriptor_version
    .. py:attribute:: descriptor
    """


class AnimationEffects(pretty_namedtuple(
    'AnimationEffects',
    'descriptor_version descriptor'
)):
    """
    .. py:attribute:: descriptor_version
    .. py:attribute:: descriptor
    """


class FilterMask(pretty_namedtuple('FilterMask', 'color opacity')):
    """
    .. py:attribute:: color
    .. py:attribute:: opacity
    """


class VectorOriginationData(pretty_namedtuple(
    'VectorOriginationData',
    'version descriptor_version data'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: descriptor_version
    .. py:attribute:: descriptor
    """


class VectorMaskSetting(pretty_namedtuple(
    'VectorMaskSetting',
    'version invert not_link disable path'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: invert
    .. py:attribute:: not_link
    .. py:attribute:: disable path
    """


class PixelSourceData(pretty_namedtuple('PixelSourceData', 'version data')):
    """
    .. py:attribute:: version
    .. py:attribute:: data
    """


class ArtboardData(pretty_namedtuple('ArtboardData', 'version data')):
    """
    .. py:attribute:: version
    .. py:attribute:: data
    """


class UserMask(pretty_namedtuple('UserMask', 'color opacity flag')):
    """
    .. py:attribute:: color
    .. py:attribute:: opacity
    .. py:attribute:: flag
    """


class FilterEffects(pretty_namedtuple(
    'FilterEffects',
    'uuid version rectangle depth max_channels channels extra_data'
)):
    """
    .. py:attribute:: uuid
    .. py:attribute:: version
    .. py:attribute:: rectangle
    .. py:attribute:: depth
    .. py:attribute:: max_channels
    .. py:attribute:: channels
    .. py:attribute:: extra_data
    """


class FilterEffectChannel(pretty_namedtuple(
    'FilterEffectChannel',
    'is_written compression data'
)):
    """
    .. py:attribute:: is_written
    .. py:attribute:: compression
    .. py:attribute:: data
    """


class PlacedLayerObsolete(pretty_namedtuple(
    'PlacedLayerObsolete',
    'type version uuid page total_pages anti_alias layer_type transformation '
    'warp'
)):
    """
    .. py:attribute:: type
    .. py:attribute:: version
    .. py:attribute:: uuid
    .. py:attribute:: page
    .. py:attribute:: total_pages
    .. py:attribute:: anti_alias
    .. py:attribute:: layer_type
    .. py:attribute:: transformation
    .. py:attribute:: warp
    """


class WarpInformation(pretty_namedtuple(
    'WarpInformation',
    'version descriptor_version descriptor'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: descriptor_version
    .. py:attribute:: descriptor
    """


class Divider(collections.namedtuple('Divider', 'block type key')):
    """
    .. py:attribute:: block
    .. py:attribute:: type
    .. py:attribute:: key
    """
    def __repr__(self):
        return "Divider(%s %r %s, %s)" % (
            self.block, self.type, SectionDivider.name_of(self.type), self.key
        )


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

    decoder = _tagged_block_decoders.get(
        block.key, lambda data, **kwargs: data)
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
    return _decode_descriptor_block(data, SolidColorSetting)


@register(TaggedBlock.PATTERN_FILL_SETTING)
def _decode_ptfl(data, **kwargs):
    return _decode_descriptor_block(data, PatternFillSetting)


@register(TaggedBlock.GRADIENT_FILL_SETTING)
def _decode_grfl(data, **kwargs):
    return _decode_descriptor_block(data, GradientFillSetting)


@register(TaggedBlock.BRIGHTNESS_AND_CONTRAST)
def _decode_brightness_and_contrast(data, **kwargs):
    return BrightnessContrast(*read_fmt("3H B", io.BytesIO(data)))


@register(TaggedBlock.LEVELS)
def _decode_levels(data, **kwargs):
    def read_level_record(fp):
        input_f, input_c, output_f, output_c, gamma = read_fmt("5H", fp)
        return LevelRecord(
            input_f, input_c, output_f, output_c, gamma / 100.0)

    fp = io.BytesIO(data)
    version = read_fmt("H", fp)[0]
    level_records = [read_level_record(fp) for i in range(29)]

    # decode extra level record, Photoshop CS (8.0) Additional information
    if fp.tell() < len(data):
        signature = read_fmt('4s', fp)[0]
        assert signature == b'Lvls', 'unexpected token: {0}'.format(signature)
        _ = read_fmt('H', fp)[0]  # version (= 3)
        count = read_fmt('H', fp)[0] - 29
        level_records = level_records + [
            read_level_record(fp) for i in range(count)
        ]

    return LevelsSettings(version, level_records)


@register(TaggedBlock.CURVES)
def _decode_curves(data, **kwargs):
    """
    Curve decoding is highly experimental and unstable.
    """
    fp = io.BytesIO(data)
    # Documentation wrong.
    is_map, version, count_map = read_fmt("B H I", fp)
    if version not in (1, 4):
        warnings.warn("Invalid curves version {}".format(version))
        return data
    if version == 1:
        count = bin(count_map).count("1")  # Bitmap = channel index?

    items = []
    for i in range(count):
        if is_map:
            # This lookup format is never documented.
            points = list(read_fmt("256B", fp))
        else:
            point_count = read_fmt("H", fp)[0]
            if point_count <= 2 or 19 <= point_count:
                warnings.warn("point count not in [2, 19]")
                return data
            points = [read_fmt("2H", fp) for c in range(point_count)]
        items.append(CurveData(None, points))
    extra = None
    if version == 1:
        tag, version_, count_ = read_fmt("4s H I", fp)
        assert tag == b'Crv '
        extra_items = []
        for i in range(count_):
            if is_map:
                channel_index = read_fmt("H", fp)[0]
                points = list(read_fmt("256B", fp))
            else:
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


@register(TaggedBlock.HUE_SATURATION_V4)
@register(TaggedBlock.HUE_SATURATION)
def _decode_hue_saturation(data, **kwargs):
    fp = io.BytesIO(data)
    version, enable_colorization, _ = read_fmt('H 2B', fp)
    if version != 2:
        warnings.warn("Invalid Hue/saturation version {}".format(version))
        return data
    colorization = read_fmt("3h", fp)
    master = read_fmt("3h", fp)
    items = []
    for i in range(6):
        range_values = read_fmt("4h", fp)
        settings_values = read_fmt("3h", fp)
        items.append(HueSaturationData(range_values, settings_values))
    return HueSaturation(version, enable_colorization, colorization, master,
                         items)


@register(TaggedBlock.COLOR_BALANCE)
def _decode_color_balance(data, **kwargs):
    # Undocumented, following PhotoFilter format.
    fp = io.BytesIO(data)
    shadows = read_fmt("3h", fp)
    midtones = read_fmt("3h", fp)
    highlights = read_fmt("3h", fp)
    preserve_luminosity = read_fmt("B", fp)[0]
    return ColorBalance(shadows, midtones, highlights, preserve_luminosity)


@register(TaggedBlock.BLACK_AND_WHITE)
def _decode_black_white(data, **kwargs):
    return _decode_descriptor_block(data, BlackWhite)


@register(TaggedBlock.PHOTO_FILTER)
def _decode_photo_filter(data, **kwargs):
    fp = io.BytesIO(data)
    version = read_fmt("H", fp)[0]
    if version not in (2, 3):
        warnings.warn("Invalid Photo Filter version {}".format(version))
        return data
    if version == 3:
        xyz = read_fmt("3I", fp)
        color_space = None
        color_components = None
    else:
        xyz = None
        color_space = read_fmt("H", fp)[0]
        color_components = read_fmt("4H", fp)
    density, preserve_luminosity = read_fmt("I B", fp)
    return PhotoFilter(version, xyz, color_space, color_components,
                       density, preserve_luminosity)


@register(TaggedBlock.CHANNEL_MIXER)
def _decode_channel_mixer(data, **kwargs):
    fp = io.BytesIO(data)
    version, monochrome = read_fmt("2H", fp)
    settings = read_fmt("5H", fp)
    return ChannelMixer(version, monochrome, settings)


@register(TaggedBlock.COLOR_LOOKUP)
def _decode_color_lookup(data, **kwargs):
    fp = io.BytesIO(data)
    version, descriptor_version = read_fmt("H I", fp)

    try:
        return ColorLookup(version, descriptor_version,
                           decode_descriptor(None, fp))
    except UnknownOSType as e:
        warnings.warn("Ignoring tagged block %s" % e)
        return data


@register(TaggedBlock.INVERT)
def _decode_invert(data, **kwargs):
    return Invert()


@register(TaggedBlock.POSTERIZE)
def _decode_posterize(data, **kwargs):
    return Posterize(read_fmt("2H", io.BytesIO(data))[0])


@register(TaggedBlock.THRESHOLD)
def _decode_threshold(data, **kwargs):
    return Threshold(read_fmt("2H", io.BytesIO(data))[0])


@register(TaggedBlock.SELECTIVE_COLOR)
def _decode_selective_color(data, **kwargs):
    fp = io.BytesIO(data)
    version, method = read_fmt("2H", fp)
    if version != 1:
        warnings.warn("Invalid Selective Color version %s" % (version))
        return data
    items = [read_fmt("4h", fp) for i in range(10)]
    return SelectiveColor(version, method, items)


@register(TaggedBlock.PATTERNS1)
@register(TaggedBlock.PATTERNS2)
@register(TaggedBlock.PATTERNS3)
def _decode_patterns(data, **kwargs):
    fp = io.BytesIO(data)
    patterns = []
    while fp.tell() < len(data) - 4:
        length = read_fmt("I", fp)[0]
        if length == 0:
            break
        patterns.append(_decode_pattern(fp.read(length)))
        extra_bytes = fp.tell() % 4
        if extra_bytes:
            fp.read(4 - extra_bytes)  # 4-bytes padding.
    return patterns


def _decode_pattern(data):
    fp = io.BytesIO(data)
    version, image_mode = read_fmt("2I", fp)
    if version != 1:
        warnings.warn("Unsupported patterns version %s" % (version))
        return data

    point = read_fmt("2h", fp)
    name = read_unicode_string(fp)
    pattern_id = read_pascal_string(fp, 'ascii')
    color_table = None
    if image_mode == ColorMode.INDEXED:
        color_table = [read_fmt("3B", fp) for i in range(256)]
        read_fmt('4B', fp)  # Undocumented field here...
    vma_list = _decode_virtual_memory_array_list(fp)
    return Pattern(version, image_mode, point, name, pattern_id, color_table,
                   vma_list)


def _decode_virtual_memory_array_list(fp):
    version, length = read_fmt("2I", fp)
    if version != 3:
        warnings.warn("Unsupported virtual memory array list %s" % (version))
        return None
    start = fp.tell()
    rectangle = read_fmt("4I", fp)
    num_channels = read_fmt("I", fp)[0]
    channels = []
    for i in range(num_channels + 2):
        is_written = read_fmt("I", fp)[0]
        if is_written == 0:
            continue
        array_length = read_fmt("I", fp)[0]
        if array_length == 0:
            continue
        depth = read_fmt("I", fp)[0]
        array_rect = read_fmt("4I", fp)
        pixel_depth, compression = read_fmt("H B", fp)
        channel_data = RawData(fp.read(array_length - 23))
        channels.append(VirtualMemoryArray(
            is_written, depth, array_rect, pixel_depth, compression,
            channel_data
        ))
    return VirtualMemoryArrayList(version, rectangle, channels)


@register(TaggedBlock.GRADIENT_MAP_SETTING)
def _decode_gradient_settings(data, **kwargs):
    fp = io.BytesIO(data)
    version, is_reversed, is_dithered = read_fmt("H 2B", fp)
    if version != 1:
        warnings.warn("Invalid Gradient settings version %s" % (version))
        return data
    name = read_unicode_string(fp)
    color_count = read_fmt("H", fp)[0]
    color_stops = []
    for i in range(color_count):
        location, midpoint, mode = read_fmt("2i H", fp)
        color = read_fmt("4H", fp)
        color_stops.append(ColorStop(location, midpoint, mode, color))
        read_fmt("H", fp)  # Undocumented pad.
    transparency_count = read_fmt("H", fp)[0]
    transparency_stops = []
    for i in range(transparency_count):
        transparency_stops.append(read_fmt("2I H", fp))

    expansion, interpolation, length, mode = read_fmt("4H", fp)
    if expansion != 2 or length != 32:
        warnings.warn("Ignoring Gradient settings")
        return data
    random_seed, show_transparency, use_vector_color = read_fmt("I 2H", fp)
    roughness, color_model = read_fmt("I H", fp)
    minimum_color = read_fmt("4H", fp)
    maximum_color = read_fmt("4H", fp)
    read_fmt("H", fp)  # Dummy pad.

    return GradientSettings(
        version, is_reversed, is_dithered, name, color_stops,
        transparency_stops, expansion, interpolation, length, mode,
        random_seed, show_transparency, use_vector_color, roughness,
        color_model, minimum_color, maximum_color)


@register(TaggedBlock.EXPORT_SETTING1)
@register(TaggedBlock.EXPORT_SETTING2)
def _decode_extn(data, **kwargs):
    return _decode_descriptor_block(data, ExportSetting)


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


@register(TaggedBlock.VECTOR_STROKE_DATA)
def _decode_vector_stroke_data(data, **kwargs):
    fp = io.BytesIO(data)
    version = read_fmt("I", fp)[0]

    if version != 16:
        warnings.warn("Invalid vstk version %s" % (version))
        return data

    try:
        data = decode_descriptor(None, fp)
        return VectorStrokeSetting(version, data)
    except UnknownOSType as e:
        warnings.warn("Ignoring vstk tagged block (%s)" % e)
        return data


@register(TaggedBlock.VECTOR_STROKE_CONTENT_DATA)
def _decode_vector_stroke_content_data(data, **kwargs):
    fp = io.BytesIO(data)
    key, version = read_fmt("II", fp)

    if version != 16:
        warnings.warn("Invalid vscg version %s" % (version))
        return data

    try:
        descriptor = decode_descriptor(None, fp)
    except UnknownOSType as e:
        warnings.warn("Ignoring vscg tagged block (%s)" % e)
        return data

    return VectorStrokeContentSetting(key, version, descriptor)


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
    layers = layers._read_layers(
        fp, 'latin1', 32, length=len(data), version=version)
    return decode_layers(layers, version)


@register(TaggedBlock.LAYER_16)
def _decode_layer16(data, version=1, **kwargs):
    from psd_tools.reader import layers
    from psd_tools.decoder.decoder import decode_layers
    fp = io.BytesIO(data)
    layers = layers._read_layers(
        fp, 'latin1', 16, length=len(data), version=version)
    return decode_layers(layers, version)


@register(TaggedBlock.TYPE_TOOL_OBJECT_SETTING)
def _decode_type_tool_object_setting(data, **kwargs):
    fp = io.BytesIO(data)
    ver, xx, xy, yx, yy, tx, ty, txt_ver, descr1_ver = read_fmt(
        "H 6d H I", fp)

    # This decoder needs to be updated if we have new formats.
    if ver != 1 or txt_ver != 50 or descr1_ver != 16:
        warnings.warn(
            "Ignoring type setting tagged block due to old versions")
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
            text_data.items[index] = (
                b'EngineData', engine_data.decode(item[1].value))

    warp_ver, descr2_ver = read_fmt("H I", fp)
    if warp_ver != 1 or descr2_ver != 16:
        warnings.warn(
            "Ignoring type setting tagged block due to old versions")
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


@register(TaggedBlock.CONTENT_GENERATOR_EXTRA_DATA)
def _decode_content_generator_extra_data(data, **kwargs):
    return _decode_descriptor_block(data, ContentGeneratorExtraData)


@register(TaggedBlock.TEXT_ENGINE_DATA)
def _decode_text_engine_data(data, **kwargs):
    return engine_data.decode(data)


@register(TaggedBlock.UNICODE_PATH_NAME)
def _decode_unicode_path_name(data, **kwargs):
    if data:
        return _decode_descriptor_block(data, UnicodePathName)
    else:
        warnings.warn("Empty Unicode Path Name")
        return None


@register(TaggedBlock.ANIMATION_EFFECTS)
def _decode_animation_effects(data, **kwargs):
    return _decode_descriptor_block(data, AnimationEffects)


@register(TaggedBlock.FILTER_MASK)
def _decode_filter_mask(data, **kwargs):
    fp = io.BytesIO(data)
    color = decode_color(fp)
    opacity = read_fmt("H", fp)[0]
    return FilterMask(color, opacity)


@register(TaggedBlock.VECTOR_ORIGINATION_DATA)
def _decode_vector_origination_data(data, **kwargs):
    fp = io.BytesIO(data)
    ver, descr_ver = read_fmt("II", fp)

    if ver != 1 and descr_ver != 16:
        warnings.warn("Invalid vmsk version %s %s" % (ver, descr_ver))
        return data

    try:
        vector_origination_data = decode_descriptor(None, fp)
    except UnknownOSType as e:
        warnings.warn("Ignoring vector origination tagged block (%s)" % e)
        return data

    return VectorOriginationData(ver, descr_ver, vector_origination_data)


@register(TaggedBlock.PIXEL_SOURCE_DATA1)
def _decode_pixel_source_data1(data, **kwargs):
    return _decode_descriptor_block(data, PixelSourceData)


@register(TaggedBlock.PIXEL_SOURCE_DATA2)
def _decode_pixel_source_data2(data, **kwargs):
    fp = io.BytesIO(data)
    length = read_fmt("Q", fp)[0]
    return fp.read(length)


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

    path = decode_path_resource(fp.read())
    return VectorMaskSetting(
        ver, (0x01 & flags) > 0, (0x02 & flags) > 0, (0x04 & flags) > 0, path)


@register(TaggedBlock.ARTBOARD_DATA1)
@register(TaggedBlock.ARTBOARD_DATA2)
@register(TaggedBlock.ARTBOARD_DATA3)
def _decode_artboard_data(data, **kwargs):
    return _decode_descriptor_block(data, ArtboardData)


@register(TaggedBlock.PLACED_LAYER_OBSOLETE1)
@register(TaggedBlock.PLACED_LAYER_OBSOLETE2)
def _decode_placed_layer(data, **kwargs):
    fp = io.BytesIO(data)
    type_, version = read_fmt("2I", fp)
    if version != 3:
        warnings.warn("Unsupported placed layer version %s" % (version))
        return data
    uuid = read_pascal_string(fp, "ascii")
    page, total_pages, anti_alias, layer_type = read_fmt("4I", fp)
    transformation = read_fmt("8d", fp)
    warp_version, warp_desc_version = read_fmt("2I", fp)
    descriptor = decode_descriptor(None, fp)
    warp = WarpInformation(warp_version, warp_desc_version, descriptor)
    return PlacedLayerObsolete(type_, version, uuid, page, total_pages,
                               anti_alias, layer_type, transformation, warp)


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


@register(TaggedBlock.USER_MASK)
def _decode_user_mask(data, **kwargs):
    fp = io.BytesIO(data)
    color = decode_color(fp)
    opacity, flag = read_fmt("H B", fp)
    return UserMask(color, opacity, flag)


@register(TaggedBlock.FILTER_EFFECTS1)
@register(TaggedBlock.FILTER_EFFECTS2)
@register(TaggedBlock.FILTER_EFFECTS3)
def _decode_filter_effects(data, **kwargs):
    fp = io.BytesIO(data)
    version, length = read_fmt("I Q", fp)
    if version not in (1, 2, 3):
        warnings.warn("Unknown filter effects version %d" % version)
        return data

    return _decode_filter_effect_item(fp.read(length))


def _decode_filter_effect_item(data):
    fp = io.BytesIO(data)
    uuid = read_pascal_string(fp, "ascii")
    version, length = read_fmt("I Q", fp)
    assert version == 1, "Unknown filter effect version %d" % version

    rectangle = read_fmt("4i", fp)
    depth, max_channels = read_fmt("2I", fp)

    channels = []
    for i in range(max_channels + 2):
        is_written = read_fmt("I", fp)[0]
        assert is_written in (0, 1)
        if is_written:
            channel_len, compression = read_fmt("Q H", fp)
            channel_data = fp.read(max(0, channel_len - 2))
            channels.append(FilterEffectChannel(is_written, compression,
                                                RawData(channel_data)))
        else:
            channels.append(FilterEffectChannel(is_written, 0, None))

    # There seems to be undocumented extra fields.
    extra_data = None
    if len(data) > fp.tell() and read_fmt("B", fp)[0]:
        extra_rect = read_fmt("4i", fp)
        extra_length, extra_compression = read_fmt("Q H", fp)
        extra_data = (extra_rect, extra_compression,
                      RawData(fp.read(extra_length)))

    return FilterEffects(uuid, version, rectangle, depth, max_channels,
                         channels, extra_data)
