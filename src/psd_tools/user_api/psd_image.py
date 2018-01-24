# -*- coding: utf-8 -*-
from __future__ import (
    absolute_import, unicode_literals, division, print_function)

import logging
import weakref              # FIXME: there should be weakrefs in this module
import psd_tools.reader
import psd_tools.decoder
from psd_tools.constants import (
    TaggedBlock, SectionDivider, BlendMode, TextProperty, PlacedLayerProperty,
    SzProperty, ImageResourceID, PathResource)
from psd_tools.user_api import pymaging_support
from psd_tools.user_api import pil_support
from psd_tools.user_api import BBox, Pattern
from psd_tools.user_api.mask import Mask
from psd_tools.user_api.embedded import Embedded
from psd_tools.user_api.effects import get_effects

logger = logging.getLogger(__name__)


class _RawLayer(object):
    """
    Layer groups and layers are internally both 'layers' in PSD;
    they share some common properties.
    """
    def __init__(self, parent, index):
        self._parent = parent
        self._psd = parent._psd if parent else self
        self._index = index
        self._clip_layers = []

    @property
    def name(self):
        """Layer name (as unicode). """
        return self._tagged_blocks.get(TaggedBlock.UNICODE_LAYER_NAME,
                                       self._info.name)

    @property
    def kind(self):
        """
        Kind of this layer, either group, pixel, shape, type, smartobject, or
        psdimage (root object).
        """
        return self.__class__.__name__.lower().replace("layer", "")

    @property
    def visible(self):
        """Layer visibility. Doesn't take group visibility in account."""
        return self._info.flags.visible

    @property
    def visible_global(self):
        """Layer visibility. Takes group visibility in account."""
        return self.visible and self.parent.visible_global

    def has_box(self):
        info = self._info
        return info.left < info.right and info.top < info.bottom

    @property
    def layer_id(self):
        """ID of the layer."""
        return self._tagged_blocks.get(TaggedBlock.LAYER_ID)

    @property
    def opacity(self):
        """Opacity of this layer."""
        return self._info.opacity

    @property
    def parent(self):
        """Parent of this layer."""
        return self._parent

    @property
    def blend_mode(self):
        """Blend mode of this layer."""
        return self._info.blend_mode

    def has_mask(self):
        """Returns if the layer has a mask."""
        return True if self._index and self._info.mask_data else False

    """PSD base layer."""
    def as_PIL(self):
        """Returns a PIL image for this layer."""
        return self._psd._layer_as_PIL(self._index)

    def as_pymaging(self):
        """Returns a pymaging.Image for this PSD file."""
        return self._psd._layer_as_pymaging(self._index)

    @property
    def bbox(self):
        """BBox(x1, y1, x2, y2) namedtuple with layer bounding box."""
        info = self._info
        return BBox(info.left, info.top, info.right, info.bottom)

    @property
    def mask(self):
        """
        Returns mask associated with this layer.

        :rtype: Mask
        """
        return Mask(self) if self.has_mask() else None

    @property
    def clip_layers(self):
        """
        Returns clip layers associated with this layer.

        :rtype: list
        """
        return self._clip_layers

    @property
    def effects(self):
        """
        Effects associated with this layer.

        :rtype: psd_tools.user_api.effects.Effects
        """
        return get_effects(self)

    @property
    def _info(self):
        return self._psd._layer_info(self._index)

    @property
    def _tagged_blocks(self):
        return dict(self._info.tagged_blocks)

    def __repr__(self):
        bbox = self.bbox
        return (
            "<%s: %r, size=%dx%d, x=%d, y=%d, visible=%d, mask=%s, "
            "effects=%s>" % (
                self.kind, self.name, bbox.width, bbox.height,
                bbox.x1, bbox.y1, self.visible, self.mask, self.effects))


