"""
Various constants for psd_tools
"""
from enum import Enum, IntEnum


class ColorMode(IntEnum):
    """
    Color mode.
    """
    BITMAP = 0
    GRAYSCALE = 1
    INDEXED = 2
    RGB = 3
    CMYK = 4
    MULTICHANNEL = 7
    DUOTONE = 8
    LAB = 9

    @staticmethod
    def channels(value, alpha=False):
        return {
            ColorMode.BITMAP: 1,
            ColorMode.GRAYSCALE: 1,
            ColorMode.INDEXED: 1,
            ColorMode.RGB: 3,
            ColorMode.CMYK: 4,
            ColorMode.MULTICHANNEL: 3,
            ColorMode.DUOTONE: 1,
            ColorMode.LAB: 3,
        }.get(value) + alpha


class ColorSpaceID(IntEnum):
    """
    Color space types.
    """
    RGB = 0
    HSB = 1
    CMYK = 2
    LAB = 7
    GRAYSCALE = 8


class ImageResourceID(IntEnum):
    """
    Image resource keys.

    Note the following is not defined for performance reasons.

     * PATH_INFO_10 to PATH_INFO_989 corresponding to 2010 - 2989
     * PLUGIN_RESOURCES_10 to PLUGIN_RESOURCES_989 corresponding to
        4010 - 4989
    """
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
    GLOBAL_ANGLE = 1037
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
    MEASUREMENT_SCALE = 1074
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
    PATH_SELECTION_STATE = 1088
    PATH_INFO_0 = 2000
    PATH_INFO_1 = 2001
    PATH_INFO_2 = 2002
    PATH_INFO_3 = 2003
    PATH_INFO_4 = 2004
    PATH_INFO_5 = 2005
    PATH_INFO_6 = 2006
    PATH_INFO_7 = 2007
    PATH_INFO_8 = 2008
    PATH_INFO_9 = 2009
    # PATH_INFO 2010-2989 is not defined for performance reasons.
    PATH_INFO_990 = 2990
    PATH_INFO_991 = 2991
    PATH_INFO_992 = 2992
    PATH_INFO_993 = 2993
    PATH_INFO_994 = 2994
    PATH_INFO_995 = 2995
    PATH_INFO_996 = 2996
    PATH_INFO_997 = 2997
    CLIPPING_PATH_NAME = 2999
    ORIGIN_PATH_INFO = 3000
    PLUGIN_RESOURCE_0 = 4000
    PLUGIN_RESOURCE_1 = 4001
    PLUGIN_RESOURCE_2 = 4002
    PLUGIN_RESOURCE_3 = 4003
    PLUGIN_RESOURCE_4 = 4004
    PLUGIN_RESOURCE_5 = 4005
    PLUGIN_RESOURCE_6 = 4006
    PLUGIN_RESOURCE_7 = 4007
    PLUGIN_RESOURCE_8 = 4008
    PLUGIN_RESOURCE_9 = 4009
    # PLUGIN_RESOURCE 4010-4989 is not defined for performance reasons.
    PLUGIN_RESOURCE_4990 = 4990
    PLUGIN_RESOURCE_4991 = 4991
    PLUGIN_RESOURCE_4992 = 4992
    PLUGIN_RESOURCE_4993 = 4993
    PLUGIN_RESOURCE_4994 = 4994
    PLUGIN_RESOURCE_4995 = 4995
    PLUGIN_RESOURCE_4996 = 4996
    PLUGIN_RESOURCE_4997 = 4997
    PLUGIN_RESOURCE_4998 = 4998
    PLUGIN_RESOURCE_4999 = 4990
    IMAGE_READY_VARIABLES = 7000
    IMAGE_READY_DATA_SETS = 7001
    LIGHTROOM_WORKFLOW = 8000
    PRINT_FLAGS_INFO = 10000

    @staticmethod
    def is_path_info(value):
        return 2000 <= value and value <= 2997

    @staticmethod
    def is_plugin_resource(value):
        return 4000 <= value and value <= 4999


class LinkedLayerType(Enum):
    """
    Linked layer types.
    """
    DATA = b'liFD'
    EXTERNAL = b'liFE'
    ALIAS = b'liFA'


class ChannelID(IntEnum):
    """
    Channel types.
    """
    CHANNEL_0 = 0  # Red, Cyan, Gray, ...
    CHANNEL_1 = 1  # Green, Magenta, ...
    CHANNEL_2 = 2  # Blue, Yellow, ...
    CHANNEL_3 = 3  # Black, ...
    CHANNEL_4 = 4
    CHANNEL_5 = 5
    CHANNEL_6 = 6
    CHANNEL_7 = 7
    CHANNEL_8 = 8
    CHANNEL_9 = 9
    TRANSPARENCY_MASK = -1
    USER_LAYER_MASK = -2
    REAL_USER_LAYER_MASK = -3


