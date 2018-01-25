# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, print_function

import logging
# import weakref              # FIXME: there should be weakrefs in this module
import psd_tools.reader
import psd_tools.decoder
from psd_tools.constants import TaggedBlock, SectionDivider, ImageResourceID
from psd_tools.user_api import pymaging_support
from psd_tools.user_api import pil_support
from psd_tools.user_api import BBox, Pattern
from psd_tools.user_api.smart_object import SmartObject
from psd_tools.user_api.layers import (
    Group, AdjustmentLayer, TypeLayer, ShapeLayer, SmartObjectLayer,
    PixelLayer)

logger = logging.getLogger(__name__)


class _PSDImageBuilder(object):
    """Mixin for PSDImage building."""

    def build(self, decoded_data):
        """Build the tree structure."""
        self.decoded_data = decoded_data
        layer_records = decoded_data.layer_and_mask_data.layers.layer_records

        group_stack = [self]
        clip_stack = []

        for index, record in reversed(list(enumerate(layer_records))):
            current_group = group_stack[-1]
            blocks = dict(record.tagged_blocks)

            divider = blocks.get(
                TaggedBlock.SECTION_DIVIDER_SETTING,
                blocks.get(TaggedBlock.NESTED_SECTION_DIVIDER_SETTING),
            )
            if divider:
                if divider.type in (SectionDivider.CLOSED_FOLDER,
                                    SectionDivider.OPEN_FOLDER):
                    layer = Group(current_group, index)
                    group_stack.append(layer)

                elif divider.type == SectionDivider.BOUNDING_SECTION_DIVIDER:
                    if len(group_stack) == 1:
                        # This means that there is a BOUNDING_SECTION_DIVIDER
                        # without an OPEN_FOLDER before it. Create a new group
                        # and move layers to this new group in this case.

                        # Assume the first layer is a group
                        # and convert it to a group:
                        layers = group_stack[0].layers[0]
                        group = Group(current_group, layers[0]._index)
                        group._layers = layers[1:]

                        # replace moved layers with newly created group:
                        group_stack[0].layers = [group]
                    else:
                        assert group_stack.pop() is not self
                    continue
                else:
                    logger.warn("Invalid state")

            elif TaggedBlock.TYPE_TOOL_OBJECT_SETTING in blocks:
                layer = TypeLayer(current_group, index)

            elif (TaggedBlock.VECTOR_ORIGINATION_DATA in blocks or
                  TaggedBlock.VECTOR_MASK_SETTING1 in blocks or
                  TaggedBlock.VECTOR_MASK_SETTING2 in blocks or
                  TaggedBlock.VECTOR_STROKE_DATA in blocks or
                  TaggedBlock.VECTOR_STROKE_CONTENT_DATA in blocks):
                layer = ShapeLayer(current_group, index)

            elif (TaggedBlock.SMART_OBJECT_PLACED_LAYER_DATA in blocks or
                  TaggedBlock.PLACED_LAYER_OBSOLETE2 in blocks or
                  TaggedBlock.PLACED_LAYER_DATA in blocks):
                layer = SmartObjectLayer(current_group, index)

            elif any([TaggedBlock.is_adjustment_key(key) or
                      TaggedBlock.is_fill_key(key)
                      for key in blocks.keys()]):
                layer = AdjustmentLayer(current_group, index)

            else:
                layer = PixelLayer(current_group, index)

            if record.clipping:
                clip_stack.append(layer)
            else:
                layer._clip_layers = clip_stack
                clip_stack = []
                current_group._layers.append(layer)


