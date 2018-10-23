from __future__ import absolute_import, unicode_literals
import logging
import glob
import os

logging.basicConfig(level=logging.DEBUG)


def full_name(filename):
    return os.path.join(
        os.path.abspath(os.path.dirname(os.path.dirname(__file__))),
        'psd_files', filename
    )


def all_files():
    return [(filepath,) for filepath in glob.glob(full_name('*.ps*'))]


def check_write_read(element, *args, **kwargs):
    data = element.tobytes(*args, **kwargs)
    new_element = element.frombytes(data, *args, **kwargs)
    assert element == new_element, '%s vs %s' % (element, new_element)


def check_read_write(cls, data, *args, **kwargs):
    element = cls.frombytes(data, *args, **kwargs)
    new_data = element.tobytes(*args, **kwargs)
    assert data == new_data
