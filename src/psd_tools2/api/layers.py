"""
Layer module.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools2.constants import SectionDivider, Clipping

logger = logging.getLogger(__name__)


class Layer(object):
    def __init__(self, psd, record, channels, parent):
        self._psd = psd
        self._record = record
        self._channels = channels
        self._parent = parent
        self._clip_layers = None

    @property
    def name(self):
        return self._record.tagged_blocks.get_data(
            'UNICODE_LAYER_NAME', self._record.name
        )

    @property
    def invisible(self):
        return not self._record.flags.visible

    @property
    def left(self):
        return self._record.left

    @property
    def top(self):
        return self._record.top

    @property
    def right(self):
        return self._record.right

    @property
    def bottom(self):
        return self._record.bottom

    @property
    def size(self):
        return self.width, self.height

    @property
    def width(self):
        return self.right - self.left

    @property
    def height(self):
        return self.bottom - self.top

    def __repr__(self):
        return '%s(%r size=%dx%d%s)' % (
            self.__class__.__name__, self.name, self.width, self.height,
            ' invisible' if self.invisible else '',
        )

    def _repr_pretty_(self, p, cycle):
        if cycle:
            return '{name}(...)'.format(name=self.__class__.__name__)

        with p.group(2, self.__repr__()):
            for idx, layer in enumerate(self._clip_layers or []):
                p.break_()
                p.text('+ ')
                p.pretty(layer)


class Group(Layer):
    def __init__(self, *args):
        super(Group, self).__init__(*args)
        self._layers = []

    @property
    def layers(self):
        return self._layers

    def _repr_pretty_(self, p, cycle):
        if cycle:
            return '{name}(...)'.format(name=self.__class__.__name__)

        with p.group(2, self.__repr__()):
            for idx, layer in enumerate(self._layers):
                p.break_()
                p.text('[%d] ' % idx)
                p.pretty(layer)
            for idx, layer in enumerate(self._clip_layers or []):
                p.break_()
                p.text('+ ')
                p.pretty(layer)


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