class Group(_RawLayer):
    """PSD layer group."""

    def __init__(self, parent, index):
        super(Group, self).__init__(parent, index)
        self._layers = []


    @property
    def closed(self):
        divider = self._divider
        if divider is None:
            return None
        return divider.type == SectionDivider.CLOSED_FOLDER

    @property
    def bbox(self):
        """
        BBox(x1, y1, x2, y2) namedtuple with a bounding box for
        all layers in this group; None if a group has no children.
        """
        return combined_bbox(self.layers)

    @property
    def layers(self):
        """
        Return a list of child layers in this group.
        """
        return self._layers

    def descendants(self, include_clip=True):
        """
        Return a generator to iterate over all descendant layers.
        """
        for layer in self._layers:
            yield layer
            if layer.kind == "group":
                for child in layer.descendants(include_clip):
                    yield child
            if include_clip:
                for clip_layer in layer.clip_layers:
                    yield clip_layer

    def as_PIL(self, **kwargs):
        """
        Returns a PIL image for this group.
        This is highly experimental.
        """
        return merge_layers(self.layers, **kwargs)

    @property
    def _divider(self):
        blocks = self._tagged_blocks
        return blocks.get(
            TaggedBlock.SECTION_DIVIDER_SETTING,
            blocks.get(TaggedBlock.NESTED_SECTION_DIVIDER_SETTING),
        )

    def __repr__(self):
        return "<%s: %r, layer_count=%d, mask=%s, visible=%d>" % (
            self.kind, self.name, len(self.layers), self.mask,
            self.visible)


class PSDImage(Group):
    """PSD image."""

    def __init__(self, decoded_data):
        super(PSDImage, self).__init__(None, None)
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

            elif blocks.get(TaggedBlock.TYPE_TOOL_OBJECT_SETTING):
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

    def as_PIL(self, fallback=True):
        """Returns a PIL image for this PSD file."""
        if not self.has_preview() and fallback:
            logger.warning("Rendering PIL")
            return self.as_PIL_merged()
        return pil_support.extract_composite_image(self.decoded_data)

    def as_PIL_merged(self):
        """
        Returns a PIL image for this PSD file.
        Image is obtained by merging all layers.
        This is highly experimental.
        """
        bbox = BBox(0, 0, self.header.width, self.header.height)
        return merge_layers(self.layers, bbox=bbox)

    def has_preview(self):
        """Returns if the image has a preview."""
        version_info = self._image_resource_blocks.get("version_info")
        return not version_info or version_info.has_real_merged_data

    def as_pymaging(self):
        """Returns a pymaging.Image for this PSD file."""
        return pymaging_support.extract_composite_image(self.decoded_data)

    @property
    def name(self):
        return "root"

    @property
    def visible(self):
        return True

    @property
    def visible_global(self):
        return True

    @property
    def header(self):
        return self.decoded_data.header

    @property
    def embedded(self):
        return {linked.unique_id: Embedded(linked) for linked in
                self._linked_layer_iter()}

    @property
    def patterns(self):
        """Returns a dict of pattern (texture) data in PIL.Image."""
        blocks = self._tagged_blocks
        patterns = blocks.get(
            TaggedBlock.PATTERNS1,
            blocks.get(
                TaggedBlock.PATTERNS2,
                blocks.get(TaggedBlock.PATTERNS3, [])))
        return {p.pattern_id: Pattern(p) for p in patterns}

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
            if isinstance(l, Group):
                self.print_tree(l.layers, indent + indent_width, **kwargs)

    def thumbnail(self):
        """
        Returns a thumbnail image in PIL.Image. When the file does not
        contain an embedded thumbnail image, returns None.
        """
        blocks = self._image_resource_blocks
        thumbnail_resource = blocks.get("thumbnail_resource")
        if thumbnail_resource:
            return pil_support.extract_thumbnail(thumbnail_resource)
        else:
            thumbnail_resource = blocks.get("thumbnail_resource_ps4")
            if thumbnail_resource:
                return pil_support.extract_thumbnail(thumbnail_resource,
                                                     "BGR")
        return None

    @property
    def _tagged_blocks(self):
        return dict(self.decoded_data.layer_and_mask_data.tagged_blocks)

    @property
    def _image_resource_blocks(self):
        return {ImageResourceID.name_of(block.resource_id).lower(): block.data
                for block in self.decoded_data.image_resource_blocks}

    def _layer_info(self, index):
        layers = self.decoded_data.layer_and_mask_data.layers.layer_records
        return layers[index]

    def _layer_as_PIL(self, index):
        return pil_support.extract_layer_image(self.decoded_data, index)

    def _layer_as_pymaging(self, index):
        return pymaging_support.extract_layer_image(self.decoded_data, index)

    def _linked_layer_iter(self):
        """Iterate over linked layers (smart objects / embedded files)."""
        from psd_tools.decoder.linked_layer import LinkedLayerCollection
        for data in self._tagged_blocks.values():
            if isinstance(data, LinkedLayerCollection):
                for layer in data.linked_list:
                    yield layer

    def __repr__(self):
        return "<%s: size=%dx%d, layer_count=%d>" % (
            self.kind, self.header.width, self.header.height,
            len(self.layers))


