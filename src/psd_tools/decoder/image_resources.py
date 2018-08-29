# -*- coding: utf-8 -*-
"""
Module for decoding image resources section.

Image resources section holds key-value store of various resources that are
relevant to the photoshop document. The keys are specified by
:py:class:`~psd_tools.constants.ImageResourceID`.

"""
from __future__ import absolute_import, unicode_literals, division
import io
import struct
import warnings
from collections import namedtuple
from psd_tools.utils import (read_pascal_string, unpack, read_fmt,
                             read_unicode_string, be_array_from_bytes,
                             decode_fixed_point_32bit)
from psd_tools.constants import (ImageResourceID, PrintScaleStyle,
                                 DisplayResolutionUnit, DimensionUnit)
from psd_tools.decoder import decoders
from psd_tools.decoder.actions import decode_descriptor, UnknownOSType, RawData
from psd_tools.decoder.color import decode_color
from psd_tools.decoder.path import decode_path_resource

_image_resource_decoders, register = decoders.new_registry()

_image_resource_decoders.update({
    ImageResourceID.LAYER_STATE_INFO:           decoders.single_value("H"),
    ImageResourceID.WATERMARK:                  decoders.single_value("B"),
    ImageResourceID.ICC_UNTAGGED_PROFILE:       decoders.boolean(),
    ImageResourceID.EFFECTS_VISIBLE:            decoders.boolean(),
    ImageResourceID.IDS_SEED_NUMBER:            decoders.single_value("I"),
    ImageResourceID.INDEXED_COLOR_TABLE_COUNT:  decoders.single_value("H"),
    ImageResourceID.TRANSPARENCY_INDEX:         decoders.single_value("H"),
    ImageResourceID.GLOBAL_ALTITUDE:            decoders.single_value("i"),
    ImageResourceID.GLOBAL_ANGLE:               decoders.single_value("i"),
    ImageResourceID.COPYRIGHT_FLAG:             decoders.boolean("H"),

    ImageResourceID.ALPHA_NAMES_UNICODE:        decoders.unicode_string,
    ImageResourceID.WORKFLOW_URL:               decoders.unicode_string,
    ImageResourceID.AUTO_SAVE_FILE_PATH:        decoders.unicode_string,
    ImageResourceID.AUTO_SAVE_FORMAT:           decoders.unicode_string,
})


class HalftoneScreen(namedtuple(
    'HalftoneScreen',
    'ink_frequency units angle shape accurate_screen printer_default'
)):
    """
    .. py:attribute:: ink_frequency
    .. py:attribute:: units
    .. py:attribute:: angle
    .. py:attribute:: shape
    .. py:attribute:: accurate_screen
    .. py:attribute:: printer_default
    """


class TransferFunction(namedtuple('TransferFunction', 'curve override')):
    """
    .. py:attribute:: curve
    .. py:attribute:: override
    """


class PrintScale(namedtuple('PrintScale', 'style x y scale')):
    """
    .. py:attribute:: style
    .. py:attribute:: x
    .. py:attribute:: y
    .. py:attribute:: scale
    """


class PrintFlags(namedtuple(
    'PrintFlags',
    'labels crop_marks color_bars registration_marks negative flip '
    'interpolate caption print_flags'
)):
    """
    .. py:attribute:: labels
    .. py:attribute:: crop_marks
    .. py:attribute:: color_bars
    .. py:attribute:: registration_marks
    .. py:attribute:: negative
    .. py:attribute:: flip
    .. py:attribute:: interpolate
    .. py:attribute:: caption
    .. py:attribute:: print_flags
    """