class Clipping(IntEnum):
    """Clipping."""
    BASE = 0
    NON_BASE = 1


class BlendMode(Enum):
    """
    Blend modes.
    """
    PASS_THROUGH = b'pass'
    NORMAL = b'norm'
    DISSOLVE = b'diss'
    DARKEN = b'dark'
    MULTIPLY = b'mul '
    COLOR_BURN = b'idiv'
    LINEAR_BURN = b'lbrn'
    DARKER_COLOR = b'dkCl'
    LIGHTEN = b'lite'
    SCREEN = b'scrn'
    COLOR_DODGE = b'div '
    LINEAR_DODGE = b'lddg'
    LIGHTER_COLOR = b'lgCl'
    OVERLAY = b'over'
    SOFT_LIGHT = b'sLit'
    HARD_LIGHT = b'hLit'
    VIVID_LIGHT = b'vLit'
    LINEAR_LIGHT = b'lLit'
    PIN_LIGHT = b'pLit'
    HARD_MIX = b'hMix'
    DIFFERENCE = b'diff'
    EXCLUSION = b'smud'
    SUBTRACT = b'fsub'
    DIVIDE = b'fdiv'
    HUE = b'hue '
    SATURATION = b'sat '
    COLOR = b'colr'
    LUMINOSITY = b'lum '


class GlobalLayerMaskKind(IntEnum):
    """Global layer mask kind."""
    COLOR_SELECTED = 0
    COLOR_PROTECTED = 1
    PER_LAYER = 128
    # others options are possible in beta versions.


class Compression(IntEnum):
    """
    Compression modes.

    Compression. 0 = Raw Data, 1 = RLE compressed, 2 = ZIP without prediction,
    3 = ZIP with prediction.
    """
    RAW = 0
    PACK_BITS = 1
    ZIP = 2
    ZIP_WITH_PREDICTION = 3


class TaggedBlockID(Enum):
    """Tagged blocks keys."""
    ALPHA = b'Alph'  # Undocumented.
    ANIMATION_EFFECTS = b'anFX'
    ANNOTATIONS = b'Anno'
    ARTBOARD_DATA1 = b'artb'
    ARTBOARD_DATA2 = b'artd'
    ARTBOARD_DATA3 = b'abdd'
    BLACK_AND_WHITE = b'blwh'
    BLEND_CLIPPING_ELEMENTS = b'clbl'
    BLEND_FILL_OPACITY = b'iOpa'  # Undocumented.
    BLEND_INTERIOR_ELEMENTS = b'infx'
    BRIGHTNESS_AND_CONTRAST = b'brit'
    CHANNEL_BLENDING_RESTRICTIONS_SETTING = b'brst'
    CHANNEL_MIXER = b'mixr'
    COLOR_BALANCE = b'blnc'
    COLOR_LOOKUP = b'clrL'
    COMPUTER_INFO = b'cinf'  # Undocumented.
    CONTENT_GENERATOR_EXTRA_DATA = b'CgEd'
    CURVES = b'curv'
    EFFECTS_LAYER = b'lrFX'
    EXPORT_SETTING1 = b'extd'  # Undocumented.
    EXPORT_SETTING2 = b'extn'  # Undocumented.
    EXPOSURE = b'expA'
    FILTER_EFFECTS1 = b'FXid'
    FILTER_EFFECTS2 = b'FEid'
    FILTER_EFFECTS3 = b'FELS'  # Undocumented.
    FILTER_MASK = b'FMsk'
    FOREIGN_EFFECT_ID = b'ffxi'
    GRADIENT_FILL_SETTING = b'GdFl'
    GRADIENT_MAP = b'grdm'
    HUE_SATURATION = b'hue2'
    HUE_SATURATION_V4 = b'hue '
    INVERT = b'nvrt'
    KNOCKOUT_SETTING = b'knko'
    LAYER = b'Layr'
    LAYER_16 = b'Lr16'
    LAYER_32 = b'Lr32'
    LAYER_ID = b'lyid'
    LAYER_MASK_AS_GLOBAL_MASK = b'lmgm'
    LAYER_NAME_SOURCE_SETTING = b'lnsr'
    LAYER_VERSION = b'lyvr'
    LEVELS = b'levl'
    LINKED_LAYER1 = b'lnkD'
    LINKED_LAYER2 = b'lnk2'
    LINKED_LAYER3 = b'lnk3'
    LINKED_LAYER_EXTERNAL = b'lnkE'
    METADATA_SETTING = b'shmd'
    NESTED_SECTION_DIVIDER_SETTING = b'lsdk'
    OBJECT_BASED_EFFECTS_LAYER_INFO = b'lfx2'
    OBJECT_BASED_EFFECTS_LAYER_INFO_V0 = b'lmfx'  # Undocumented.
    OBJECT_BASED_EFFECTS_LAYER_INFO_V1 = b'lfxs'  # Undocumented.
    PATTERNS1 = b'Patt'
    PATTERNS2 = b'Pat2'
    PATTERNS3 = b'Pat3'
    PATTERN_DATA = b'shpa'
    PATTERN_FILL_SETTING = b'PtFl'
    PHOTO_FILTER = b'phfl'
    PIXEL_SOURCE_DATA1 = b'PxSc'
    PIXEL_SOURCE_DATA2 = b'PxSD'
    PLACED_LAYER1 = b'plLd'
    PLACED_LAYER2 = b'PlLd'
    POSTERIZE = b'post'
    PROTECTED_SETTING = b'lspf'
    REFERENCE_POINT = b'fxrp'
    SAVING_MERGED_TRANSPARENCY = b'Mtrn'
    SAVING_MERGED_TRANSPARENCY16 = b'Mt16'
    SAVING_MERGED_TRANSPARENCY32 = b'Mt32'
    SECTION_DIVIDER_SETTING = b'lsct'
    SELECTIVE_COLOR = b'selc'
    SHEET_COLOR_SETTING = b'lclr'
    SMART_OBJECT_LAYER_DATA1 = b'SoLd'
    SMART_OBJECT_LAYER_DATA2 = b'SoLE'
    SOLID_COLOR_SHEET_SETTING = b'SoCo'
    TEXT_ENGINE_DATA = b'Txt2'
    THRESHOLD = b'thrs'
    TRANSPARENCY_SHAPES_LAYER = b'tsly'
    TYPE_TOOL_INFO = b'tySh'
    TYPE_TOOL_OBJECT_SETTING = b'TySh'
    UNICODE_LAYER_NAME = b'luni'
    UNICODE_PATH_NAME = b'pths'
    USER_MASK = b'LMsk'
    USING_ALIGNED_RENDERING = b'sn2P'
    VECTOR_MASK_AS_GLOBAL_MASK = b'vmgm'
    VECTOR_MASK_SETTING1 = b'vmsk'
    VECTOR_MASK_SETTING2 = b'vsms'
    VECTOR_ORIGINATION_DATA = b'vogk'
    VECTOR_STROKE_DATA = b'vstk'
    VECTOR_STROKE_CONTENT_DATA = b'vscg'
    VIBRANCE = b'vibA'


