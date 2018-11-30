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
        self._clip_layers = []

    @property
    def name(self):
        """
        Layer name.

        :return: str.
        """
        return self._record.tagged_blocks.get_data(
            'UNICODE_LAYER_NAME', self._record.name
        )

    @property
    def kind(self):
        """
        Kind of this layer, either of group, pixel, shape, type, smartobject,
        or psdimage.

        :return: str.
        """
        return self.__class__.__name__.lower().replace("layer", "")

    @property
    def visible(self):
        """Layer invisibility. Doesn't take group visibility in account."""
        return self._record.flags.visible

    def is_visible(self):
        """Layer invisibility. Takes group visibility in account."""
        return self.visible or self.parent.is_visible()

    @property
    def opacity(self):
        """Opacity of this layer."""
        return self._record.opacity

    @property
    def parent(self):
        """Parent of this layer."""
        return self._parent

    def is_group(self):
        """Return True if the layer is a group."""
        return False

    @property
    def blend_mode(self):
        """
        Blend mode of this layer. See
        :py:class:`~psd_tools2.constants.BlendMode`

        :return: blend mode enum.
        """
        return self._record.blend_mode

    def has_mask(self):
        """Returns True if the layer has a mask."""
        return self._record.mask_data is not None

    @property
    def left(self):
        """Left coordinate."""
        return self._record.left

    @property
    def top(self):
        """Top coordinate."""
        return self._record.top

    @property
    def right(self):
        """Right coordinate."""
        return self._record.right

    @property
    def bottom(self):
        """Bottom coordinate."""
        return self._record.bottom

    @property
    def width(self):
        """Width of the layer."""
        return self.right - self.left

    @property
    def height(self):
        """Height of the layer."""
        return self.bottom - self.top

    @property
    def size(self):
        """(width, height) tuple."""
        return self.width, self.height

    @property
    def bbox(self):
        """(left, top, right, bottom) tuple."""
        return self.left, self.top, self.right, self.bottom

    @property
    def clip_layers(self):
        """
        Clip layers associated with this layer.

        :return: list of, AdjustmentLayer, PixelLayer, or ShapeLayer
        """
        return self._clip_layers

    @property
    def tagged_blocks(self):
        return self._record.tagged_blocks

    def __repr__(self):
        return '%s(%r size=%dx%d%s)' % (
            self.__class__.__name__, self.name, self.width, self.height,
            ' invisible' if not self.visible else '',
        )


class GroupMixin(object):
    def __init__(self, *args):
        super(GroupMixin, self).__init__(*args)
        self._layers = []

    def __len__(self):
        return self._layers.__len__()

    def __iter__(self):
        return self._layers.__iter__()

    def __getitem__(self, key):
        return self._layers.__getitem__(key)

    def __setitem__(self, key, value):
        return self._layers.__setitem__(key, value)

    def __delitem__(self, key):
        return self._layers.__delitem__(key)

    def is_group(self):
        """Return True if the layer is a group."""
        return True

    def descendants(self, include_clip=True):
        """
        Return a generator to iterate over all descendant layers.

        :param include_clip: include clipping layers.
        """
        for layer in self:
            yield layer
            if layer.is_group():
                for child in layer.descendants(include_clip):
                    yield child
            if include_clip and hasattr(layer, 'clip_layers'):
                for clip_layer in layer.clip_layers:
                    yield clip_layer


class Group(GroupMixin, Layer):
    pass


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
