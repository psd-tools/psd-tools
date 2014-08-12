# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, division
import io
import warnings
import collections

from psd_tools.utils import (read_pascal_string, unpack, read_fmt,
                             read_unicode_string, be_array_from_bytes,
                             decode_fixed_point_32bit)
from psd_tools.constants import ImageResourceID, PrintScaleStyle, DisplayResolutionUnit, DimensionUnit
from psd_tools.decoder import decoders
from psd_tools.decoder.actions import decode_descriptor, UnknownOSType
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
    ImageResourceID.WORKFLOW_URL:               decoders.unicode_string
})

PrintScale = collections.namedtuple('PrintScale', 'style, x, y, scale')
PrintFlags = collections.namedtuple('PrintFlags', 'labels, crop_marks, color_bars, registration_marks, negative, flip, interpolate, caption, print_flags')
PrintFlagsInfo = collections.namedtuple('PrintFlagsInfo', 'version, center_crop_marks, bleed_width_value, bleed_width_scale')
VersionInfo = collections.namedtuple('VersionInfo', 'version, has_real_merged_data, writer_name, reader_name, file_version')
PixelAspectRatio = collections.namedtuple('PixelAspectRatio', 'version aspect')
_ResolutionInfo = collections.namedtuple('ResolutionInfo', 'h_res, h_res_unit, width_unit, v_res, v_res_unit, height_unit')
PathSelectionState = collections.namedtuple('PathSelectionState', 'descriptor_version descriptor')
LayerComps = collections.namedtuple('LayerComps', 'descriptor_version descriptor')


class ResolutionInfo(_ResolutionInfo):
    def __repr__(self):

        return "ResolutionInfo(h_res=%s, h_res_unit=%s, v_res=%s, v_res_unit=%s, width_unit=%s, height_unit=%s)" % (
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

    decoder = _image_resource_decoders.get(resource.resource_id, lambda data: data)
    return resource._replace(data = decoder(resource.data))

@register(ImageResourceID.LAYER_GROUP_INFO)
def _decode_layer_group_info(data):
    return be_array_from_bytes("H", data)

@register(ImageResourceID.LAYER_SELECTION_IDS)
def _decode_layer_selection(data):
    return be_array_from_bytes("I", data[2:])

@register(ImageResourceID.LAYER_GROUPS_ENABLED_ID)
def _decode_layer_groups_enabled_id(data):
    return be_array_from_bytes("B", data)

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
    h_res, h_res_unit, width_unit, v_res, v_res_unit, height_unit = unpack("4s HH 4s HH", data)

    h_res = decode_fixed_point_32bit(h_res)
    v_res = decode_fixed_point_32bit(v_res)

    return ResolutionInfo(h_res, h_res_unit, width_unit, v_res, v_res_unit, height_unit)

@register(ImageResourceID.ICC_PROFILE)
def _decode_icc(data):
    try:
        from PIL import ImageCms
    except ImportError:
        warnings.warn("ICC profile is not handled; colors could be incorrect. "
                      "Please build PIL or Pillow with littlecms/littlecms2 "
                      "support.")
        return data

    return ImageCms.ImageCmsProfile(io.BytesIO(data))

@register(ImageResourceID.BACKGROUND_COLOR)
def _decode_background_color(data):
    fp = io.BytesIO(data)
    return decode_color(fp)

@register(ImageResourceID.PATH_SELECTION_STATE)
def _decode_path_selection_state(data):
    fp = io.BytesIO(data)
    version = read_fmt("I", fp)[0]

    try:
        return PathSelectionState(version, decode_descriptor(None, fp))
    except UnknownOSType as e:
        warnings.warn("Ignoring image resource %s" % e)
        return data

@register(ImageResourceID.LAYER_COMPS)
def _decode_layer_comps(data):
    fp = io.BytesIO(data)
    version = read_fmt("I", fp)[0]

    try:
        return LayerComps(version, decode_descriptor(None, fp))
    except UnknownOSType as e:
        warnings.warn("Ignoring image resource %s" % e)
        return data