class AdjustmentLayer(_RawLayer):
    """PSD adjustment layer wrapper."""
    def __repr__(self):
        return "<%s: %r, visible=%s>" % (
            self.kind, self.name, self.visible)


class PixelLayer(_RawLayer):
    """PSD pixel layer wrapper."""
    pass


class ShapeLayer(_RawLayer):
    """PSD shape layer wrapper."""

    def as_PIL(self, vector=False):
        """Returns a PIL image for this layer."""
        if vector or (self._info.flags.pixel_data_irrelevant and
                      not self.has_box()):
            # TODO: Replace polygon with bezier curve.
            return pil_support.draw_polygon(self.bbox, self.get_anchors(),
                                            self._get_color())
        else:
            return self._psd._layer_as_PIL(self._index)

    @property
    def bbox(self):
        """BBox(x1, y1, x2, y2) namedtuple of the shape."""
        if self.has_box():
            return super(ShapeLayer, self).bbox

        # TODO: Compute bezier curve.
        anchors = self.get_anchors()
        if not anchors or len(anchors) < 2:
            # Could be all pixel fill.
            return BBox(0, 0, 0, 0)
        return BBox(min([p[0] for p in anchors]),
                    min([p[1] for p in anchors]),
                    max([p[0] for p in anchors]),
                    max([p[1] for p in anchors]))

    def get_anchors(self):
        """Anchor points of the shape [(x, y), (x, y), ...]."""
        blocks = self._tagged_blocks
        vmsk = blocks.get(TaggedBlock.VECTOR_MASK_SETTING1,
                          blocks.get(TaggedBlock.VECTOR_MASK_SETTING2))
        if not vmsk:
            return None
        width, height = self._psd.header.width, self._psd.header.height
        knot_types = (
            PathResource.CLOSED_SUBPATH_BEZIER_KNOT_LINKED,
            PathResource.CLOSED_SUBPATH_BEZIER_KNOT_UNLINKED,
            PathResource.OPEN_SUBPATH_BEZIER_KNOT_LINKED,
            PathResource.OPEN_SUBPATH_BEZIER_KNOT_UNLINKED
        )
        return [(int(p["anchor"][1] * width), int(p["anchor"][0] * height))
                for p in vmsk.path if p.get("selector") in knot_types]

    def _get_color(self, default='black'):
        soco = self._tagged_blocks.get(TaggedBlock.SOLID_COLOR_SHEET_SETTING)
        if not soco:
            logger.warning("Gradient or pattern fill not supported")
            return default
        color_data = dict(soco.data.items).get(b'Clr ')
        if color_data.classID == b'RGBC':
            colors = dict(color_data.items)
            return (int(colors[b'Rd  '].value), int(colors[b'Grn '].value),
                    int(colors[b'Bl  '].value), int(self.opacity))
        else:
            return default


