"""
Layer module.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools2.constants import BlendMode, SectionDivider, Clipping

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

    @name.setter
    def name(self, value):
        if str != bytes:
            assert isinstance(value, str)
        else:
            assert isinstance(value, unicode)
        assert len(value) < 256, 'Layer name too long (%d) %s' % (
            len(value), value
        )
        try:
            value.encode('macroman')
            self._record.name = value
        except UnicodeEncodeError:
            self._record.name = str('?')
        self._record.tagged_blocks.set_data('UNICODE_LAYER_NAME', value)

    @property
    def kind(self):
        """
        Kind of this layer, either of group, pixel, shape, type, smartobject,
        or psdimage.

        :return: str.
        """
        return self.__class__.__name__.lower().replace("layer", "")

    @property
    def layer_id(self):
        """
        Layer ID.

        :return: int layer id. if the layer is not assigned an id, -1.
        """
        return self.tagged_blocks.get_data('layer_id', -1)

    @property
    def visible(self):
        """Layer invisibility. Doesn't take group visibility in account."""
        return self._record.flags.visible

    @visible.setter
    def visible(self, value):
        self._record.flags.visible = bool(value)

    def is_visible(self):
        """Layer invisibility. Takes group visibility in account."""
        return self.visible or self.parent.is_visible()

    @property
    def opacity(self):
        """Opacity of this layer."""
        return self._record.opacity

    @opacity.setter
    def opacity(self, value):
        assert 0 <= value and value <= 255
        self._record.opacity = int(value)

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

    @blend_mode.setter
    def blend_mode(self, value):
        if hasattr(BlendMode, value.upper()):
            self._record.blend_mode = getattr(BlendMode, value.upper())
        else:
            self._record.blend_mode = BlendMode(value)

    def has_mask(self):
        """Returns True if the layer has a mask."""
        return self._record.mask_data is not None

    @property
    def left(self):
        """Left coordinate."""
        return self._record.left

    @left.setter
    def left(self, value):
        w = self.width
        self._record.left = int(value)
        self._record.right = int(value) + w

    @property
    def top(self):
        """Top coordinate."""
        return self._record.top

    @top.setter
    def top(self, value):
        h = self.height
        self._record.top = int(value)
        self._record.bottom = int(value) + h

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
    def offset(self):
        """(left, top) tuple."""
        return self.left, self.top

    @offset.setter
    def offset(self, value):
        self.left, self.top = value

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