class PrintFlagsInfo(namedtuple(
    'PrintFlagsInfo',
    'version center_crop_marks bleed_width_value bleed_width_scale'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: center_crop_marks
    .. py:attribute:: bleed_width_value
    .. py:attribute:: bleed_width_scale
    """


class ThumbnailResource(namedtuple(
    'ThumbnailResource',
    'format width height widthbytes total_size size bits planes data'
)):
    """
    """


class SlicesHeader(namedtuple(
    'SlicesHeader',
    'descriptor_version descriptor'
)):
    """
    .. py:attribute:: format
    .. py:attribute:: width
    .. py:attribute:: height
    .. py:attribute:: widthbytes
    .. py:attribute:: total_size
    .. py:attribute:: size
    .. py:attribute:: bits
    .. py:attribute:: planes data
    """


class SlicesHeaderV6(namedtuple(
    'SlicesHeaderV6',
    'top left bottom right name count items'
)):
    """
    .. py:attribute:: top
    .. py:attribute:: left
    .. py:attribute:: bottom
    .. py:attribute:: right
    .. py:attribute:: name
    .. py:attribute:: count
    .. py:attribute:: items
    """


class SlicesResourceBlock(namedtuple(
    'SlicesResourceBlock',
    'id group_id origin associated_id name type left top right bottom url '
    'target message alt_tag cell_is_html cell_text horizontal_alignment '
    'vertical_alignment alpha red green blue descriptor'
)):
    """
    .. py:attribute:: id
    .. py:attribute:: group_id
    .. py:attribute:: origin
    .. py:attribute:: associated_id
    .. py:attribute:: name
    .. py:attribute:: type
    .. py:attribute:: left
    .. py:attribute:: top
    .. py:attribute:: right
    .. py:attribute:: bottom
    .. py:attribute:: url
    .. py:attribute:: target
    .. py:attribute:: message
    .. py:attribute:: alt_tag
    .. py:attribute:: cell_is_html
    .. py:attribute:: cell_text
    .. py:attribute:: horizontal_alignment
    .. py:attribute:: vertical_alignment
    .. py:attribute:: alpha
    .. py:attribute:: red
    .. py:attribute:: green
    .. py:attribute:: blue
    .. py:attribute:: descriptor
    """


class VersionInfo(namedtuple(
    'VersionInfo',
    'version has_real_merged_data writer_name reader_name file_version'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: has_real_merged_data
    .. py:attribute:: writer_name
    .. py:attribute:: reader_name
    .. py:attribute:: file_version
    """


class UrlListItem(namedtuple('UrlListItem', 'number id url')):
    """
    .. py:attribute:: number
    .. py:attribute:: id
    .. py:attribute:: url
    """


class PixelAspectRatio(namedtuple('PixelAspectRatio', 'version aspect')):
    """
    .. py:attribute:: version
    .. py:attribute:: aspect
    """


class ResolutionInfo(namedtuple(
    'ResolutionInfo',
    'h_res h_res_unit width_unit v_res v_res_unit height_unit'
)):
    """
    .. py:attribute:: h_res
    .. py:attribute:: h_res_unit
    .. py:attribute:: width_unit
    .. py:attribute:: v_res
    .. py:attribute:: v_res_unit
    .. py:attribute:: height_unit
    """
    def __repr__(self):

        return ("ResolutionInfo(h_res=%s, h_res_unit=%s, v_res=%s, "
                "v_res_unit=%s, width_unit=%s, height_unit=%s)") % (
            self.h_res,
            DisplayResolutionUnit.name_of(self.h_res_unit),
            self.v_res,
            DisplayResolutionUnit.name_of(self.v_res_unit),
            DimensionUnit.name_of(self.width_unit),
            DimensionUnit.name_of(self.height_unit),
        )


class LayerComps(namedtuple('LayerComps', 'descriptor_version descriptor')):
    """
    .. py:attribute:: descriptor_version
    .. py:attribute:: descriptor
    """


class MeasurementScale(namedtuple(
    'MeasurementScale',
    'descriptor_version descriptor'
)):
    """
    .. py:attribute:: descriptor_version
    .. py:attribute:: descriptor
    """


class TimelineInformation(namedtuple(
    'TimelineInformation',
    'descriptor_version descriptor'
)):
    """
    .. py:attribute:: descriptor_version
    .. py:attribute:: descriptor
    """


class SheetDisclosure(namedtuple(
    'SheetDisclosure',
    'descriptor_version descriptor'
)):
    """
    .. py:attribute:: descriptor_version
    .. py:attribute:: descriptor
    """


class OnionSkins(namedtuple('OnionSkins', 'descriptor_version descriptor')):
    """
    .. py:attribute:: descriptor_version
    .. py:attribute:: descriptor
    """


class CountInformation(namedtuple(
    'CountInformation',
    'descriptor_version descriptor'
)):
    """
    .. py:attribute:: descriptor_version
    .. py:attribute:: descriptor
    """


class PrintInformation(namedtuple(
    'PrintInformation',
    'descriptor_version descriptor'
)):
    """
    .. py:attribute:: descriptor_version
    .. py:attribute:: descriptor
    """


class PrintStyle(namedtuple(
    'PrintStyle',
    'descriptor_version descriptor'
)):
    """
    .. py:attribute:: descriptor_version
    .. py:attribute:: descriptor
    """


class PathSelectionState(namedtuple(
    'PathSelectionState',
    'descriptor_version descriptor'
)):
    """
    .. py:attribute:: descriptor_version
    .. py:attribute:: descriptor
    """


class GridGuideResource(namedtuple(
    'GridGuideResource',
    'version grid_horizontal grid_vertical guides'
)):
    """
    .. py:attribute:: version
    .. py:attribute:: grid_horizontal
    .. py:attribute:: grid_vertical
    .. py:attribute:: guides
    """


class GuideResourceBlock(namedtuple(
    'GuideResourceBlock',
    'location direction'
)):
    """
    .. py:attribute:: location
    .. py:attribute:: direction
    """


class OriginPathInfo(namedtuple(
    'OriginPathInfo',
    'descriptor_version descriptor'
)):
    """
    .. py:attribute:: descriptor_version
    .. py:attribute:: descriptor
    """


def decode(image_resource_blocks):
    """
    Replaces ``data`` of image resource blocks with parsed data structures.
    """
    return [parse_image_resource(res) for res in image_resource_blocks]


def parse_image_resource(resource):
    """
    Replaces ``data`` of image resource block with a parsed data structure.
    """
    if not ImageResourceID.is_known(resource.resource_id):
        warnings.warn("Unknown resource_id (%s)" % resource.resource_id)

    if (ImageResourceID.PATH_INFO_0 <= resource.resource_id and
            ImageResourceID.PATH_INFO_LAST >= resource.resource_id):
        decoder = decode_path_resource
    else:
        decoder = _image_resource_decoders.get(resource.resource_id,
                                               lambda data: data)
    return resource._replace(data=decoder(resource.data))


def _decode_descriptor_resource(data, kls):
    if isinstance(data, bytes):
        fp = io.BytesIO(data)
    version = read_fmt("I", fp)[0]

    try:
        return kls(version, decode_descriptor(None, fp))
    except UnknownOSType as e:
        warnings.warn("Ignoring image resource %s" % e)
        return data


@register(ImageResourceID.GRAYSCALE_HALFTONING_INFO)
@register(ImageResourceID.COLOR_HALFTONING_INFO)
@register(ImageResourceID.DUOTONE_HALFTONING_INFO)
def _decode_halftone_screens(data):
    if not len(data) == 72:
        return data
    fp = io.BytesIO(data)
    descriptions = []
    for i in range(4):
        # 16 bits + 16 bits fixed points.
        ink_frequency = float(read_fmt("I", fp)[0]) / 0x10000
        units = read_fmt("h", fp)[0]
        angle = read_fmt("I", fp)[0] / 0x10000
        shape = read_fmt("H", fp)[0]
        padding = read_fmt("I", fp)[0]
        if padding:
            warnings.warn("Invalid halftone screens")
            return data
        accurate_screen, printer_default = read_fmt("2?", fp)
        descriptions.append(HalftoneScreen(
            ink_frequency, units, angle, shape, accurate_screen,
            printer_default))
    return descriptions


@register(ImageResourceID.GRAYSCALE_TRANSFER_FUNCTION)
@register(ImageResourceID.COLOR_TRANSFER_FUNCTION)
@register(ImageResourceID.DUOTONE_TRANSFER_FUNCTION)
def _decode_transfer_function(data):
    if not len(data) == 112:
        return data
    fp = io.BytesIO(data)
    functions = []
    for i in range(4):
        curve = read_fmt("13h", fp)
        override = read_fmt("H", fp)[0]
        functions.append(TransferFunction(curve, override))
    return functions


@register(ImageResourceID.LAYER_GROUP_INFO)
def _decode_layer_group_info(data):
    return be_array_from_bytes("H", data)


@register(ImageResourceID.LAYER_SELECTION_IDS)
def _decode_layer_selection(data):
    return be_array_from_bytes("I", data[2:])


@register(ImageResourceID.LAYER_GROUPS_ENABLED_ID)
def _decode_layer_groups_enabled_id(data):
    return be_array_from_bytes("B", data)


@register(ImageResourceID.THUMBNAIL_RESOURCE_PS4)
@register(ImageResourceID.THUMBNAIL_RESOURCE)
def _decode_thumbnail_resource(data):
    fp = io.BytesIO(data)
    fmt, width, height, widthbytes, total_size, size, bits, planes = read_fmt(
        "6I2H", fp)
    jfif = RawData(fp.read(size))
    return ThumbnailResource(fmt, width, height, widthbytes, total_size, size,
                             bits, planes, jfif)


@register(ImageResourceID.SLICES)
def _decode_slices(data):
    fp = io.BytesIO(data)
    version = read_fmt('I', fp)[0]
    if version == 6:
        return _decode_slices_v6(fp)
    elif version in (7, 8):
        return _decode_descriptor_resource(fp.read(-1), SlicesHeader)
    else:
        warnings.warn("Unsupported slices version %s. "
                      "Only version 7 or 8 slices supported." % version)
        return data


def _decode_slices_v6(fp):
    bbox = read_fmt('4I', fp)
    name = read_unicode_string(fp)
    count = read_fmt('I', fp)[0]
    items = []
    for index in range(count):
        items.append(_decode_slices_v6_block(fp))
    return SlicesHeaderV6(bbox[0], bbox[1], bbox[2], bbox[3], name, count,
                          items)


def _decode_slices_v6_block(fp):
    slice_id, group_id, origin = read_fmt('3I', fp)
    associated_id = read_fmt('I', fp)[0] if origin == 1 else None
    name = read_unicode_string(fp)
    slice_type, left, top, right, bottom = read_fmt('5I', fp)
    url = read_unicode_string(fp)
    target = read_unicode_string(fp)
    message = read_unicode_string(fp)
    alt_tag = read_unicode_string(fp)
    cell_is_html = read_fmt('?', fp)[0]
    cell_text = read_unicode_string(fp)
    horizontal_alignment, vertical_alignment = read_fmt('2I', fp)
    alpha, red, green, blue = read_fmt('4B', fp)
    # Some version stores descriptor here, but the documentation unclear...
    descriptor = None
    return SlicesResourceBlock(
        slice_id, group_id, origin, associated_id, name, slice_type, left,
        top, right, bottom, url, target, message, alt_tag, cell_is_html,
        cell_text, horizontal_alignment, vertical_alignment, alpha, red,
        green, blue, descriptor)


@register(ImageResourceID.URL_LIST)
def _decode_url_list(data):
    urls = []
    fp = io.BytesIO(data)
    count = read_fmt("I", fp)[0]

    try:
        for i in range(count):
            number, id = read_fmt("2I", fp)
            url = read_unicode_string(fp)
            urls.append(UrlListItem(number, id, url))
        return urls
    except UnknownOSType as e:
        warnings.warn("Ignoring image resource %s" % e)
        return data


@register(ImageResourceID.VERSION_INFO)
def _decode_version_info(data):
    fp = io.BytesIO(data)

    return VersionInfo(
        read_fmt("I", fp)[0],
        read_fmt("?", fp)[0],
        read_unicode_string(fp),
        read_unicode_string(fp),
        read_fmt("I", fp)[0],
    )


@register(ImageResourceID.EXIF_DATA_1)
@register(ImageResourceID.EXIF_DATA_3)
def _decode_exif_data(data):
    try:
        import exifread
    except:
        warnings.warn("EXIF data is ignored. Install exifread to decode.")
        return data

    fp = io.BytesIO(data)
    tags = exifread.process_file(fp)
    exif = {}
    for key in tags.keys():
        ifd = tags[key]
        if isinstance(ifd, exifread.classes.IfdTag):
            field_type = exifread.tags.FIELD_TYPES[ifd.field_type - 1]
            if isinstance(ifd.printable, bytes):
                try:
                    value = ifd.printable.decode('utf-8')
                except UnicodeDecodeError:
                    value = ifd.printable.encode('string_escape')
            else:
                value = ifd.printable
            if field_type[1] in ('A', 'B'):
                exif[key] = value
            else:
                try:
                    exif[key] = int(value)
                except ValueError:
                    exif[key] = value
        else:
            # Seems sometimes EXIF data is corrupt.
            pass
    return exif


@register(ImageResourceID.PIXEL_ASPECT_RATIO)
def _decode_pixel_aspect_ration(data):
    version = unpack("I", data[:4])[0]
    aspect = unpack("d", data[4:])[0]
    return PixelAspectRatio(version, aspect)


@register(ImageResourceID.PRINT_FLAGS)
def _decode_print_flags(data):
    try:
        return PrintFlags(*(unpack("9?x", data)))
    except struct.error as e:
        warnings.warn("%s" % e)
        return data


@register(ImageResourceID.PRINT_FLAGS_INFO)
def _decode_print_flags_info(data):
    return PrintFlagsInfo(*(unpack("HBxIh", data)))


@register(ImageResourceID.PRINT_SCALE)
def _decode_print_scale(data):
    style, x, y, scale = unpack("H3f", data)

    if not PrintScaleStyle.is_known(style):
        warnings.warn("Unknown print scale style (%s)" % style)

    return PrintScale(style, x, y, scale)


@register(ImageResourceID.CAPTION_PASCAL)
def _decode_caption_pascal(data):
    fp = io.BytesIO(data)
    return read_pascal_string(fp, 'ascii')


@register(ImageResourceID.RESOLUTION_INFO)
def _decode_resolution(data):
    h_res, h_res_unit, width_unit, v_res, v_res_unit, height_unit = unpack(
        "4s HH 4s HH", data)

    h_res = decode_fixed_point_32bit(h_res)
    v_res = decode_fixed_point_32bit(v_res)

    return ResolutionInfo(
        h_res, h_res_unit, width_unit, v_res, v_res_unit, height_unit)


@register(ImageResourceID.GRID_AND_GUIDES_INFO)
def _decode_grid_and_guides_info(data):
    fp = io.BytesIO(data)
    version, grid_h, grid_v, guide_count = read_fmt("4I", fp)

    try:
        guides = []
        for i in range(guide_count):
            guides.append(GuideResourceBlock(*read_fmt("IB", fp)))
        return GridGuideResource(version, grid_h, grid_v, guides)
    except UnknownOSType as e:
        warnings.warn("Ignoring image resource %s" % e)
        return data


@register(ImageResourceID.ICC_PROFILE)
def _decode_icc(data):
    try:
        from PIL import ImageCms
        return ImageCms.ImageCmsProfile(io.BytesIO(data))
    except ImportError:
        warnings.warn(
            "ICC profile is not handled; colors could be incorrect. "
            "Please build PIL or Pillow with littlecms/littlecms2 support.")
        return data


@register(ImageResourceID.BACKGROUND_COLOR)
def _decode_background_color(data):
    fp = io.BytesIO(data)
    return decode_color(fp)


@register(ImageResourceID.LAYER_COMPS)
def _decode_layer_comps(data):
    return _decode_descriptor_resource(data, LayerComps)


@register(ImageResourceID.MEASUREMENT_SCALE)
def _decode_measurement_scale(data):
    return _decode_descriptor_resource(data, MeasurementScale)


@register(ImageResourceID.TIMELINE_INFO)
def _decode_timeline_information(data):
    return _decode_descriptor_resource(data, TimelineInformation)


@register(ImageResourceID.SHEET_DISCLOSURE)
def _decode_sheet_disclosure(data):
    return _decode_descriptor_resource(data, SheetDisclosure)


@register(ImageResourceID.ONION_SKINS)
def _decode_onion_skins(data):
    return _decode_descriptor_resource(data, OnionSkins)


@register(ImageResourceID.COUNT_INFO)
def _decode_count_information(data):
    return _decode_descriptor_resource(data, CountInformation)


@register(ImageResourceID.PRINT_INFO_CS5)
def _decode_print_information_cs5(data):
    return _decode_descriptor_resource(data, PrintInformation)


@register(ImageResourceID.PRINT_STYLE)
def _decode_print_style(data):
    return _decode_descriptor_resource(data, PrintStyle)


@register(ImageResourceID.PATH_SELECTION_STATE)
def _decode_path_selection_state(data):
    return _decode_descriptor_resource(data, PathSelectionState)


@register(ImageResourceID.CLIPPING_PATH_NAME)
def _decode_clipping_path_name(data):
    fp = io.BytesIO(data)  # TODO: flatness and fill rule decoding?
    return read_pascal_string(fp, 'ascii')


@register(ImageResourceID.ORIGIN_PATH_INFO)
def _decode_origin_path_info(data):
    return _decode_descriptor_resource(data, OriginPathInfo)
