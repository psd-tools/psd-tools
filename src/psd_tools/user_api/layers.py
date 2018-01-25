# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import logging
from psd_tools.constants import (
    TaggedBlock, SectionDivider, BlendMode, TextProperty, PlacedLayerProperty,
    SzProperty, PathResource)
from psd_tools.user_api import pil_support
from psd_tools.user_api import BBox
from psd_tools.user_api.mask import Mask
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
                                       self._record.name)

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
        return self._record.flags.visible

    def is_visible(self):
        """Layer visibility. Takes group visibility in account."""
        return self.visible and self.parent.is_visible()

    def is_group(self):
        """Return True if the layer is a group."""
        return isinstance(self, Group)

    @property
    def layer_id(self):
        """ID of the layer."""
        return self._tagged_blocks.get(TaggedBlock.LAYER_ID)

    @property
    def opacity(self):
        """Opacity of this layer."""
        return self._record.opacity

    @property
    def parent(self):
        """Parent of this layer."""
        return self._parent

    @property
    def blend_mode(self):
        """Blend mode of this layer."""
        return self._record.blend_mode

    def has_mask(self):
        """Returns if the layer has a mask."""
        return True if self._index and self._record.mask_data else False

    def as_PIL(self):
        """Returns a PIL.Image for this layer."""
        if self.has_pixels():
            return self._psd._layer_as_PIL(self._index)
        else:
            return None

    def as_pymaging(self):
        """Returns a pymaging.Image for this layer."""
        if self.has_pixels():
            return self._psd._layer_as_pymaging(self._index)
        else:
            return None

    @property
    def bbox(self):
        """BBox(x1, y1, x2, y2) namedtuple with layer bounding box."""
        info = self._record
        return BBox(info.left, info.top, info.right, info.bottom)

    def has_box(self):
        """Return True if the layer has a nonzero area."""
        info = self._record
        return info.left < info.right and info.top < info.bottom

    def has_pixels(self):
        """Return True if the layer has associated pixels."""
        return all(c.data and len(c.data) > 0 for c in self._channels)

    @property
    def mask(self):
        """
        Returns mask associated with this layer.

        :rtype: psd_tools.user_api.mask.Mask
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
        """(Deprecated) Use `_record()`."""
        return self._record

    @property
    def _record(self):
        """Returns the underlying layer record."""
        return self._psd._layer_records(self._index)

    @property
    def _channels(self):
        """Returns the underlying layer channel images."""
        return self._psd._layer_channels(self._index)

    @property
    def _tagged_blocks(self):
        """Returns the underlying tagged blocks structure."""
        return dict(self._record.tagged_blocks)

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

    def has_box(self):
        """Return True if the layer has a nonzero area."""
        return any(l.has_box() for l in self.descendants())

    @property
    def layers(self):
        """
        Return a list of child layers in this group.

        :rtype: list
        """
        return self._layers

    def descendants(self, include_clip=True):
        """
        Return a generator to iterate over all descendant layers.
        """
        for layer in self._layers:
            yield layer
            if layer.is_group():
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
        if vector or (self._record.flags.pixel_data_irrelevant and
                      not self.has_box()):
            # TODO: Replace polygon with bezier curve.
            return pil_support.draw_polygon(self.bbox, self.get_anchors(),
                                            self._get_color())
        else:
            return self._psd._layer_as_PIL(self._index)

    @property
    def bbox(self, vector=False):
        """BBox(x1, y1, x2, y2) namedtuple of the shape."""
        if vector:
            # TODO: Compute bezier curve.
            anchors = self.get_anchors()
            if not anchors or len(anchors) < 2:
                # Could be all pixel fill.
                return BBox(0, 0, 0, 0)
            return BBox(min([p[0] for p in anchors]),
                        min([p[1] for p in anchors]),
                        max([p[0] for p in anchors]),
                        max([p[1] for p in anchors]))
        else:
            return super(ShapeLayer, self).bbox

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

    This is experimental.
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

        if not layer.has_box():
            continue

        if skip_layer(layer):
            continue

        if not layer.visible and respect_visibility:
            continue

        if layer.is_group():
            layer_image = layer.as_PIL(
                respect_visibility=respect_visibility,
                ignore_blend_mode=ignore_blend_mode,
                skip_layer=skip_layer)
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
