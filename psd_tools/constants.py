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


class DescriptorClassID(Enum):
    """
    Descriptor classID.
    """
    NULL = b'null'
    NAME = b'Nm  '
    IDENTIFIER = b'Idnt'
    VERSION = b'Vrsn'

    ALIAS = b'alis'

    SHAPE = b'ShpC'
    CURVE = b'Crv '
    TOP = b'Top '
    LEFT = b'Left'
    BOTTOM = b'Btom'
    RIGHT = b'Rght'

    CNT = b'Cnt '  # ???
    POINT = b'Pnt '
    CONTROL_POINT = b'CrPt'
    HORIZONTAL = b'Hrzn'
    VERTICAL = b'Vrtc'

    COLOR = b'Clr '
    RGB = b'RGBC'
    GRAYSCALE = b'Grsc'
    CMYK = b'CMYC'

    RED = b'Rd  '
    GREEN = b'Grn '
    BLUE = b'Bl  '
    GRAY = b'Gry '
    CYAN = b'Cyn '
    MAGENTA = b'Mgnt'
    YELLOW = b'Yllw'

    PATTERN = b'Ptrn'

    # Gradient configuration
    GRADIENT = b'Grdn'
    TYPE = b'Type'
    CLRY = b'Clry'  # Color picker?
    USRS = b'UsrS'  # User setting?
    LOCATION = b'Lctn'
    MID_POINT = b'Mdpn'
    OPACITY = b'Opct'
    STOP_COLOR = b'Clrt'
    STOP_OPACITY = b'TrnS'

    LINEAR = b'Lnr '
    GRADIENT_RADIAL = b'Rdl '
    GRADIENT_REFLECTED = b'Rflc'
    GRADIENT_DIAMOND = b'DMND'
    COLORS = b'Clrs'
    INTERPOLATION = b'Intr'
    TRANSPARENCY = b'Trns'

    GRADIENT_CONFIG = b'Grad'
    GRADIENT_TYPE = b'GrdT'

    GRADIENT_TYPE_VALUE = b'GrdF'
    GRADIENT_TYPE_SOLID = b'CstS'

    # Noise gradient
    SH_TRANSPARENCY = b'ShTr'
    RESTRICT_COLORS = b'VctC'
    RANDOM_SEED = b'RndS'
    SMOOTHNESS = b'Smth'
    MINIMUM = b'Mnm '
    MAXIMUM = b'Mxm '

    # BrightnessContrast adjustment
    BC_BRIGHTNESS = b'Brgh'
    BC_CONTRAST = b'Cntr'
    BC_LAB = b'Lab '
    BC_AUTO = b'Auto'

    # Vibrance adjustment
    SATURATION = b'Strt'

    ENABLED = b'enab'
    ANGLE = b'Angl'
    MODE = b'Md  '
    CHOKE = b'Ckmt'
    BLUR = b'blur'
    NOISE = b'Nose'
    ANTI_ALIASED = b'AntA'
    DITHERED = b'Dthr'

    LAYER_I = b'LyrI'  # ???
    OFFSET = b'Ofst'
    LAYER_FONT_EFFECT = b'Lefx'  # ???
    SCALE = b'Scl '
    # LAYER_EFFECT = b'FrFX'
    FSTL = b'FStl'  # ???

    FR_FILL = b'FrFl'  # ???
    SOLID_COLOR = b'SClr'

    # Stroke
    STROKE_STYLE = b'Styl'
    STROKE_INNER = b'InsF'
    STROKE_OUTER = b'OutF'
    STROKE_CENTER = b'CtrF'
    FILL_TYPE = b'PntT'

    REVERSED = b'Rvrs'
    ALIGNED = b'Algn'

    # Blend mode
    BLEND_MODE = b'BlnM'
    BLEND_NORMAL = b'Nrml'
    BLEND_DISSOLVE = b'Dslv'
    BLEND_DARKEN = b'Drkn'
    BLEND_MULTIPLY = b'Mltp'
    BLEND_COLOR_BURN = b'CBrn'
    BLEND_LINEAR_BURN = b'linearBurn'
    BLEND_DARKER_COLOR = b'darkerColor'
    BLEND_LIGHTEN = b'Lghn'
    BLEND_SCREEN = b'Scrn'
    BLEND_COLOR_DODGE = b'CDdg'
    BLEND_LINEAR_DODGE = b'linearDodge'
    BLEND_LIGHTER_COLOR = b'lighterColor'
    BLEND_OVERLAY = b'Ovrl'
    BLEND_SOFT_LIGHT = b'SftL'
    BLEND_HARD_LIGHT = b'HrdL'
    BLEND_VIVID_LIGHT = b'vividLight'
    BLEND_LINEAR_LIGHT = b'linearLight'
    BLEND_PIN_LIGHT = b'pinLight'
    BLEND_HARD_MIX = b'hardMix'
    BLEND_DIFFERENCE = b'Dfrn'
    BLEND_EXCLUSION = b'Xclu'
    BLEND_SUBTRACT = b'blendSubtraction'
    BLEND_DIVIDE = b'blendDivide'
    BLEND_HUE = b'H   '
    BLEND_SATURATION = b'Strt'
    BLEND_COLOR = b'Clr '
    BLEND_LUMINOSITY = b'Lmns'

    DISTANCE = b'Dstn'
    SIZE = b'Sz  '

    # Effect types
    DROP_SHADOW = b'DrSh'
    INNER_SHADOW = b'IrSh'
    OUTER_GLOW = b'OrGl'
    COLOR_OVERLAY = b'SoFi'
    GRADIENT_OVERLAY = b'GrFl'
    STROKE = b'FrFX'
    INNER_GLOW = b'IrGl'
    BEVEL_EMBOSS = b'ebbl'
    SATIN = b'ChFX'

    USE_GLOBAL_LIGHT = b'uglg'

    # Grow
    GLOW_TYPE = b'GlwT'
    GLOW_SOURCE = b'glwS'

    GLOW_SOURCE_TYPE = b'IGSr'
    GLOW_SOURCE_EDGE = b'SrcE'
    GLOW_SOURCE_CENTER = b'SrcC'

    INVERTED = b'Invr'
    QUARYTY_RANGE = b'Inpr'
    QUALITY_JITTER = b'ShdN'

    # BevelEmboss
    BEVEL_TYPE = b'bvlT'
    BEVEL_SMOOTH = b'SfBL'
    BEVEL_CHIESEL_HARD = b'PrBL'
    BEVEL_CHIESEL_SOFT = b'Slmt'

    BEVEL_STYLE = b'bvlS'
    BEVEL_STYLE_TYPE = b'BESl'
    BEVEL_STYLE_OUTER = b'OtrB'
    BEVEL_STYLE_INNER = b'InrB'
    BEVEL_STYLE_EMBOSS = b'Embs'
    BEVEL_STYLE_PILLOW_EMBOSS = b'PlEb'
    # BEVEL_STROKE_EMBOSS = b'strokeEmboss'

    BEVEL_DIRECTION = b'bvlD'
    BEVEL_DIRECTION_TYPE = b'BESs'  # ???
    IN = b'In  '
    OUT = b'Out '

    GLOW_TYPE_VALUE = b'BETE'  # ???

    HIGHLIGHT_MODE = b'hglM'
    HIGHLIGHT_COLOR = b'hglC'
    HIGHLIGHT_OPACITY = b'hglO'

    SHADOW_MODE = b'sdwM'
    SHADOW_COLOR = b'sdwC'
    SHADOW_OPACITY = b'sdwO'

    ALTITUDE = b'Lald'
    DEPTH = b'srgR'
    SOFTEN = b'Sftn'

    # Satin
    LIGHT_ANGLE = b'lagl'
    SATIN_CONTOUR = b'MpgS'

    # Text property
    TEXT_LAYER = b'TxLr'
    TEXT = b'Txt '
    NONE = b'None'
    ORIENTATION = b'Ornt'
    NOISE_GRADIENT = b'ClNs'
    COLORS2 = b'ClrS'

    # Smart object
    PAGE_NUMBER = b'PgNm'
    TRANSFORM = b'Trnf'
    RECTANGLE = b'Rctn'
    CROP = b'Crop'
    WIDTH = b'Wdth'
    HEIGHT = b'Hght'
    RESOLUTION = b'Rslt'
    COMP = b'comp'

    ANTI_ALIASE = b'Annt'  # ???

    ANCR = b'AnCr'
    ANSM = b'AnSm'
    ANST = b'AnSt'
    name = b'name'
    Rnd  = b'Rnd '
    FrgC = b'FrgC'
    BckC = b'BckC'
    Fltr = b'Fltr'
    UnsM = b'UnsM'
    Amnt = b'Amnt'
    Rds  = b'Rds '
    Thsh = b'Thsh'
    X    = b'X   '
    Y    = b'Y   '
    Z    = b'Z   '
    VrsM = b'VrsM'
    VrsN = b'VrsN'
    VrsF = b'VrsF'
    GamR = b'GamR'
    GamG = b'GamG'
    GamB = b'GamB'
    Glnr = b'Glnr'
    Glbi = b'Glbi'
    Gunt = b'Gunt'
    Gast = b'Gast'
    Gfrm = b'Gfrm'
    Gfps = b'Gfps'
    rrwp = b'rrwp'
    rrmu = b'rrmu'
    mhtp = b'mhtp'
    Flip = b'Flip'
    GRNm = b'GRNm'
    lite = b'lite'
    hots = b'hots'
    FlOf = b'FlOf'
    shdw = b'shdw'
    attn = b'attn'
    attt = b'attt'
    atta = b'atta'
    attb = b'attb'
    attc = b'attc'
    orad = b'orad'
    irad = b'irad'
    mult = b'mult'
    ison = b'ison'
    ssml = b'ssml'
    afon = b'afon'
    afpw = b'afpw'
    tarx = b'tarx'
    tary = b'tary'
    tarz = b'tarz'
    caml = b'caml'
    camc = b'camc'
    bank = b'bank'
    Lns  = b'Lns '
    orth = b'orth'
    aspr = b'aspr'
    zmfc = b'zmfc'
    mshl = b'mshl'
    msho = b'msho'
    verl = b'verl'
    nrml = b'nrml'
    uvl  = b'uvl '
    faci = b'faci'
    plyc = b'plyc'
    Mtrx = b'Mtrx'
    flag = b'flag'
    hidn = b'hidn'
    hmat = b'hmat'
    hsmt = b'hsmt'
    misv = b'misv'
    misc = b'misc'
    miss = b'miss'
    misi = b'misi'
    Grup = b'Grup'
    OrgH = b'OrgH'
    tRiD = b'tRiD'
    Ang1 = b'Ang1'
    Ang2 = b'Ang2'
    FTcs = b'FTcs'
    QCSt = b'QCSt'
    QCsa = b'QCsa'
    Qlty = b'Qlty'
    Nw   = b'Nw  '
    PrnS = b'PrnS'
    Rct1 = b'Rct1'
    Bckg = b'Bckg'
    Clsp = b'Clsp'
    Qcsa = b'Qcsa'
    Mtrl = b'Mtrl'
    mtID = b'mtID'
    Srce = b'Srce'
    Dfs  = b'Dfs '
    mtll = b'mtll'
    mtlo = b'mtlo'
    ared = b'ared'
    agrn = b'agrn'
    ablu = b'ablu'
    dred = b'dred'
    dgrn = b'dgrn'
    dblu = b'dblu'
    sred = b'sred'
    sgrn = b'sgrn'
    sblu = b'sblu'
    ered = b'ered'
    egrn = b'egrn'
    eblu = b'eblu'
    shin = b'shin'
    shi2 = b'shi2'
    rtgh = b'rtgh'
    rogh = b'rogh'
    refl = b'refl'
    self = b'self'
    shad = b'shad'
    twos = b'twos'
    wire = b'wire'
    decl = b'decl'
    wfsz = b'wfsz'
    RfAc = b'RfAc'
    gMtr = b'gMtr'
    mIHd = b'mIHd'
    mapl = b'mapl'
    mapo = b'mapo'
    srgh = b'srgh'
    uscl = b'uscl'
    vscl = b'vscl'
    uoff = b'uoff'
    voff = b'voff'
    msty = b'msty'
    sTyP = b'sTyP'
    sWrU = b'sWrU'
    sWrV = b'sWrV'
    sWrW = b'sWrW'
    sMin = b'sMin'
    sMag = b'sMag'
    sMip = b'sMip'
    sUsE = b'sUsE'
    KeFL = b'KeFL'
    KeCS = b'KeCS'
    InsN = b'InsN'
    flgO = b'flgO'
    flgT = b'flgT'
    NoID = b'NoID'
    PrID = b'PrID'
    tYpE = b'tYpE'
    tYgE = b'tYgE'
    PvLs = b'PvLs'
    PvtO = b'PvtO'
    PvtX = b'PvtX'
    PvtY = b'PvtY'
    PvtZ = b'PvtZ'
    ExLs = b'ExLs'
    ExOb = b'ExOb'
    PvPr = b'PvPr'
    LcMt = b'LcMt'
    RgBl = b'RgBl'
    sTCl = b'sTCl'
    repo = b'repo'
    GsnB = b'GsnB'
    HSBC = b'HSBC'
    Lyr  = b'Lyr '
    Ordn = b'Ordn'
    Trgt = b'Trgt'
    Ylw  = b'Ylw '
    Blck = b'Blck'
    LghS = b'LghS'
    On   = b'On  '
    Fcs  = b'Fcs '
    Intn = b'Intn'
    LghT = b'LghT'
    Pstn = b'Pstn'
    Vct0 = b'Vct0'
    Vct1 = b'Vct1'
    CrnL = b'CrnL'
    Glos = b'Glos'
    Exps = b'Exps'
    AmbB = b'AmbB'
    AmbC = b'AmbC'
    FrmW = b'FrmW'
    BmpA = b'BmpA'
    BmpC = b'BmpC'
    LnsF = b'LnsF'
    FlrC = b'FlrC'
    Nkn1 = b'Nkn1'
    Dspl = b'Dspl'
    HrzS = b'HrzS'
    VrtS = b'VrtS'
    DspM = b'DspM'
    StrF = b'StrF'
    UndA = b'UndA'
    RptE = b'RptE'
    DspF = b'DspF'
    HStr = b'HStr'
    Clrz = b'Clrz'
    Adjs = b'Adjs'
    Hst2 = b'Hst2'
    Lght = b'Lght'
    LaID = b'LaID'
    LaSt = b'LaSt'
    FrLs = b'FrLs'
    CMod = b'CMod'
    Sett = b'Sett'
    Cst  = b'Cst '
    WBal = b'WBal'
    AsSh = b'AsSh'
    Temp = b'Temp'
    Tint = b'Tint'
    CtoG = b'CtoG'
    Shrp = b'Shrp'
    LNR  = b'LNR '
    CNR  = b'CNR '
    VigA = b'VigA'
    BlkB = b'BlkB'
    RHue = b'RHue'
    RSat = b'RSat'
    GHue = b'GHue'
    GSat = b'GSat'
    BHue = b'BHue'
    BSat = b'BSat'
    Vibr = b'Vibr'
    HA_R = b'HA_R'
    HA_O = b'HA_O'
    HA_Y = b'HA_Y'
    HA_G = b'HA_G'
    HA_A = b'HA_A'
    HA_B = b'HA_B'
    HA_P = b'HA_P'
    HA_M = b'HA_M'
    SA_R = b'SA_R'
    SA_O = b'SA_O'
    SA_Y = b'SA_Y'
    SA_G = b'SA_G'
    SA_A = b'SA_A'
    SA_B = b'SA_B'
    SA_P = b'SA_P'
    SA_M = b'SA_M'
    LA_R = b'LA_R'
    LA_O = b'LA_O'
    LA_Y = b'LA_Y'
    LA_G = b'LA_G'
    LA_A = b'LA_A'
    LA_B = b'LA_B'
    LA_P = b'LA_P'
    LA_M = b'LA_M'
    STSH = b'STSH'
    STSS = b'STSS'
    STHH = b'STHH'
    STHS = b'STHS'
    STB  = b'STB '
    PC_S = b'PC_S'
    PC_D = b'PC_D'
    PC_L = b'PC_L'
    PC_H = b'PC_H'
    PC_1 = b'PC_1'
    PC_2 = b'PC_2'
    PC_3 = b'PC_3'
    ShpR = b'ShpR'
    ShpD = b'ShpD'
    ShpM = b'ShpM'
    PCVA = b'PCVA'
    GRNA = b'GRNA'
    LPEn = b'LPEn'
    MDis = b'MDis'
    PerV = b'PerV'
    PerH = b'PerH'
    PerR = b'PerR'
    PerS = b'PerS'
    PerA = b'PerA'
    PerU = b'PerU'
    PerX = b'PerX'
    PerY = b'PerY'
    AuCA = b'AuCA'
    Ex12 = b'Ex12'
    Cr12 = b'Cr12'
    Hi12 = b'Hi12'
    Sh12 = b'Sh12'
    Wh12 = b'Wh12'
    Bk12 = b'Bk12'
    Cl12 = b'Cl12'
    DfPA = b'DfPA'
    DPHL = b'DPHL'
    DPHH = b'DPHH'
    DfGA = b'DfGA'
    DPGL = b'DPGL'
    DPGH = b'DPGH'
    Dhze = b'Dhze'
    CrvR = b'CrvR'
    CrvG = b'CrvG'
    CrvB = b'CrvB'
    CamP = b'CamP'
    CP_D = b'CP_D'
    PrVe = b'PrVe'
    Rtch = b'Rtch'
    REye = b'REye'
    LCs  = b'LCs '
    Upri = b'Upri'
    GuUr = b'GuUr'
    FXRf = b'FXRf'
    IMsk = b'IMsk'
    Lvls = b'Lvls'
    LvlA = b'LvlA'
    Chnl = b'Chnl'
    Cmps = b'Cmps'
    Inpt = b'Inpt'
    Gmm  = b'Gmm '
    AWBV = b'AWBV'
    TMMs = b'TMMs'
    LNRD = b'LNRD'
    CNRD = b'CNRD'
    LNRC = b'LNRC'
    CNRS = b'CNRS'
    Nkn  = b'Nkn '
    HghP = b'HghP'
    LbCl = b'LbCl'
    Lmnc = b'Lmnc'
    A    = b'A   '
    B    = b'B   '
    Expn = b'Expn'
    PstS = b'PstS'
    Inte = b'Inte'
    Img  = b'Img '
    Bltn = b'Bltn'
    Cptn = b'Cptn'
    Clbr = b'Clbr'
    RgsM = b'RgsM'
    CrnC = b'CrnC'
    CntC = b'CntC'
    Lbls = b'Lbls'
    Ngtv = b'Ngtv'
    EmlD = b'EmlD'
    BrdT = b'BrdT'
    Bld  = b'Bld '
    PgPs = b'PgPs'
    PgPC = b'PgPC'
    Clrm = b'Clrm'
    MpBl = b'MpBl'
    Spcn = b'Spcn'
    LCnt = b'LCnt'
    Msge = b'Msge'
    Path = b'Path'
    AdNs = b'AdNs'
    Dstr = b'Dstr'
    Unfr = b'Unfr'
    Mnch = b'Mnch'
    FlRs = b'FlRs'
    PaCm = b'PaCm'
    SbpL = b'SbpL'
    Sbpl = b'Sbpl'
    Pts  = b'Pts '
    Pthp = b'Pthp'
    Anch = b'Anch'
    Fwd  = b'Fwd '
    Bwd  = b'Bwd '
    Smoo = b'Smoo'
    InvT = b'InvT'
    BanW = b'BanW'
    SlcC = b'SlcC'
    Mthd = b'Mthd'
    CrcM = b'CrcM'
    Rltv = b'Rltv'
    ClrC = b'ClrC'
    Ylws = b'Ylws'
    Whts = b'Whts'
    Ntrl = b'Ntrl'
    Blks = b'Blks'
    Bk   = b'Bk  '
    MtnB = b'MtnB'
    RdlB = b'RdlB'
    BlrM = b'BlrM'
    Zm   = b'Zm  '
    BlrQ = b'BlrQ'
    Gd   = b'Gd  '
    GEfc = b'GEfc'
    GEfs = b'GEfs'
    GEfk = b'GEfk'
    GEft = b'GEft'
    GELv = b'GELv'
    GraP = b'GraP'
    StrL = b'StrL'
    LgDr = b'LgDr'
    SDir = b'SDir'
    StrD = b'StrD'
    SDRD = b'SDRD'
    PltK = b'PltK'
    StrS = b'StrS'
    StDt = b'StDt'
    Engn = b'Engn'


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