class SmartObjectLayer(_RawLayer):
    """PSD smartobject layer wrapper."""
    def __init__(self, parent, index):
        super(SmartObjectLayer, self).__init__(parent, index)
        self._block = self._get_block()

    @property
    def unique_id(self):
        return (self._block.get(PlacedLayerProperty.ID).value
                if self._block else None)

    @property
    def placed_bbox(self):
        """
        BBox(x1, y1, x2, y2) with transformed box. The tranform of a layer
        the points for all 4 corners.
        """
        if self._block:
            transform = self._block.get(PlacedLayerProperty.TRANSFORM).items
            return BBox(transform[0].value, transform[1].value,
                        transform[4].value, transform[5].value)
        else:
            return None

    @property
    def object_bbox(self):
        """
        BBox(x1, y1, x2, y2) with original object content coordinates.
        """
        if self._block:
            size = dict(self._block.get(PlacedLayerProperty.SIZE).items)
            return BBox(0, 0,
                        size[SzProperty.WIDTH].value,
                        size[SzProperty.HEIGHT].value)
        else:
            return None

    @property
    def linked_data(self):
        """
        Return linked layer data.
        """
        return self._psd.embedded.get(self.unique_id)

    def _get_block(self):
        blocks = self._tagged_blocks
        block = None
        for key in (TaggedBlock.SMART_OBJECT_PLACED_LAYER_DATA,
                    TaggedBlock.PLACED_LAYER_DATA,
                    TaggedBlock.PLACED_LAYER_OBSOLETE1,
                    TaggedBlock.PLACED_LAYER_OBSOLETE2):
            block = blocks.get(key)
            if block:
                break

        if not block:
            logger.warning("Empty smartobject")
            return None

        return dict(block)

    def __repr__(self):
        bbox = self.bbox
        return (
            "<%s: %r, size=%dx%d, x=%d, y=%d, mask=%s, visible=%d, "
            "linked=%s>") % (
            self.__class__.__name__, self.name, bbox.width, bbox.height,
            bbox.x1, bbox.y1, self.mask, self.visible,
            self.linked_data)


class TypeLayer(_RawLayer):
    """
    PSD type layer.

    A type layer has text information such as fonts and paragraph settings.
    """
    def __init__(self, parent, index):
        super(TypeLayer, self).__init__(parent, index)
        self._type_info = self._tagged_blocks.get(
            TaggedBlock.TYPE_TOOL_OBJECT_SETTING)
        self.text_data = dict(self._type_info.text_data.items)

    @property
    def text(self):
        """Unicode string."""
        return self.text_data[TextProperty.TXT].value

    @property
    def matrix(self):
        """Matrix [xx xy yx yy tx ty] applies affine transformation."""
        return (self._type_info.xx, self._type_info.xy, self._type_info.yx,
                self._type_info.yy, self._type_info.tx, self._type_info.ty)

    @property
    def engine_data(self):
        """Type information in engine data format."""
        return self.text_data.get(b'EngineData')

    @property
    def fontset(self):
        """Font set."""
        return self.engine_data[b'DocumentResources'][b'FontSet']

    @property
    def writing_direction(self):
        """Writing direction."""
        return self.engine_data[b'EngineDict'][
            b'Rendered'][b'Shapes'][b'WritingDirection']

    @property
    def full_text(self):
        """Raw string including trailing newline."""
        return self.engine_data[b'EngineDict'][b'Editor'][b'Text']

    def style_spans(self):
        """Returns spans by text style segments."""
        text = self.full_text
        fontset = self.fontset
        engine_data = self.engine_data
        runlength = engine_data[b'EngineDict'][b'StyleRun'][b'RunLengthArray']
        runarray = engine_data[b'EngineDict'][b'StyleRun'][b'RunArray']

        start = 0
        spans = []
        for run, size in zip(runarray, runlength):
            runtext = text[start:start + size]
            stylesheet = run[b'StyleSheet'][b'StyleSheetData'].copy()
            stylesheet[b'Text'] = runtext
            stylesheet[b'Font'] = fontset[stylesheet.get(b'Font', 0)]
            spans.append(stylesheet)
            start += size
        return spans


