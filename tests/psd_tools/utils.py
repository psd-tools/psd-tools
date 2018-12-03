# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals
import os
import psd_tools.reader
import psd_tools.decoder

DATA_PATH = os.path.join(
    os.path.abspath(os.path.dirname(os.path.dirname(__file__))),
    'psd_files'
)


def full_name(filename):
    return os.path.join(DATA_PATH, filename)


def load_psd(filename):
    with open(full_name(filename), 'rb') as f:
        return psd_tools.reader.parse(f)


def decode_psd(filename):
    return psd_tools.decoder.parse(load_psd(filename))


# see http://lukeplant.me.uk/blog/posts/fuzzy-testing-with-assertnumqueries/
class FuzzyInt(int):
    def __new__(cls, lowest, highest):
        obj = super(FuzzyInt, cls).__new__(cls, highest)
        obj.lowest = lowest
        obj.highest = highest
        return obj

    def __eq__(self, other):
        return other >= self.lowest and other <= self.highest

    def __repr__(self):
        return str("[%d..%d]") % (self.lowest, self.highest)


def with_psb(fixtures):
    psb_fixtures = []
    for fixture in fixtures:
        psb_fixtures.append(
            type(fixture)([fixture[0].replace('.psd', '.psb')]) + fixture[1:])
    print(fixtures + type(fixtures)(psb_fixtures))
    return fixtures + type(fixtures)(psb_fixtures)