class PSDImage(Group, _PSDImageBuilder):
    """PSD image."""

    def __init__(self, decoded_data):
        super(PSDImage, self).__init__(None, None)
        self._smart_objects = None
        self._patterns = None
        self._image_resource_blocks = None
        self.build(decoded_data)

    @classmethod
    def load(cls, path, encoding='utf8'):
        """Returns a new :class:`PSDImage` loaded from ``path``."""
        with open(path, 'rb') as fp:
            return cls.from_stream(fp, encoding)

    @classmethod
    def from_stream(cls, fp, encoding='utf8'):
        """Returns a new :class:`PSDImage` loaded from stream ``fp``."""
        decoded_data = psd_tools.decoder.parse(
            psd_tools.reader.parse(fp, encoding)
        )
        return cls(decoded_data)

    def as_PIL(self, render=False, **kwargs):
        """
        Returns a PIL image for this PSD file.

        :param render: Force rendering the view if True
        :returns: PIL Image
        """
        if render or not self.has_preview():
            bbox = BBox(0, 0, self.header.width, self.header.height)
            return super(PSDImage, self).as_PIL(bbox=bbox, **kwargs)
        return pil_support.extract_composite_image(self.decoded_data)

    def as_PIL_merged(self, **kwargs):
        """
        (Deprecated) Returns a PIL image with forced rendering.
        """
        return self.as_PIL(render=True, **kwargs)

    def has_preview(self):
        """Returns if the image has a preview."""
        version_info = self.image_resource_blocks.get("version_info")
        return self.has_pixels() and (
            not version_info or version_info.has_real_merged_data)

    def has_pixels(self):
        """Return True if the image has associated pixels."""
        return all(c.data and len(c.data) > 0
                   for c in self.decoded_data.image_data)

    def as_pymaging(self):
        """Returns a pymaging.Image for this PSD file."""
        return pymaging_support.extract_composite_image(self.decoded_data)

    @property
    def name(self):
        """Layer name as unicode. PSDImage is 'root'."""
        return "root"

    @property
    def mask(self):
        """Returns mask associated with this layer. PSDImage returns `None`."""
        return None

    @property
    def visible(self):
        """
        Visiblity flag of this layer. PSDImage is always visible.

        :returns: True
        """
        return True

    def is_visible(self):
        """
        Layer visibility. PSDImage is always visible.

        :returns: True
        """
        return True

    @property
    def header(self):
        """Header section of the underlying PSD data."""
        return self.decoded_data.header

    @property
    def width(self):
        """Width of the image."""
        return self.decoded_data.header.width

    @property
    def height(self):
        """Height of the image."""
        return self.decoded_data.header.height

    @property
    def embedded(self):
        """(Deprecated) Use `smart_objects`."""
        return self.smart_objects

    @property
    def smart_objects(self):
        """Dict of the smart objects."""
        if not self._smart_objects:
            links = self.get_tag([
                TaggedBlock.LINKED_LAYER1,
                TaggedBlock.LINKED_LAYER2,
                TaggedBlock.LINKED_LAYER3,
                TaggedBlock.LINKED_LAYER_EXTERNAL
            ])
            if links:
                self._smart_objects = {item.unique_id: SmartObject(item)
                                       for item in links.linked_list}
            else:
                self._smart_objects = {}
        return self._smart_objects

    @property
    def patterns(self):
        """Returns a dict of pattern (texture) data in PIL.Image."""
        if not self._patterns:
            patterns = self.get_tag([TaggedBlock.PATTERNS1,
                                     TaggedBlock.PATTERNS2,
                                     TaggedBlock.PATTERNS3],
                                    [])
            self._patterns = {p.pattern_id: Pattern(p) for p in patterns}
        return self._patterns

    def print_tree(self, layers=None, indent=0, indent_width=2, **kwargs):
        """Print the layer tree structure."""
        if not layers:
            layers = self.layers
            print(((' ' * indent) + "{}").format(self), **kwargs)
            indent = indent + indent_width
        for l in layers:
            for clip in l.clip_layers:
                print(((' ' * indent) + "/{}").format(clip), **kwargs)
            print(((' ' * indent) + "{}").format(l), **kwargs)
            if l.is_group():
                self.print_tree(l.layers, indent + indent_width, **kwargs)

    def thumbnail(self):
        """
        Returns a thumbnail image in PIL.Image. When the file does not
        contain an embedded thumbnail image, returns None.
        """
        if "thumbnail_resource" in self.image_resource_blocks:
            return pil_support.extract_thumbnail(
                self.image_resource_blocks["thumbnail_resource"])
        elif "thumbnail_resource_ps4" in self.image_resource_blocks:
            return pil_support.extract_thumbnail(
                self.image_resource_blocks["thumbnail_resource_ps4"], "BGR")
        return None

    @property
    def tagged_blocks(self):
        """Returns dict of the underlying tagged blocks."""
        if not self._tagged_blocks:
            self._tagged_blocks = dict(
                self.decoded_data.layer_and_mask_data.tagged_blocks)
        return self._tagged_blocks

    @property
    def image_resource_blocks(self):
        """Returns dict of the underlying image resource blocks."""
        if not self._image_resource_blocks:
            self._image_resource_blocks = {
                ImageResourceID.name_of(block.resource_id).lower(): block.data
                for block in self.decoded_data.image_resource_blocks
            }
        return self._image_resource_blocks

    def _layer_records(self, index):
        records = self.decoded_data.layer_and_mask_data.layers.layer_records
        return records[index]

    def _layer_channels(self, index):
        data = self.decoded_data.layer_and_mask_data.layers.channel_image_data
        return data[index]

    def _layer_as_PIL(self, index):
        return pil_support.extract_layer_image(self.decoded_data, index)

    def _layer_as_pymaging(self, index):
        return pymaging_support.extract_layer_image(self.decoded_data, index)

    def __repr__(self):
        return "<%s: size=%dx%d, layer_count=%d>" % (
            self.kind, self.header.width, self.header.height,
            len(self.layers))