class PrintScaleStyle(IntEnum):
    """Print scale style."""
    CENTERED = 0
    SIZE_TO_FIT = 1
    USER_DEFINED = 2


class OSType(Enum):
    """
    Descriptor OSTypes and reference OSTypes.
    """

    # OS types
    REFERENCE = b'obj '
    DESCRIPTOR = b'Objc'
    LIST = b'VlLs'
    DOUBLE = b'doub'
    UNIT_FLOAT = b'UntF'
    UNIT_FLOATS = b'UnFl'  # Undocumented
    STRING = b'TEXT'
    ENUMERATED = b'enum'
    INTEGER = b'long'
    LARGE_INTEGER = b'comp'
    BOOLEAN = b'bool'
    GLOBAL_OBJECT = b'GlbO'
    CLASS1 = b'type'
    CLASS2 = b'GlbC'
    ALIAS = b'alis'
    RAW_DATA = b'tdta'
    OBJECT_ARRAY = b'ObAr'  # Undocumented
    PATH = b'Pth '  # Undocumented

    # Reference OS types
    PROPERTY = b'prop'
    CLASS3 = b'Clss'
    ENUMERATED_REFERENCE = b'Enmr'
    OFFSET = b'rele'
    IDENTIFIER = b'Idnt'
    INDEX = b'indx'
    NAME = b'name'


class EffectOSType(Enum):
    """
    OS Type keys for Layer Effects.
    """
    COMMON_STATE = b'cmnS'
    DROP_SHADOW = b'dsdw'
    INNER_SHADOW = b'isdw'
    OUTER_GLOW = b'oglw'
    INNER_GLOW = b'iglw'
    BEVEL = b'bevl'
    SOLID_FILL = b'sofi'


class PathResourceID(IntEnum):
    CLOSED_LENGTH = 0
    CLOSED_KNOT_LINKED = 1
    CLOSED_KNOT_UNLINKED = 2
    OPEN_LENGTH = 3
    OPEN_KNOT_LINKED = 4
    OPEN_KNOT_UNLINKED = 5
    PATH_FILL = 6
    CLIPBOARD = 7
    INITIAL_FILL = 8


class PlacedLayerType(IntEnum):
    UNKNOWN = 0
    VECTOR = 1
    RASTER = 2
    IMAGE_STACK = 3


class SectionDivider(IntEnum):
    OTHER = 0
    OPEN_FOLDER = 1
    CLOSED_FOLDER = 2
    BOUNDING_SECTION_DIVIDER = 3


class SheetColorType(IntEnum):
    NO_COLOR = 0
    RED = 1
    ORANGE = 2
    YELLOW = 3
    GREEN = 4
    BLUE = 5
    VIOLET = 6
    GRAY = 7
