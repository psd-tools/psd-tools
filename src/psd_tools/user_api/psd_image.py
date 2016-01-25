# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, division

import logging
import weakref              # FIXME: there should be weakrefs in this module
from collections import namedtuple

import psd_tools.reader
import psd_tools.decoder
from psd_tools.constants import TaggedBlock, SectionDivider, BlendMode, TextProperty, PlacedLayerProperty, SzProperty
from psd_tools.user_api import pil_support, pymaging_support
from psd_tools.user_api.layers import group_layers
from psd_tools.user_api.embedded import Embedded

try:
    from psd_tools.user_api import _blend_modes
except ImportError:
    _blend_modes = None

logger = logging.getLogger(__name__)


Size = namedtuple('Size', 'width, height')


class BBox(namedtuple('BBox', 'x1, y1, x2, y2')):

    @property
    def width(self):
        return self.x2 - self.x1

    @property
    def height(self):
        return self.y2 - self.y1


class TextData(object):

    def __init__(self, tagged_blocks):
        text_data = dict(tagged_blocks.text_data.items)
        self.text = text_data[TextProperty.TXT].value


class PlacedLayerData(object):

    def __init__(self, placed_layer_block):
        placed_layer_data = dict(placed_layer_block)
        self.transform = placed_layer_data[PlacedLayerProperty.TRANSFORM].items
        self.size = dict(placed_layer_data[PlacedLayerProperty.SIZE].items)


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
        """ Layer visibility. Doesn't take group visibility in account. """
        return self._info.flags.visible

    @property
    def visible_global(self):
        """ Layer visibility. Takes group visibility in account. """
        return self.visible and self.parent.visible_global

    @property
    def layer_id(self):
        return self._tagged_blocks.get(TaggedBlock.LAYER_ID)

    @property
    def opacity(self):
        return self._info.opacity

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
    def fill(self):
        return self._tagged_blocks.get(TaggedBlock.FILL_OPACITY, 255)

    @property
    def blend_mode(self):
        return self._info.blend_mode

    @property
    def bbox(self):
        """ BBox(x1, y1, x2, y2) namedtuple with layer bounding box. """
        info = self._info
        return BBox(info.left, info.top, info.right, info.bottom)

    @property
    def transform_bbox(self):
        """
        BBox(x1, y1, x2, y2) namedtuple with layer transform box
        (Top Left and Bottom Right corners). The tranform of a layer the
        points for all 4 corners.
        """
        placed_layer_block = self._placed_layer_block()
        if not placed_layer_block:
            return None
        placed_layer_data = PlacedLayerData(placed_layer_block)

        transform = placed_layer_data.transform
        if not transform:
            return None
        return BBox(
            transform[0].value, transform[1].value,
            transform[4].value, transform[5].value
        )

    @property
    def placed_layer_size(self):
        """
        BBox(x1, y1, x2, y2) namedtuple with original
        smart object content size.
        """
        placed_layer_block = self._placed_layer_block()
        if not placed_layer_block:
            return None
        placed_layer_data = PlacedLayerData(placed_layer_block)

        size = placed_layer_data.size
        if not size:
            return None
        return Size(size[SzProperty.WIDTH].value, size[SzProperty.HEIGHT].value)

    def _placed_layer_block(self):
        so_layer_block = self._tagged_blocks.get(TaggedBlock.SMART_OBJECT_PLACED_LAYER_DATA)
        return self._tagged_blocks.get(TaggedBlock.PLACED_LAYER_DATA, so_layer_block)

    @property
    def text_data(self):
        tagged_blocks = self._tagged_blocks.get(TaggedBlock.TYPE_TOOL_OBJECT_SETTING)
        if tagged_blocks:
            return TextData(tagged_blocks)

    def __repr__(self):
        bbox = self.bbox
        return "<psd_tools.Layer: %r, size=%dx%d, x=%d, y=%d>" % (
            self.name, bbox.width, bbox.height, bbox.x1, bbox.y1
        )


class Group(_RawLayer):
    """ PSD layer group wrapper """

    def __init__(self, parent, index, layers):
        self.parent = parent
        self._psd = parent._psd
        self._index = index
        self.layers = layers

    @property
    def blend_mode(self):
        blocks = self._tagged_blocks
        divider = blocks.get(
            TaggedBlock.SECTION_DIVIDER_SETTING,
            blocks.get(TaggedBlock.NESTED_SECTION_DIVIDER_SETTING)
        )

        if divider is None or divider.blend_mode is None:
            return self._info.blend_mode
        return divider.blend_mode

    @property
    def closed(self):
        blocks = self._tagged_blocks
        divider = blocks.get(
            TaggedBlock.SECTION_DIVIDER_SETTING,
            blocks.get(TaggedBlock.NESTED_SECTION_DIVIDER_SETTING)
        )

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

    def as_PIL(self, use_global_bbox=False):
        """
        Returns a PIL image for this group.
        This is highly experimental.
        """
        if use_global_bbox:
            bbox = BBox(0, 0, self._psd.header.width, self._psd.header.height)
            merged_image = merge_layers(self.layers, bbox=bbox)
        else:
            merged_image = merge_layers(self.layers)
        return pil_support.try_remove_alpha(merged_image)

    def _add_layer(self, child):
        self.layers.append(child)

    def __repr__(self):
        return "<psd_tools.Group: %r, layer_count=%d>" % (
            self.name, len(self.layers)
        )