def combined_bbox(layers):
    """
    Returns a bounding box for ``layers`` or None if this is not possible.
    """
    bboxes = [layer.bbox for layer in layers
              if layer.bbox is not None and
              layer.bbox.width > 0 and layer.bbox.height > 0]
    if not bboxes:
        return None

    lefts, tops, rights, bottoms = zip(*bboxes)
    return BBox(min(lefts), min(tops), max(rights), max(bottoms))


def merge_layers(layers, respect_visibility=True, ignore_blend_mode=True,
                 skip_layer=lambda layer: False, bbox=None):
    """
    Merges layers together (the first layer is on top).

    By default hidden layers are not rendered;
    pass ``respect_visibility=False`` to render them.

    In order to skip some layers pass ``skip_layer`` function which
    should take ``layer`` as an argument and return True or False.

    If ``bbox`` is not None, it should be a 4-tuple with coordinates;
    returned image will be restricted to this rectangle.

    This is highly experimental.
    """

    # FIXME: this currently assumes PIL
    from PIL import Image

    if bbox is None:
        bbox = combined_bbox(layers)

    if bbox is None:
        return None

    result = Image.new(
        "RGBA",
        (bbox.width, bbox.height),
        color=(255, 255, 255, 0)  # fixme: transparency is incorrect
    )

    for layer in reversed(layers):

        if layer is None:
            continue

        if not layer.bbox or (
            layer.bbox.width == 0 and layer.bbox.height == 0):
            continue

        if skip_layer(layer):
            continue

        if not layer.visible and respect_visibility:
            continue

        if layer.kind == "group":
            layer_image = merge_layers(
                layer.layers, respect_visibility, ignore_blend_mode,
                skip_layer)
        else:
            layer_image = layer.as_PIL()

        if not layer_image:
            continue

        if not ignore_blend_mode and layer.blend_mode != BlendMode.NORMAL:
            logger.warning("Blend mode is not implemented: %s",
                           BlendMode.name_of(layer.blend_mode))
            continue

        if len(layer.clip_layers):
            clip_box = combined_bbox(layer.clip_layers)
            if clip_box:
                intersect = clip_box.intersect(layer.bbox)
                if intersect:
                    clip_image = merge_layers(
                        layer.clip_layers, respect_visibility,
                        ignore_blend_mode, skip_layer)
                    clip_image = clip_image.crop(
                        intersect.offset((clip_box.x1, clip_box.y1)))
                    clip_mask = layer_image.crop(
                        intersect.offset((layer.bbox.x1, layer.bbox.y1)))

        layer_image = pil_support.apply_opacity(layer_image, layer.opacity)

        x, y = layer.bbox.x1 - bbox.x1, layer.bbox.y1 - bbox.y1
        w, h = layer_image.size

        if x < 0 or y < 0:  # image doesn't fit the bbox
            x_overflow = - min(x, 0)
            y_overflow = - min(y, 0)
            logger.debug("cropping.. (%s, %s)", x_overflow, y_overflow)
            layer_image = layer_image.crop((x_overflow, y_overflow, w, h))
            x += x_overflow
            y += y_overflow

        if w+x > bbox.width or h+y > bbox.height:
            # FIXME
            logger.debug("cropping..")

        if layer_image.mode == 'RGBA':
            tmp = Image.new("RGBA", result.size, color=(255, 255, 255, 0))
            tmp.paste(layer_image, (x, y))
            result = Image.alpha_composite(result, tmp)
        elif layer_image.mode == 'RGB':
            result.paste(layer_image, (x, y))
        else:
            logger.warning(
                "layer image mode is unsupported for merging: %s",
                layer_image.mode)
            continue

        if 'clip_mask' in locals():
            location = (intersect.x1 - bbox.x1, intersect.y1 - bbox.y1)
            if clip_image.mode == 'RGBA':
                tmp = Image.new("RGBA", result.size, color=(255, 255, 255, 0))
                tmp.paste(clip_image, location, mask=clip_mask)
                result = Image.alpha_composite(result, tmp)
            elif clip_image.mode == 'RGB':
                result.paste(clip_image, location, mask=clip_mask)

    return result
