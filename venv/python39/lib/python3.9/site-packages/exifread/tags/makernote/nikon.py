
from ...utils import make_string, Ratio

def ev_bias(seq):
    """
    First digit seems to be in steps of 1/6 EV.
    Does the third value mean the step size?  It is usually 6,
    but it is 12 for the ExposureDifference.
    Check for an error condition that could cause a crash.
    This only happens if something has gone really wrong in
    reading the Nikon MakerNote.
    http://tomtia.plala.jp/DigitalCamera/MakerNote/index.asp
    """
    if len(seq) < 4:
        return ''
    if seq == [252, 1, 6, 0]:
        return '-2/3 EV'
    if seq == [253, 1, 6, 0]:
        return '-1/2 EV'
    if seq == [254, 1, 6, 0]:
        return '-1/3 EV'
    if seq == [0, 1, 6, 0]:
        return '0 EV'
    if seq == [2, 1, 6, 0]:
        return '+1/3 EV'
    if seq == [3, 1, 6, 0]:
        return '+1/2 EV'
    if seq == [4, 1, 6, 0]:
        return '+2/3 EV'
        # Handle combinations not in the table.
    a = seq[0]
    # Causes headaches for the +/- logic, so special case it.
    if a == 0:
        return '0 EV'
    if a > 127:
        a = 256 - a
        ret_str = '-'
    else:
        ret_str = '+'
    step = seq[2]  # Assume third value means the step size
    whole = a / step
    a = a % step
    if whole != 0:
        ret_str = '%s%s ' % (ret_str, str(whole))
    if a == 0:
        ret_str += 'EV'
    else:
        r = Ratio(a, step)
        ret_str = ret_str + r.__repr__() + ' EV'
    return ret_str