class _RootGroup(Group):
    """ A fake group for holding all layers """

    @property
    def visible(self):
        return True

    @property
    def visible_global(self):
        return True

    @property
    def name(self):
        return "_RootGroup"


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
        self.embedded = [Embedded(linked) for linked in self._linked_layer_iter()]

    @classmethod
    def load(cls, path, encoding='latin1'):
        """
        Returns a new :class:`PSDImage` loaded from ``path``.
        """
        with open(path, 'rb') as fp:
            return cls.from_stream(fp, encoding)

    @classmethod
    def from_stream(cls, fp, encoding='latin1'):
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
        return pil_support.extract_composite_image(self.decoded_data)

    def as_PIL_merged(self):
        """
        Returns a PIL image for this PSD file.
        Image is obtained by merging all layers.
        This is highly experimental.
        """
        bbox = BBox(0, 0, self.header.width, self.header.height)
        merged_image = merge_layers(self.layers, bbox=bbox)
        return pil_support.try_remove_alpha(merged_image)

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
        return combined_bbox(self.layers)

    def _layer_info(self, index):
        layers = self.decoded_data.layer_and_mask_data.layers.layer_records
        return layers[index]

    def _layer_as_PIL(self, index):
        return pil_support.extract_layer_image(self.decoded_data, index)

    def _layer_as_pymaging(self, index):
        return pymaging_support.extract_layer_image(self.decoded_data, index)

    def _linked_layer_iter(self):
        """
        Iterate over linked layers (smart objects / embedded files)
        """
        from psd_tools.decoder.linked_layer import LinkedLayerCollection
        for block in self.decoded_data.layer_and_mask_data.tagged_blocks:
            if isinstance(block.data, LinkedLayerCollection):
                for layer in block.data.linked_list:
                    yield layer


def combined_bbox(layers):
    """
    Returns a bounding box for ``layers`` or None if this is not possible.
    """
    bboxes = [layer.bbox for layer in layers if layer.bbox is not None
              and layer.bbox.width > 0 and layer.bbox.height > 0]
    if not bboxes:
        return None

    lefts, tops, rights, bottoms = zip(*bboxes)
    return BBox(min(lefts), min(tops), max(rights), max(bottoms))


# FIXME: this currently assumes PIL
from PIL import Image

