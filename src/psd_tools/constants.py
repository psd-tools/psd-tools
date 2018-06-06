# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals


class Enum(object):
    """
    Base class for enumeration.
    """

    _attributes_cache = None
    _values_dict_cache = None

    @classmethod
    def _attributes(cls):
        if cls._attributes_cache is None:
            attrs = [name for name in dir(cls)
                     if name.isupper() and not name.startswith('_')]
            cls._attributes_cache = attrs
        return cls._attributes_cache

    @classmethod
    def _values_dict(cls):
        if cls._values_dict_cache is None:
            cls._values_dict_cache = dict([
                (getattr(cls, name), name)
                for name in cls._attributes()
            ])
        return cls._values_dict_cache

    @classmethod
    def is_known(cls, value):
        return value in cls._values_dict()

    @classmethod
    def name_of(cls, value):
        return cls._values_dict().get(value, "<unknown:{}>".format(value))

    @classmethod
    def human_name_of(cls, value, separator="-"):
        return cls.name_of(value).lower().replace("_", separator)


class ColorMode(Enum):
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


class ChannelID(Enum):
    """
    Channel types.
    """
    TRANSPARENCY_MASK = -1
    USER_LAYER_MASK = -2
    REAL_USER_LAYER_MASK = -3


class ImageResourceID(Enum):
    """
    Image resource keys.
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

    # PATH_INFO = 2000...2997
    PATH_INFO_0 = 2000
    PATH_INFO_LAST = 2997
    CLIPPING_PATH_NAME = 2999
    ORIGIN_PATH_INFO = 3000

    # PLUGIN_RESOURCES = 4000..4999
    PLUGIN_RESOURCES_0 = 4000
    PLUGIN_RESOURCES_LAST = 4999

    IMAGE_READY_VARIABLES = 7000
    IMAGE_READY_DATA_SETS = 7001
    LIGHTROOM_WORKFLOW = 8000
    PRINT_FLAGS_INFO = 10000

    @classmethod
    def is_known(cls, value):
        path_info = cls.PATH_INFO_0 <= value <= cls.PATH_INFO_LAST
        plugin_resource = (
            cls.PLUGIN_RESOURCES_0 <= value <= cls.PLUGIN_RESOURCES_LAST
        )
        return (
            super(ImageResourceID, cls).is_known(value) or
            path_info or
            plugin_resource
        )

    @classmethod
    def name_of(cls, value):
        if cls.PATH_INFO_0 < value < cls.PATH_INFO_LAST:
            return "PATH_INFO_%d" % (value - cls.PATH_INFO_0)
        if cls.PLUGIN_RESOURCES_0 < value < cls.PLUGIN_RESOURCES_LAST:
            return "PLUGIN_RESOURCES_%d" % (value - cls.PLUGIN_RESOURCES_0)
        return super(ImageResourceID, cls).name_of(value)


class ColorSpaceID(Enum):
    """
    Color space types.
    """
    RGB = 0
    HSB = 1
    CMYK = 2
    LAB = 7
    GRAYSCALE = 8


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


class BlendMode2(Enum):
    """Blend mode in layer effect descriptor."""
    NORMAL = b'Nrml'
    DISSOLVE = b'Dslv'
    DARKEN = b'Drkn'
    MULTIPLY = b'Mltp'
    COLOR_BURN = b'CBrn'
    LINEAR_BURN = b'linearBurn'
    DARKER_COLOR = b'darkerColor'
    LIGHTEN = b'Lghn'
    SCREEN = b'Scrn'
    COLOR_DODGE = b'CDdg'
    LINEAR_DODGE = b'linearDodge'
    LIGHTER_COLOR = b'lighterColor'
    OVERLAY = b'Ovrl'
    SOFT_LIGHT = b'SftL'
    HARD_LIGHT = b'HrdL'
    VIVID_LIGHT = b'vividLight'
    LINEAR_LIGHT = b'linearLight'
    PIN_LIGHT = b'pinLight'
    HARD_MIX = b'hardMix'
    DIFFERENCE = b'Dfrn'
    EXCLUSION = b'Xclu'
    SUBTRACT = b'blendSubtraction'
    DIVIDE = b'blendDivide'
    HUE = b'H   '
    SATURATION = b'Strt'
    COLOR = b'Clr '
    LUMINOSITY = b'Lmns'


class Clipping(Enum):
    """Clipping."""
    BASE = 0
    NON_BASE = 1


class GlobalLayerMaskKind(Enum):
    """Global layer mask kind."""
    COLOR_SELECTED = 0
    COLOR_PROTECTED = 1
    PER_LAYER = 128
    # others options are possible in beta versions.


class Compression(Enum):
    """Compression modes."""
    RAW = 0
    PACK_BITS = 1
    ZIP = 2
    ZIP_WITH_PREDICTION = 3


class PrintScaleStyle(Enum):
    """Print scale style."""
    CENTERED = 0
    SIZE_TO_FIT = 1
    USER_DEFINED = 2


class TaggedBlock(Enum):
    """Tagged blocks keys."""
    _FILL_KEYS = set([
        b'SoCo', b'GdFl', b'PtFl'
    ])

    _ADJUSTMENT_KEYS = set([
        b'brit', b'levl', b'curv', b'expA', b'vibA', b'hue ', b'hue2',
        b'blnc', b'blwh', b'phfl', b'mixr', b'clrL', b'nvrt', b'post',
        b'thrs', b'grdm', b'selc'
    ])

    SOLID_COLOR_SHEET_SETTING = b'SoCo'
    GRADIENT_FILL_SETTING = b'GdFl'
    PATTERN_FILL_SETTING = b'PtFl'
    BRIGHTNESS_AND_CONTRAST = b'brit'
    LEVELS = b'levl'
    CURVES = b'curv'
    EXPOSURE = b'expA'
    VIBRANCE = b'vibA'
    HUE_SATURATION_V4 = b'hue '
    HUE_SATURATION = b'hue2'
    COLOR_BALANCE = b'blnc'
    BLACK_AND_WHITE = b'blwh'
    PHOTO_FILTER = b'phfl'
    CHANNEL_MIXER = b'mixr'
    COLOR_LOOKUP = b'clrL'
    INVERT = b'nvrt'
    POSTERIZE = b'post'
    THRESHOLD = b'thrs'
    GRADIENT_MAP_SETTING = b'grdm'
    SELECTIVE_COLOR = b'selc'

    @classmethod
    def is_adjustment_key(cls, key):
        return key in cls._ADJUSTMENT_KEYS

    @classmethod
    def is_fill_key(cls, key):
        return key in cls._FILL_KEYS

    EFFECTS_LAYER = b'lrFX'
    TYPE_TOOL_INFO = b'tySh'
    UNICODE_LAYER_NAME = b'luni'
    LAYER_ID = b'lyid'
    OBJECT_BASED_EFFECTS_LAYER_INFO_V0 = b'lmfx'  # Undocumented.
    OBJECT_BASED_EFFECTS_LAYER_INFO_V1 = b'lfxs'  # Undocumented.
    OBJECT_BASED_EFFECTS_LAYER_INFO = b'lfx2'

    PATTERNS1 = b'Patt'
    PATTERNS2 = b'Pat2'
    PATTERNS3 = b'Pat3'

    ANNOTATIONS = b'Anno'
    BLEND_CLIPPING_ELEMENTS = b'clbl'
    BLEND_INTERIOR_ELEMENTS = b'infx'
    BLEND_FILL_OPACITY = b'iOpa'  # Undocumented.

    KNOCKOUT_SETTING = b'knko'
    PROTECTED_SETTING = b'lspf'
    SHEET_COLOR_SETTING = b'lclr'
    REFERENCE_POINT = b'fxrp'
    SECTION_DIVIDER_SETTING = b'lsct'
    NESTED_SECTION_DIVIDER_SETTING = b'lsdk'
    CHANNEL_BLENDING_RESTRICTIONS_SETTING = b'brst'
    VECTOR_MASK_SETTING1 = b'vmsk'
    VECTOR_MASK_SETTING2 = b'vsms'
    TYPE_TOOL_OBJECT_SETTING = b'TySh'
    FOREIGN_EFFECT_ID = b'ffxi'
    LAYER_NAME_SOURCE_SETTING = b'lnsr'
    PATTERN_DATA = b'shpa'
    METADATA_SETTING = b'shmd'
    LAYER_VERSION = b'lyvr'
    TRANSPARENCY_SHAPES_LAYER = b'tsly'
    LAYER_MASK_AS_GLOBAL_MASK = b'lmgm'
    VECTOR_MASK_AS_GLOBAL_MASK = b'vmgm'
    VECTOR_ORIGINATION_DATA = b'vogk'
    PIXEL_SOURCE_DATA1 = b'PxSc'
    PIXEL_SOURCE_DATA2 = b'PxSD'
    ARTBOARD_DATA1 = b'artb'
    ARTBOARD_DATA2 = b'artd'
    ARTBOARD_DATA3 = b'abdd'

    PLACED_LAYER_OBSOLETE1 = b'plLd'
    PLACED_LAYER_OBSOLETE2 = b'PlLd'

    LINKED_LAYER1 = b'lnkD'
    LINKED_LAYER2 = b'lnk2'
    LINKED_LAYER3 = b'lnk3'
    LINKED_LAYER_EXTERNAL = b'lnkE'
    CONTENT_GENERATOR_EXTRA_DATA = b'CgEd'
    TEXT_ENGINE_DATA = b'Txt2'
    UNICODE_PATH_NAME = b'pths'
    ANIMATION_EFFECTS = b'anFX'
    FILTER_MASK = b'FMsk'
    PLACED_LAYER_DATA = b'SoLd'
    SMART_OBJECT_PLACED_LAYER_DATA = b'SoLE'
    EXPORT_SETTING1 = b'extd'  # Undocumented.
    EXPORT_SETTING2 = b'extn'  # Undocumented.

    VECTOR_STROKE_DATA = b'vstk'
    VECTOR_STROKE_CONTENT_DATA = b'vscg'
    USING_ALIGNED_RENDERING = b'sn2P'
    SAVING_MERGED_TRANSPARENCY = b'Mtrn'
    SAVING_MERGED_TRANSPARENCY16 = b'Mt16'
    SAVING_MERGED_TRANSPARENCY32 = b'Mt32'
    USER_MASK = b'LMsk'
    FILTER_EFFECTS1 = b'FXid'
    FILTER_EFFECTS2 = b'FEid'
    FILTER_EFFECTS3 = b'FELS'  # Undocumented.

    LAYER_16 = b'Lr16'
    LAYER_32 = b'Lr32'
    LAYER = b'Layr'


class OSType(Enum):
    """
    Action descriptor types.
    """
    REFERENCE = b'obj '
    DESCRIPTOR = b'Objc'
    LIST = b'VlLs'
    DOUBLE = b'doub'
    UNIT_FLOAT = b'UntF'
    UNIT_FLOATS = b'UnFl'
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
    OBJECT_ARRAY = b'ObAr'
    PATH = b'Pth '  # Undocumented


class ReferenceOSType(Enum):
    """
    OS Type keys for Reference Structure.
    """
    PROPERTY = b'prop'
    CLASS = b'Clss'
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


class UnitFloatType(Enum):
    """
    Units the value is in (used in Unit float structure).
    """
    ANGLE = b'#Ang'  # base degrees
    DENSITY = b'#Rsl'  # base per inch
    DISTANCE = b'#Rlt'  # base 72ppi
    NONE = b'#Nne'  # coerced
    PERCENT = b'#Prc'  # unit value
    PIXELS = b'#Pxl'  # tagged unit value
    POINTS = b'#Pnt'  # points
    MILLIMETERS = b'#Mlm'  # millimeters


class SectionDivider(Enum):
    OTHER = 0
    OPEN_FOLDER = 1
    CLOSED_FOLDER = 2
    BOUNDING_SECTION_DIVIDER = 3


class DisplayResolutionUnit(Enum):
    PIXELS_PER_INCH = 1
    PIXELS_PER_CM = 2


class DimensionUnit(Enum):
    INCH = 1
    CM = 2
    POINT = 3  # 72 points == 1 inch
    PICA = 4   # 6 pica == 1 inch
    COLUMN = 5


class PlacedLayerProperty(Enum):
    TRANSFORM = b'Trnf'
    SIZE = b'Sz  '
    ID = b'Idnt'


class SzProperty(Enum):
    WIDTH = b'Wdth'
    HEIGHT = b'Hght'


class TextProperty(Enum):
    TXT = b'Txt '
    ORIENTATION = b'Ornt'


class TextOrientation(Enum):
    HORIZONTAL = b'Hrzn'


class PathResource(Enum):
    CLOSED_SUBPATH_LENGTH_RECORD = 0
    CLOSED_SUBPATH_BEZIER_KNOT_LINKED = 1
    CLOSED_SUBPATH_BEZIER_KNOT_UNLINKED = 2
    OPEN_SUBPATH_LENGTH_RECORD = 3
    OPEN_SUBPATH_BEZIER_KNOT_LINKED = 4
    OPEN_SUBPATH_BEZIER_KNOT_UNLINKED = 5
    PATH_FILL_RULE_RECORD = 6
    CLIPBOARD_RECORD = 7
    INITIAL_FILL_RULE_RECORD = 8


class LinkedLayerType(Enum):
    DATA = b'liFD'
    EXTERNAL = b'liFE'
    ALIAS = b'liFA'


class ObjectBasedEffects(Enum):
    """Type of the object-based effects."""
    DROP_SHADOW_MULTI = b'dropShadowMulti'
    DROP_SHADOW = b'DrSh'
    INNER_SHADOW_MULTI = b'innerShadowMulti'
    INNER_SHADOW = b'IrSh'
    OUTER_GLOW = b'OrGl'
    COLOR_OVERLAY_MULTI = b'solidFillMulti'
    COLOR_OVERLAY = b'SoFi'
    GRADIENT_OVERLAY_MULTI = b'gradientFillMulti'
    GRADIENT_OVERLAY = b'GrFl'
    PATTERN_OVERLAY = b'patternFill'
    STROKE_MULTI = b'frameFXMulti'
    STROKE = b'FrFX'
    INNER_GLOW = b'IrGl'
    BEVEL_EMBOSS = b'ebbl'
    SATIN = b'ChFX'