# class DisplayResolutionUnit(Enum):
#     PIXELS_PER_INCH = 1
#     PIXELS_PER_CM = 2


# class DimensionUnit(Enum):
#     INCH = 1
#     CM = 2
#     POINT = 3  # 72 points == 1 inch
#     PICA = 4   # 6 pica == 1 inch
#     COLUMN = 5


# class PlacedLayerProperty(Enum):
#     TRANSFORM = b'Trnf'
#     SIZE = b'Sz  '
#     ID = b'Idnt'


# class TextProperty(Enum):
#     TXT = b'Txt '
#     ORIENTATION = b'Ornt'


# class TextOrientation(Enum):
#     HORIZONTAL = b'Hrzn'


# class ObjectBasedEffects(Enum):
#     """Type of the object-based effects."""
#     DROP_SHADOW_MULTI = b'dropShadowMulti'
#     DROP_SHADOW = b'DrSh'
#     INNER_SHADOW_MULTI = b'innerShadowMulti'
#     INNER_SHADOW = b'IrSh'
#     OUTER_GLOW = b'OrGl'
#     COLOR_OVERLAY_MULTI = b'solidFillMulti'
#     COLOR_OVERLAY = b'SoFi'
#     GRADIENT_OVERLAY_MULTI = b'gradientFillMulti'
#     GRADIENT_OVERLAY = b'GrFl'
#     PATTERN_OVERLAY = b'patternFill'
#     STROKE_MULTI = b'frameFXMulti'
#     STROKE = b'FrFX'
#     INNER_GLOW = b'IrGl'
#     BEVEL_EMBOSS = b'ebbl'
#     SATIN = b'ChFX'
