#!/Users/Stephen/Scripts/psd-tools3/venv/python39/bin/python
# -*- coding: utf-8 -*-
#
#
# Library to extract Exif information from digital camera image files.
# https://github.com/ianare/exif-py
#
#
# Copyright (c) 2002-2007 Gene Cash
# Copyright (c) 2007-2014 Ianaré Sévi and contributors
#
# See LICENSE.txt file for licensing information
# See CHANGES.txt file for all contributors and changes
#

"""
Runs Exif tag extraction in command line.
"""

import sys
import getopt
import logging
import timeit
from exifread.tags import DEFAULT_STOP_TAG, FIELD_TYPES
from exifread import process_file, exif_log, __version__

logger = exif_log.get_logger()


def usage(exit_status):
    """Show command line usage."""
    msg = ('Usage: EXIF.py [OPTIONS] file1 [file2 ...]\n'
           'Extract EXIF information from digital camera image files.\n\nOptions:\n'
           '-h --help               Display usage information and exit.\n'
           '-v --version            Display version information and exit.\n'
           '-q --quick              Do not process MakerNotes.\n'
           '-t TAG --stop-tag TAG   Stop processing when this tag is retrieved.\n'
           '-s --strict             Run in strict mode (stop on errors).\n'
           '-d --debug              Run in debug mode (display extra info).\n'
           '-c --color              Output in color (only works with debug on POSIX).\n'
    )
    print(msg)
    sys.exit(exit_status)


def show_version():
    """Show the program version."""
    print('Version %s on Python%s' % (__version__, sys.version_info[0]))
    sys.exit(0)


def main():
    """Parse command line options/arguments and execute."""
    try:
        arg_names = ["help", "version", "quick", "strict", "debug", "stop-tag="]
        opts, args = getopt.getopt(sys.argv[1:], "hvqsdct:v", arg_names)
    except getopt.GetoptError:
        usage(2)

    detailed = True
    stop_tag = DEFAULT_STOP_TAG
    debug = False
    strict = False
    color = False

    for option, arg in opts:
        if option in ("-h", "--help"):
            usage(0)
        if option in ("-v", "--version"):
            show_version()
        if option in ("-q", "--quick"):
            detailed = False
        if option in ("-t", "--stop-tag"):
            stop_tag = arg
        if option in ("-s", "--strict"):
            strict = True
        if option in ("-d", "--debug"):
            debug = True
        if option in ("-c", "--color"):
            color = True

    if not args:
        usage(2)

    exif_log.setup_logger(debug, color)

    # output info for each file
    for filename in args:
        file_start = timeit.default_timer()
        try:
            img_file = open(str(filename), 'rb')
        except IOError:
            logger.error("'%s' is unreadable", filename)
            continue
        logger.info("Opening: %s", filename)

        tag_start = timeit.default_timer()

        # get the tags
        data = process_file(img_file, stop_tag=stop_tag, details=detailed, strict=strict, debug=debug)

        tag_stop = timeit.default_timer()

        if not data:
            logger.warning("No EXIF information found\n")
            continue

        if 'JPEGThumbnail' in data:
            logger.info('File has JPEG thumbnail')
            del data['JPEGThumbnail']
        if 'TIFFThumbnail' in data:
            logger.info('File has TIFF thumbnail')
            del data['TIFFThumbnail']

        tag_keys = list(data.keys())
        tag_keys.sort()

        for i in tag_keys:
            try:
                logger.info('%s (%s): %s', i, FIELD_TYPES[data[i].field_type][2], data[i].printable)
            except:
                logger.error("%s : %s", i, str(data[i]))

        file_stop = timeit.default_timer()

        logger.debug("Tags processed in %s seconds", tag_stop - tag_start)
        logger.debug("File processed in %s seconds", file_stop - file_start)
        print("")


if __name__ == '__main__':
    main()
