# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, division
import io
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

_image_resource_decoders, register = decoders.new_registry()

_image_resource_decoders.update({
    ImageResourceID.LAYER_STATE_INFO:           decoders.single_value("H"),
    ImageResourceID.WATERMARK:                  decoders.single_value("B"),
    ImageResourceID.ICC_UNTAGGED_PROFILE:       decoders.boolean(),
    ImageResourceID.EFFECTS_VISIBLE:            decoders.boolean(),
    ImageResourceID.IDS_SEED_NUMBER:            decoders.single_value("I"),
    ImageResourceID.INDEXED_COLOR_TABLE_COUNT:  decoders.single_value("H"),
    ImageResourceID.TRANSPARENCY_INDEX:         decoders.single_value("H"),
    ImageResourceID.GLOBAL_ALTITUDE:            decoders.single_value("I"),
    ImageResourceID.GLOBAL_ANGLE_OBSOLETE:      decoders.single_value("I"),
    ImageResourceID.COPYRIGHT_FLAG:             decoders.boolean("H"),

    ImageResourceID.ALPHA_NAMES_UNICODE:        decoders.unicode_string,
    ImageResourceID.WORKFLOW_URL:               decoders.unicode_string,
    ImageResourceID.AUTO_SAVE_FILE_PATH:        decoders.unicode_string,
    ImageResourceID.AUTO_SAVE_FORMAT:           decoders.unicode_string,
})

PrintScale = namedtuple('PrintScale', 'style, x, y, scale')
PrintFlags = namedtuple(
    'PrintFlags', 'labels, crop_marks, color_bars, registration_marks, '
    'negative, flip, interpolate, caption, print_flags')
PrintFlagsInfo = namedtuple(
    'PrintFlagsInfo',
    'version, center_crop_marks, bleed_width_value, bleed_width_scale')
ThumbnailResource = namedtuple(
    'ThumbnailResource',
    'format, width, height, widthbytes, total_size, size, bits, planes, '
    'data')
SlicesResource = namedtuple(
    'SlicesResource', 'descriptor_version, descriptor')
VersionInfo = namedtuple(
    'VersionInfo', 'version, has_real_merged_data, writer_name, '
    'reader_name, file_version')
UrlListItem = namedtuple('UrlListItem', 'number, id, url')
PixelAspectRatio = namedtuple(
    'PixelAspectRatio', 'version aspect')
_ResolutionInfo = namedtuple(
    'ResolutionInfo', 'h_res, h_res_unit, width_unit, v_res, v_res_unit, '
    'height_unit')
LayerComps = namedtuple(
    'LayerComps', 'descriptor_version descriptor')
MeasurementScale = namedtuple(
    'MeasurementScale', 'descriptor_version descriptor')
TimelineInformation = namedtuple(
    'TimelineInformation', 'descriptor_version descriptor')
SheetDisclosure = namedtuple(
    'SheetDisclosure', 'descriptor_version descriptor')
OnionSkins = namedtuple('OnionSkins', 'descriptor_version descriptor')
CountInformation = namedtuple(
    'CountInformation', 'descriptor_version descriptor')
PrintInformation = namedtuple(
    'PrintInformation', 'descriptor_version descriptor')
PrintStyle = namedtuple(
    'PrintStyle', 'descriptor_version descriptor')
PathSelectionState = namedtuple(
    'PathSelectionState', 'descriptor_version descriptor')
GridGuideResource = namedtuple(
    'GridGuideResource', 'version grid_horizontal grid_vertical guides')
GuideResourceBlock = namedtuple(
    'GuideResourceBlock', 'location direction')


class ResolutionInfo(_ResolutionInfo):
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

    decoder = _image_resource_decoders.get(resource.resource_id,
                                           lambda data: data)
    return resource._replace(data=decoder(resource.data))


def _decode_descriptor_resource(data, kls):
    fp = io.BytesIO(data)
    version = read_fmt("I", fp)[0]

    try:
        return kls(version, decode_descriptor(None, fp))
    except UnknownOSType as e:
        warnings.warn("Ignoring image resource %s" % e)
        return data


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
    if version not in [7, 8]:
        warnings.warn("Unsupported slices version %s. "
                      "Only version 7 or 8 slices supported." % version)
        return data

    # TODO: Support version 6.

    return _decode_descriptor_resource(fp.read(-1), SlicesResource)


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
            if field_type[1] in ('A', 'B'):
                exif[key] = str(ifd)
            else:
                exif[key] = int(str(ifd))
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
    return PrintFlags(*(unpack("9?x", data)))


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
    except ImportError:
        warnings.warn(
            "ICC profile is not handled; colors could be incorrect. "
            "Please build PIL or Pillow with littlecms/littlecms2 support.")
        return data

    return ImageCms.ImageCmsProfile(io.BytesIO(data))


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
