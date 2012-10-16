# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

class Enum(object):

    @classmethod
    def _attributes(cls):
        return [name for name in dir(cls) if name.isupper()]

    @classmethod
    def is_known(cls, value):
        for name in cls._attributes():
            if getattr(cls, name) == value:
                return True
        return False

class ColorMode(Enum):
    BITMAP = 0
    GRAYSCALE = 1
    INDEXED = 2
    RGB = 3
    CMYK = 4
    MULTICHANNEL = 7
    DUOTONE = 8
    LAB = 9

class ChannelID(Enum):
    RED = 0
    GREEN = 1
    BLUE = 2
    TRANSPARENCY_MASK = -1
    USER_LAYER_MASK = -2
    REAL_USER_LAYER_MASK = -3

class ImageResourceID(Enum):
    OBSOLETE1 = 1000
    MAC_PRINT_MANAGER_INFO = 1001
    OBSOLETE2 = 1003
    RESOLUTION_INFO = 1005
    ALPHA_NAMES_PASCAL = 1006
    DISPLAY_INFO_OBSOLETE = 1007
    CAPTION_PASCAL = 1008
    BORDER_INFO = 1009
    BACKGROUND_COLOR = 1010
    PRINT_FLAGS = 1011
    GRAYSCALE_HALFTONING_INFO = 1012
    COLOR_HALFTONING_INFO = 1013
    DUOTONE_HALFTONING_INFO = 1014
    GRAYSCALE_TRANSFER_FUNCTION = 1015
    COLOR_TRANSFER_FUNCTION = 1016
    DUOTONE_TRANSFER_FUNCTION = 1017
    DUOTONE_IMAGE_INFO = 1018
    EFFECTIVE_BW = 1019
    OBSOLETE3 = 1020
    EPS_OPTIONS = 1021
    QUICK_MASK_INFO = 1022
    OBSOLETE4 = 1023
    LAYER_STATE_INFO = 1024
    WORKING_PATH = 1025
    LAYER_GROUP_INFO = 1026
    OBSOLETE5 = 1027
    IPTC_NAA = 1028
    IMAGE_MODE_RAW = 1029
    JPEG_QUALITY = 1030
    GRID_AND_GUIDES_INFO = 1032
    THUMBNAIL_RESOURCE_PS4 = 1033
    COPYRIGHT_FLAG = 1034
    URL = 1035
    THUMBNAIL_RESOURCE = 1036
    GLOBAL_ANGLE_OBSOLETE = 1037
    COLOR_SAMPLERS_RESOURCE_OBSOLETE = 1038
    ICC_PROFILE = 1039
    WATERMARK = 1040
    ICC_UNTAGGED_PROFILE = 1041
    EFFECTS_VISIBLE = 1042
    SPOT_HALFTONE = 1043
    IDS_SEED_NUMBER = 1044
    ALPHA_NAMES_UNICODE = 1045
    INDEXED_COLOR_TABLE_COUNT = 1046
    TRANSPARENCY_INDEX = 1047
    GLOBAL_ALTITUDE = 1049
    SLICES = 1050
    WORKFLOW_URL = 1051
    JUMP_TO_XPEP = 1052
    ALPHA_IDENTIFIERS = 1053
    URL_LIST = 1054
    VERSION_INFO = 1057
    EXIF_DATA_1 = 1058
    EXIF_DATA_3 = 1059
    XMP_METADATA = 1060
    CAPTION_DIGEST = 1061
    PRINT_SCALE = 1062
    PIXEL_ASPECT_RATIO = 1064
    LAYER_COMPS = 1065
    ALTERNATE_DUOTONE_COLORS = 1066
    ALTERNATE_SPOT_COLORS = 1067
    LAYER_SELECTION_IDS = 1069
    HDR_TONING_INFO = 1070
    PRINT_INFO_CS2 = 1071
    LAYER_GROUPS_ENABLED_ID = 1072
    COLOR_SAMPLERS_RESOURCE = 1073
    MEASURMENT_SCALE = 1074
    TIMELINE_INFO = 1075
    SHEET_DISCLOSURE = 1076
    DISPLAY_INFO = 1077
    ONION_SKINS = 1078
    COUNT_INFO = 1080
    PRINT_INFO_CS5 = 1082
    PRINT_STYLE = 1083
    MAC_NSPRINTINFO = 1084
    WINDOWS_DEVMODE = 1085
    AUTO_SAVE_FILE_PATH = 1086
    AUTO_SAVE_FORMAT = 1087

    # PATH_INFO = 2000...2997
    PATH_INFO_FIRST = 2000
    PATH_INFO_LAST = 2997
    CLIPPING_PATH_NAME = 2999

    # PLUGIN_RESOURCES = 4000..4999
    PLUGIN_RESOURCES_FIRST = 4000
    PLUGIN_RESOURCES_LAST = 4999

    IMAGE_READY_VARIABLES = 7000
    IMAGE_READY_DATA_SETS = 7001
    LIGHTROOM_WORKFLOW = 8000
    PRINT_FLAGS_INFO = 10000

    @classmethod
    def is_known(cls, value):
        path_info = cls.PATH_INFO_FIRST <= value <= cls.PATH_INFO_LAST
        plugin_resource = cls.PLUGIN_RESOURCES_FIRST <= value <= cls.PLUGIN_RESOURCES_LAST
        return super(ImageResourceID, cls).is_known(value) or path_info or plugin_resource


class BlendMode(Enum):
    PASS_THROUGH = 'pass'
    NORMAL = 'norm'
    DISSOLVE = 'diss'
    DARKEN = 'dark'
    MULTIPLY = 'mul '
    COLOR_BURN = 'idiv'
    LINEAR_BURN = 'lbrn'
    DARKER_COLOR = 'dkCl'
    LIGHTEN = 'lite'
    SCREEN = 'scrn'
    COLOR_DODGE = 'div '
    LINEAR_DODGE = 'lddg'
    LIGHTER_COLOR = 'lgCl'
    OVERLAY = 'over'
    SOFT_LIGHT = 'sLit'
    HARD_LIGHT = 'hLit'
    VIVID_LIGHT = 'vLit'
    LINEAR_LIGHT = 'lLit'
    PIN_LIGHT = 'pLit'
    HARD_MIX = 'hMix'
    DIFFERENCE = 'diff'
    EXCLUSION = 'smud'
    SUBTRACT = 'fsub'
    DIVIDE = 'fdiv'
    HUE = 'hue '
    SATURATION = 'sat '
    COLOR = 'colr'
    LUMINOSITY = 'lum '

class Clipping(Enum):
    BASE = 0
    NON_BASE = 1

class GlobalLayerMaskKind(Enum):
    COLOR_SELECTED = 0
    COLOR_PROTECTED = 1
    PER_LAYER = 128
    # others options are possible in beta versions.

class Compression(Enum):
    RAW = 0
    PACK_BITS = 1
    ZIP = 2
    ZIP_WITH_PREDICTION = 3

class PrintScaleStyle(Enum):
    CENTERED = 0
    SIZE_TO_FIT = 1
    USER_DEFINED = 2
