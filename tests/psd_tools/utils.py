from __future__ import absolute_import, unicode_literals
import logging
import fnmatch
import os
import tempfile
from psd_tools.utils import trimmed_repr

logging.basicConfig(level=logging.DEBUG)

# Use maccyrillic encoding.
CYRILLIC_FILES = {
    'layer_mask_data.psb',
    'layer_mask_data.psd',
    'layer_params.psb',
    'layer_params.psd',
    'layer_comps.psb',
    'layer_comps.psd',
}

# Unknown encoding.
OTHER_FILES = {
    'advanced-blending.psd',
    'effect-stroke-gradient.psd',
    'layer_effects.psd',
    'patterns.psd',
    'fill_adjustments.psd',
    'blend-and-clipping.psd',
    'clipping-mask2.psd',
}

TEST_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


def find_files(pattern='*.ps*', root=TEST_ROOT):
    for root, dirnames, filenames in os.walk(root):
        for filename in fnmatch.filter(filenames, pattern):
            yield os.path.join(root, filename)


def full_name(filename):
    return os.path.join(TEST_ROOT, 'psd_files', filename)


def all_files():
    return [f for f in find_files() if f.find('third-party-psds') < 0]


def check_write_read(element, *args, **kwargs):
    with tempfile.TemporaryFile() as f:
        element.write(f, *args, **kwargs)
        f.flush()
        f.seek(0)
        new_element = element.read(f, *args, **kwargs)
    assert element == new_element, '%s vs %s' % (element, new_element)


def check_read_write(cls, data, *args, **kwargs):
    element = cls.frombytes(data, *args, **kwargs)
    new_data = element.tobytes(*args, **kwargs)
    assert data == new_data, '%s vs %s' % (
        trimmed_repr(data), trimmed_repr(new_data)
    )
