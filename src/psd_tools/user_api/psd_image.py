# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import collections
import weakref              # FIXME: there should be weakrefs in this module
import psd_tools.reader
import psd_tools.decoder
from psd_tools.constants import TaggedBlock, SectionDivider
from psd_tools.user_api.layers import group_layers
from psd_tools.user_api.pil_support import composite_image_to_PIL, layer_to_PIL
from psd_tools.user_api import pymaging_support

BBox = collections.namedtuple('BBox', 'x1, y1, x2, y2')

class _RawLayer(object):
    """
    Layer groups and layers are internally both 'layers' in PSD;
    they share some common properties.
    """

    parent = None
    _psd = None
    _index = None

    @property
    def name(self):
        """ Layer name (as unicode). """
        return self._tagged_blocks.get(
            TaggedBlock.UNICODE_LAYER_NAME,
            self._info.name
        )

    @property
    def visible(self):
        """ Layer visibility. Takes group visibility in account. """
        return self._info.flags.visible and self.parent.visible

    @property
    def layer_id(self):
        return self._tagged_blocks.get(TaggedBlock.LAYER_ID)

    @property
    def opacity(self):
        return self._info.opacity

    @property
    def blend_mode(self):
        return self._info.blend_mode

    @property
    def _info(self):
        return self._psd._layer_info(self._index)

    @property
    def _tagged_blocks(self):
        return dict(self._info.tagged_blocks)


class Layer(_RawLayer):
    """ PSD layer wrapper """

    def __init__(self, parent, index):
        self.parent = parent
        self._psd = parent._psd
        self._index = index

    def as_PIL(self):
        """ Returns a PIL image for this layer. """
        return self._psd._layer_as_PIL(self._index)

    def as_pymaging(self):
        """ Returns a pymaging.Image for this PSD file. """
        return self._psd._layer_as_pymaging(self._index)

    @property
    def bbox(self):
        """ BBox(x1, y1, x2, y2) namedtuple with layer bounding box. """
        info = self._info
        return BBox(info.left, info.top, info.right, info.bottom)

    @property
    def width(self):
        return self._info.width()

    @property
    def height(self):
        return self._info.height()

    def __repr__(self):
        return "<psd_tools.Layer: %r, size=%dx%d, x=%d, y=%d>" % (
            self.name, self.width, self.height, self._info.left, self._info.top)


class Group(_RawLayer):
    """ PSD layer group wrapper """

    def __init__(self, parent, index, layers):
        self.parent = parent
        self._psd = parent._psd
        self._index = index
        self.layers = layers

    @property
    def closed(self):
        divider = self._tagged_blocks.get(TaggedBlock.SECTION_DIVIDER_SETTING, None)
        if divider is None:
            return
        return divider.type == SectionDivider.CLOSED_FOLDER

    @property
    def bbox(self):
        """
        BBox(x1, y1, x2, y2) namedtuple with a bounding box for
        all layers in this group; None if a group has no children.
        """
        return _combined_bbox(self.layers)

    def _add_layer(self, child):
        self.layers.append(child)

    def __repr__(self):
        return "<psd_tools.Group: %r, layer_count=%d>" % (
            self.name, len(self.layers))



class PSDImage(object):
    """ PSD image wrapper """

    def __init__(self, decoded_data):
        self.header = decoded_data.header
        self.decoded_data = decoded_data

        # wrap decoded data to Layer and Group structures
        def fill_group(group, data):

            for layer in data['layers']:
                index = layer['index']

                if 'layers' in layer:
                    # group
                    sub_group = Group(group, index, [])
                    fill_group(sub_group, layer)
                    group._add_layer(sub_group)
                else:
                    # regular layer
                    group._add_layer(Layer(group, index))

        self._psd = self
        fake_root_data = {'layers': group_layers(decoded_data), 'index': None}
        root = _RootGroup(self, None, [])
        fill_group(root, fake_root_data)

        self._fake_root_group = root
        self.layers = root.layers


    @classmethod
    def load(cls, path, encoding='utf8'):
        """
        Returns a new :class:`PSDImage` loaded from ``path``.
        """
        with open(path, 'rb') as fp:
            return cls.from_stream(fp, encoding)

    @classmethod
    def from_stream(cls, fp, encoding='utf8'):
        """
        Returns a new :class:`PSDImage` loaded from stream ``fp``.
        """
        decoded_data = psd_tools.decoder.parse(
            psd_tools.reader.parse(fp, encoding)
        )
        return cls(decoded_data)


    def as_PIL(self):
        """
        Returns a PIL image for this PSD file.
        """
        return composite_image_to_PIL(self.decoded_data)

    def as_pymaging(self):
        """
        Returns a pymaging.Image for this PSD file.
        """
        return pymaging_support.extract_composite_image(self.decoded_data)

    @property
    def bbox(self):
        """
        BBox(x1, y1, x2, y2) namedtuple with a bounding box for
        all layers in this image; None if there are no image layers.

        This may differ from the image dimensions
        (img.header.width and img.header.heigth).
        """
        return _combined_bbox(self.layers)

    def _layer_info(self, index):
        layers = self.decoded_data.layer_and_mask_data.layers.layer_records
        return layers[index]

    def _layer_as_PIL(self, index):
        return layer_to_PIL(self.decoded_data, index)

    def _layer_as_pymaging(self, index):
        return pymaging_support.extract_layer_image(self.decoded_data, index)


def _combined_bbox(layers):
    """
    Returns a bounding box for ``layers`` or None if this is not possible.
    """
    bboxes = [layer.bbox for layer in layers if layer.bbox is not None]
    if not bboxes:
        return None

    lefts, tops, rights, bottoms = zip(*bboxes)
    return BBox(min(lefts), min(tops), max(rights), max(bottoms))


class _RootGroup(Group):
    """ A fake group for holding all layers """

    @property
    def visible(self):
        return True
