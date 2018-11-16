"""
PSD Image module.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools2.constants import SectionDivider, Clipping


logger = logging.getLogger(__name__)


class Layer(object):
    def __init__(self, record, channels, parent):
        self._record = record
        self._channels = channels
        self._parent = parent
        self._clip_layers = None

class Group(Layer):
    def __init__(self, *args):
        super(Group, self).__init__(*args)
        self._layers = []

    @property
    def layers(self):
        return self._layers


class PixelLayer(Layer):
    pass

class SmartObjectLayer(Layer):
    pass

class TypeLayer(Layer):
    pass

class ShapeLayer(Layer):
    pass

class AdjustmentLayer(Layer):
    pass