# Nikon E99x MakerNote Tags
TAGS_NEW = {
    0x0001: ('MakernoteVersion', make_string),  # Sometimes binary
    0x0002: ('ISOSetting', make_string),
    0x0003: ('ColorMode', ),
    0x0004: ('Quality', ),
    0x0005: ('Whitebalance', ),
    0x0006: ('ImageSharpening', ),
    0x0007: ('FocusMode', ),
    0x0008: ('FlashSetting', ),
    0x0009: ('AutoFlashMode', ),
    0x000B: ('WhiteBalanceBias', ),
    0x000C: ('WhiteBalanceRBCoeff', ),
    0x000D: ('ProgramShift', ev_bias),
    # Nearly the same as the other EV vals, but step size is 1/12 EV (?)
    0x000E: ('ExposureDifference', ev_bias),
    0x000F: ('ISOSelection', ),
    0x0010: ('DataDump', ),
    0x0011: ('NikonPreview', ),
    0x0012: ('FlashCompensation', ev_bias),
    0x0013: ('ISOSpeedRequested', ),
    0x0016: ('PhotoCornerCoordinates', ),
    0x0017: ('ExternalFlashExposureComp', ev_bias),
    0x0018: ('FlashBracketCompensationApplied', ev_bias),
    0x0019: ('AEBracketCompensationApplied', ),
    0x001A: ('ImageProcessing', ),
    0x001B: ('CropHiSpeed', ),
    0x001C: ('ExposureTuning', ),
    0x001D: ('SerialNumber', ),  # Conflict with 0x00A0 ?
    0x001E: ('ColorSpace', ),
    0x001F: ('VRInfo', ),
    0x0020: ('ImageAuthentication', ),
    0x0022: ('ActiveDLighting', ),
    0x0023: ('PictureControl', ),
    0x0024: ('WorldTime', ),
    0x0025: ('ISOInfo', ),
    0x0080: ('ImageAdjustment', ),
    0x0081: ('ToneCompensation', ),
    0x0082: ('AuxiliaryLens', ),
    0x0083: ('LensType', ),
    0x0084: ('LensMinMaxFocalMaxAperture', ),
    0x0085: ('ManualFocusDistance', ),
    0x0086: ('DigitalZoomFactor', ),
    0x0087: ('FlashMode', {
        0x00: 'Did Not Fire',
        0x01: 'Fired, Manual',
        0x07: 'Fired, External',
        0x08: 'Fired, Commander Mode ',
        0x09: 'Fired, TTL Mode',
    }),
    0x0088: ('AFFocusPosition', {
        0x0000: 'Center',
        0x0100: 'Top',
        0x0200: 'Bottom',
        0x0300: 'Left',
        0x0400: 'Right',
    }),
    0x0089: ('BracketingMode', {
        0x00: 'Single frame, no bracketing',
        0x01: 'Continuous, no bracketing',
        0x02: 'Timer, no bracketing',
        0x10: 'Single frame, exposure bracketing',
        0x11: 'Continuous, exposure bracketing',
        0x12: 'Timer, exposure bracketing',
        0x40: 'Single frame, white balance bracketing',
        0x41: 'Continuous, white balance bracketing',
        0x42: 'Timer, white balance bracketing'
    }),
    0x008A: ('AutoBracketRelease', ),
    0x008B: ('LensFStops', ),
    0x008C: ('NEFCurve1', ),  # ExifTool calls this 'ContrastCurve'
    0x008D: ('ColorMode', ),
    0x008F: ('SceneMode', ),
    0x0090: ('LightingType', ),
    0x0091: ('ShotInfo', ),  # First 4 bytes are a version number in ASCII
    0x0092: ('HueAdjustment', ),
    # ExifTool calls this 'NEFCompression', should be 1-4
    0x0093: ('Compression', ),
    0x0094: ('Saturation', {
        -3: 'B&W',
        -2: '-2',
        -1: '-1',
        0: '0',
        1: '1',
        2: '2',
    }),
    0x0095: ('NoiseReduction', ),
    0x0096: ('NEFCurve2', ),  # ExifTool calls this 'LinearizationTable'
    0x0097: ('ColorBalance', ),  # First 4 bytes are a version number in ASCII
    0x0098: ('LensData', ),  # First 4 bytes are a version number in ASCII
    0x0099: ('RawImageCenter', ),
    0x009A: ('SensorPixelSize', ),
    0x009C: ('Scene Assist', ),
    0x009E: ('RetouchHistory', ),
    0x00A0: ('SerialNumber', ),
    0x00A2: ('ImageDataSize', ),
    # 00A3: unknown - a single byte 0
    # 00A4: In NEF, looks like a 4 byte ASCII version number ('0200')
    0x00A5: ('ImageCount', ),
    0x00A6: ('DeletedImageCount', ),
    0x00A7: ('TotalShutterReleases', ),
    # First 4 bytes are a version number in ASCII, with version specific
    # info to follow.  Its hard to treat it as a string due to embedded nulls.
    0x00A8: ('FlashInfo', ),
    0x00A9: ('ImageOptimization', ),
    0x00AA: ('Saturation', ),
    0x00AB: ('DigitalVariProgram', ),
    0x00AC: ('ImageStabilization', ),
    0x00AD: ('AFResponse', ),
    0x00B0: ('MultiExposure', ),
    0x00B1: ('HighISONoiseReduction', ),
    0x00B6: ('PowerUpTime', ),
    0x00B7: ('AFInfo2', ),
    0x00B8: ('FileInfo', ),
    0x00B9: ('AFTune', ),
    0x0100: ('DigitalICE', ),
    0x0103: ('PreviewCompression', {
        1: 'Uncompressed',
        2: 'CCITT 1D',
        3: 'T4/Group 3 Fax',
        4: 'T6/Group 4 Fax',
        5: 'LZW',
        6: 'JPEG (old-style)',
        7: 'JPEG',
        8: 'Adobe Deflate',
        9: 'JBIG B&W',
        10: 'JBIG Color',
        32766: 'Next',
        32769: 'Epson ERF Compressed',
        32771: 'CCIRLEW',
        32773: 'PackBits',
        32809: 'Thunderscan',
        32895: 'IT8CTPAD',
        32896: 'IT8LW',
        32897: 'IT8MP',
        32898: 'IT8BL',
        32908: 'PixarFilm',
        32909: 'PixarLog',
        32946: 'Deflate',
        32947: 'DCS',
        34661: 'JBIG',
        34676: 'SGILog',
        34677: 'SGILog24',
        34712: 'JPEG 2000',
        34713: 'Nikon NEF Compressed',
        65000: 'Kodak DCR Compressed',
        65535: 'Pentax PEF Compressed',
    }),
    0x0201: ('PreviewImageStart', ),
    0x0202: ('PreviewImageLength', ),
    0x0213: ('PreviewYCbCrPositioning', {
        1: 'Centered',
        2: 'Co-sited',
    }),
    0x0E09: ('NikonCaptureVersion', ),
    0x0E0E: ('NikonCaptureOffsets', ),
    0x0E10: ('NikonScan', ),
    0x0E22: ('NEFBitDepth', ),
}

TAGS_OLD = {
    0x0003: ('Quality', {
        1: 'VGA Basic',
        2: 'VGA Normal',
        3: 'VGA Fine',
        4: 'SXGA Basic',
        5: 'SXGA Normal',
        6: 'SXGA Fine',
    }),
    0x0004: ('ColorMode', {
        1: 'Color',
        2: 'Monochrome',
    }),
    0x0005: ('ImageAdjustment', {
        0: 'Normal',
        1: 'Bright+',
        2: 'Bright-',
        3: 'Contrast+',
        4: 'Contrast-',
    }),
    0x0006: ('CCDSpeed', {
        0: 'ISO 80',
        2: 'ISO 160',
        4: 'ISO 320',
        5: 'ISO 100',
    }),
    0x0007: ('WhiteBalance', {
        0: 'Auto',
        1: 'Preset',
        2: 'Daylight',
        3: 'Incandescent',
        4: 'Fluorescent',
        5: 'Cloudy',
        6: 'Speed Light',
    }),
}