def merge_layers(layers, respect_visibility=True, skip_layer=lambda layer: False, background=None, bbox=None):
    """
    Merges layers together (the first layer is on top).

    By default hidden layers are not rendered;
    pass ``respect_visibility=False`` to render them.

    In order to skip some layers pass ``skip_layer`` function which
    should take ``layer` as an argument and return True or False.

    If ``bbox`` is not None, it should be an instance of ``BBox`` class
    with coordinates; returned image will be restricted to this rectangle.

    If ``background`` is not None, ``bbox`` should be passed as well.
    It should be an image such as background.size == (bbox.width, bbox.height)

    This is highly experimental.
    """

    if _blend_modes is not None:
        blend_functions = {
            BlendMode.NORMAL:           None,
            BlendMode.DISSOLVE:         _blend_modes.dissolve,

            BlendMode.DARKEN:           _blend_modes.darken,
            BlendMode.MULTIPLY:         _blend_modes.multiply,
            BlendMode.COLOR_BURN:       _blend_modes.color_burn,
            BlendMode.LINEAR_BURN:      _blend_modes.linear_burn,
            BlendMode.DARKER_COLOR:     _blend_modes.darker_color,      #                                       Photoshop bug

            BlendMode.LIGHTEN:          _blend_modes.lighten,
            BlendMode.SCREEN:           _blend_modes.screen,
            BlendMode.COLOR_DODGE:      _blend_modes.color_dodge,
            BlendMode.LINEAR_DODGE:     _blend_modes.linear_dodge,
            BlendMode.LIGHTER_COLOR:    _blend_modes.lighter_color,     #                                       Photoshop bug

            BlendMode.OVERLAY:          _blend_modes.overlay,
            BlendMode.SOFT_LIGHT:       _blend_modes.soft_light,        # max deviation - +/-1 tone
            BlendMode.HARD_LIGHT:       _blend_modes.hard_light,        #                                       Photoshop bug
            BlendMode.VIVID_LIGHT:      _blend_modes.vivid_light,       # max deviation - +2 tone               Photoshop bug
            BlendMode.LINEAR_LIGHT:     _blend_modes.linear_light,      #                                       Photoshop bug
            BlendMode.PIN_LIGHT:        _blend_modes.pin_light,         # max deviation - +1 tone
            BlendMode.HARD_MIX:         _blend_modes.hard_mix,

            BlendMode.DIFFERENCE:       _blend_modes.difference,
            BlendMode.EXCLUSION:        _blend_modes.exclusion,         # max deviation - +/-1 tone
            BlendMode.SUBTRACT:         _blend_modes.subtract,
            BlendMode.DIVIDE:           _blend_modes.divide,

            BlendMode.HUE:              _blend_modes.hue,               # max deviation - +/-2 luminance level  Photoshop bug
            BlendMode.SATURATION:       _blend_modes.saturation,        # max deviation - +/-2 luminance level  Photoshop bug
            BlendMode.COLOR:            _blend_modes.color,             # max deviation - +/-2 luminance level  Photoshop bug
            BlendMode.LUMINOSITY:       _blend_modes.luminosity         # max deviation - +/-2 luminance level  Photoshop bug
        }
    else:
        logger.warning(
            '"_blend_modes" C extension is not found. ' \
            'Blend modes are unavailable for merging!'
        )

    if background is None:
        if bbox is None:
            bbox = combined_bbox(layers)
            if bbox is None:
                return None

        # creating a base image...
        result = Image.new(
            "RGBA",
            (bbox.width, bbox.height),
            color = (255, 255, 255, 0)
        )
    else:
        if bbox is None or background.size != (bbox.width, bbox.height):
            return None

        # using existing image as a base...
        result = background

    for layer in reversed(layers):
        if layer is None:
            continue
        if respect_visibility and not layer.visible:
            continue

        layer_bbox = layer.bbox

        if layer_bbox.width == 0 or layer_bbox.height == 0:
            continue
        if layer_bbox.x2 < bbox.x1 or layer_bbox.y2 < bbox.y1 \
        or layer_bbox.x1 > bbox.x2 or layer_bbox.y1 > bbox.y2:
            logger.debug("Layer outside of bbox. Skipping...")
            continue
        if skip_layer(layer):
            continue

        use_dissolve = (layer.blend_mode == BlendMode.DISSOLVE)

        if isinstance(layer, psd_tools.Group):
            # if group's blend mode is PASS_THROUGH,
            # then its layers should be merged as if they aren't in group
            if layer.blend_mode == BlendMode.PASS_THROUGH:
                layer_image = merge_layers(
                    layer.layers, respect_visibility, skip_layer,
                    result.copy(), bbox
                )
            else:
                layer_image = merge_layers(
                    layer.layers, respect_visibility, skip_layer, None, bbox
                )

            x = y = 0
            background = result
        else:
            layer_image = layer.as_PIL()

            x, y = layer_bbox.x1 - bbox.x1, layer_bbox.y1 - bbox.y1
            w, h = layer_image.size
            # checking if layer is inside the area of rendering...
            if x < 0 or y < 0 or x + w > bbox.width or y + h > bbox.height:
                # layer doesn't fit the bbox
                crop_bbox = (
                    max(-x, 0),             max(-y, 0),
                    min(w, bbox.width - x), min(h, bbox.height - y)
                )

                logger.debug("Cropping layer to (%s, %s, %s, %s)...", *crop_bbox)

                layer_image = layer_image.crop(crop_bbox)
                x += crop_bbox[0]
                y += crop_bbox[1]
                w, h = layer_image.size

            if result.size != layer_image.size:
                background = result.crop((x, y, x + w, y + h))
            else:
                background = result

            # layer_image = pil_support.apply_opacity(layer_image, layer.fill)
            # layer_image = _blend(background, layer_image, None, use_dissolve)

        if _blend_modes is not None:
            # getting a blending function based on layers' blend mode...
            # if the given mode is not implemented, Normal mode will be used instead
            func = blend_functions.get(layer.blend_mode)
            if func is None and layer.blend_mode not in (BlendMode.NORMAL,
                                                         BlendMode.PASS_THROUGH):
                logger.warning(
                    "Blend mode is not implemented: %s. Using NORMAL mode...",
                    BlendMode.name_of(layer.blend_mode)
                )
            else:
                logger.debug(
                    "Blending using %s mode...", BlendMode.name_of(layer.blend_mode)
                )
        else:
            func = None
            use_dissolve = False

        layer_image = pil_support.apply_opacity(layer_image, layer.opacity)
        layer_image = _blend(background, layer_image, func, use_dissolve)

        if layer_image.size == result.size:
            result = layer_image
        else:
            result.paste(layer_image, (x, y))

    return result


def _blend(background, active, func, dissolve=False):
    if active.mode == 'RGBA':
        if func is not None:
            active_bytes = func(background.tobytes(), active.tobytes())
            active = Image.frombytes("RGBA", active.size, active_bytes)
        if not dissolve:
            active = Image.alpha_composite(background, active)

    elif active.mode == 'RGB':
        active = active.convert("RGBA")
        if func is not None and not dissolve:
            active_bytes = func(background.tobytes(), active.tobytes())
            active = Image.frombytes("RGBA", active.size, active_bytes)

    else:
        logger.warning("Layer image mode is unsupported for merging: %s", active.mode)
        return background

    return active
