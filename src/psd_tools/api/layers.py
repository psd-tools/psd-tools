"""
Layer module.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools.api import deprecated
from psd_tools.constants import BlendMode, SectionDivider, Clipping
from psd_tools.api.composer import extract_bbox
from psd_tools.api.effects import Effects
from psd_tools.api.mask import Mask
from psd_tools.api.pil_io import convert_layer_to_pil
from psd_tools.api.shape import VectorMask, Stroke, Origination
from psd_tools.api.smart_object import SmartObject

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
        Layer name. Writable.

        :return: `str`
        """
        return self._record.tagged_blocks.get_data(
            'UNICODE_LAYER_NAME', self._record.name
        )

    @name.setter
    def name(self, value):
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
        Kind of this layer, such as group, pixel, shape, type, smartobject,
        or psdimage. Class name without `layer` suffix.

        :return: `str`
        """
        return self.__class__.__name__.lower().replace('layer', '')

    @property
    def layer_id(self):
        """
        Layer ID.

        :return: int layer id. if the layer is not assigned an id, -1.
        """
        return self.tagged_blocks.get_data('layer_id', -1)

    @property
    def visible(self):
        """
        Layer visibility. Doesn't take group visibility in account. Writable.

        :return: `bool`
        """
        return self._record.flags.visible

    @visible.setter
    def visible(self, value):
        self._record.flags.visible = bool(value)

    def is_visible(self):
        """
        Layer visibility. Takes group visibility in account.

        :return: `bool`
        """
        return self.visible and self.parent.is_visible()

    @property
    def opacity(self):
        """
        Opacity of this layer in [0, 255] range. Writable.

        :return: int
        """
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
        """
        Return True if the layer is a group.

        :return: `bool`
        """
        return isinstance(self, GroupMixin)

    @property
    def blend_mode(self):
        """
        Blend mode of this layer. Writable.

        Example::

            from psd_tools.constants import BlendMode
            if layer.blend_mode == BlendMode.NORMAL:
                layer.blend_mode = BlendMode.SCREEN

        :return: :py:class:`~psd_tools.constants.BlendMode`.
        """
        return self._record.blend_mode

    @blend_mode.setter
    def blend_mode(self, value):
        if isinstance(value, BlendMode):
            self._record.blend_mode = value
        elif hasattr(BlendMode, value.upper()):
            self._record.blend_mode = getattr(BlendMode, value.upper())
        else:
            self._record.blend_mode = BlendMode(value)

    def has_mask(self):
        """Returns True if the layer has a mask."""
        return self._record.mask_data is not None

    @property
    def left(self):
        """
        Left coordinate. Writable.

        :return: int
        """
        return self._record.left

    @left.setter
    def left(self, value):
        w = self.width
        self._record.left = int(value)
        self._record.right = int(value) + w

    @property
    def top(self):
        """
        Top coordinate. Writable.

        :return: int
        """
        return self._record.top

    @top.setter
    def top(self, value):
        h = self.height
        self._record.top = int(value)
        self._record.bottom = int(value) + h

    @property
    def right(self):
        """
        Right coordinate.

        :return: int
        """
        return self._record.right

    @property
    def bottom(self):
        """
        Bottom coordinate.

        :return: int
        """
        return self._record.bottom

    @property
    def width(self):
        """
        Width of the layer.

        :return: int
        """
        return self.right - self.left

    @property
    def height(self):
        """
        Height of the layer.

        :return: int
        """
        return self.bottom - self.top

    @property
    def offset(self):
        """
        (left, top) tuple. Writable.

        :return: `tuple`
        """
        return self.left, self.top

    @offset.setter
    def offset(self, value):
        self.left, self.top = tuple(int(x) for x in value)

    @property
    def size(self):
        """
        (width, height) tuple.

        :return: `tuple`
        """
        return self.width, self.height

    @property
    def bbox(self):
        """(left, top, right, bottom) tuple."""
        return self.left, self.top, self.right, self.bottom

    def has_pixels(self):
        """
        Returns True if the layer has associated pixels. When this is True,
        `topil` method returns :py:class:`PIL.Image`.

        :return: `bool`
        """
        return any(
            ci.id >= 0 and cd.data and len(cd.data) > 0
            for ci, cd in zip(self._record.channel_info, self._channels)
        )

    def has_mask(self):
        """
        Returns True if the layer has a mask.

        :return: `bool`
        """
        return self._record.mask_data is not None

    @property
    def mask(self):
        """
        Returns mask associated with this layer.

        :return: :py:class:`~psd_tools.api.mask.Mask` or `None`
        """
        if not hasattr(self, "_mask"):
            self._mask = Mask(self) if self.has_mask() else None
        return self._mask

    def has_vector_mask(self):
        """
        Returns True if the layer has a vector mask.

        :return: `bool`
        """
        return any(
            key in self.tagged_blocks for key in
            ('VECTOR_MASK_SETTING1', 'VECTOR_MASK_SETTING2')
        )

    @property
    def vector_mask(self):
        """
        Returns vector mask associated with this layer.

        :return: :py:class:`~psd_tools.api.shape.VectorMask` or `None`
        """
        if not hasattr(self, '_vector_mask'):
            self._vector_mask = None
            blocks = self.tagged_blocks
            for key in ('VECTOR_MASK_SETTING1', 'VECTOR_MASK_SETTING2'):
                if key in blocks:
                    self._vector_mask = VectorMask(blocks.get_data(key))
        return self._vector_mask

    def has_origination(self):
        """
        Returns True if the layer has live shape properties.

        :return: `bool`
        """
        if self.origination:
            return True
        return False

    @property
    def origination(self):
        """
        Property for a list of live shapes or a line.

        Some of the vector masks have associated live shape properties, that
        are Photoshop feature to handle primitive shapes such as a rectangle,
        an ellipse, or a line. Vector masks without live shape properties are
        plain path objects.

        See :py:mod:`psd_tools.api.shape`.

        :return: List of :py:class:`~psd_tools.api.shape.Invalidated`,
            :py:class:`~psd_tools.api.shape.Rectangle`,
            :py:class:`~psd_tools.api.shape.RoundedRectangle`,
            :py:class:`~psd_tools.api.shape.Ellipse`, or
            :py:class:`~psd_tools.api.shape.Line`.
        """
        if not hasattr(self, '_origination'):
            data = self.tagged_blocks.get_data('VECTOR_ORIGINATION_DATA', {})
            self._origination = [
                Origination.create(x) for x
                in data.get(b'keyDescriptorList', [])
                if not data.get(b'keyShapeInvalidated')
            ]
        return self._origination

    def topil(self, **kwargs):
        """
        Get PIL Image of the layer.

        :return: :py:class:`PIL.Image`, or `None` if the layer has no pixels.
        """
        if self.has_pixels():
            return convert_layer_to_pil(self, **kwargs)
        return None

    def compose(self, *args, **kwargs):
        """
        Compose layer and masks (mask, vector mask, and clipping layers).

        :return: :py:class:`PIL.Image`, or `None` if the layer has no pixel.
        """
        from psd_tools.api.composer import compose_layer
        if self.bbox == (0, 0, 0, 0):
            return None
        return compose_layer(self, *args, **kwargs)

    def has_clip_layers(self):
        """
        Returns True if the layer has associated clipping.

        :return: `bool`
        """
        return len(self.clip_layers) > 0

    @property
    def clip_layers(self):
        """
        Clip layers associated with this layer.

        To compose clipping layers::

            from psd_tools import compose
            clip_mask = compose(layer.clip_layers)

        :return: list of layers
        """
        return self._clip_layers

    def has_effects(self):
        """
        Returns True if the layer has effects.

        :return: `bool`
        """
        return any(tag in self.tagged_blocks for tag in (
            'OBJECT_BASED_EFFECTS_LAYER_INFO',
            'OBJECT_BASED_EFFECTS_LAYER_INFO_V0',
            'OBJECT_BASED_EFFECTS_LAYER_INFO_V1',
        ))

    @property
    def effects(self):
        """
        Layer effects.

        :return: :py:class:`~psd_tools.api.effects.Effects`
        """
        if not hasattr(self, '_effects'):
            self._effects = Effects(self)
        return self._effects

    @property
    def tagged_blocks(self):
        """
        Layer tagged blocks that is a dict-like container of settings.

        See :py:class:`psd_tools.constants.TaggedBlockID` for available
        keys.

        :return: :py:class:`~psd_tools.psd.tagged_blocks.TaggedBlocks` or
            `None`.

        Example::

            metadata = layer.tagged_blocks.get_data('METADATA_SETTING')
        """
        return self._record.tagged_blocks

    def __repr__(self):
        has_size = self.width > 0 and self.height > 0
        return '%s(%r%s%s%s%s)' % (
            self.__class__.__name__, self.name,
            ' size=%dx%d' % (self.width, self.height) if has_size else '',
            ' invisible' if not self.visible else '',
            ' mask' if self.has_mask() else '',
            ' effects' if self.has_effects() else '',
        )

    @deprecated
    def as_PIL(self, *args, **kwargs):
        return self.topil(*args, **kwargs)

    @property
    @deprecated
    def flags(self):
        return self._record.flags

    @deprecated
    def has_box(self):
        return self.width > 0 and self.height > 0

    @deprecated
    def has_relevant_pixels(self):
        if self._record.flags.pixel_data_irrelevant:
            return False
        return self.has_pixels()


class GroupMixin(object):

    @property
    def left(self):
        return self.bbox[0]

    @property
    def top(self):
        return self.bbox[1]

    @property
    def right(self):
        return self.bbox[2]

    @property
    def bottom(self):
        return self.bbox[3]

    @property
    def bbox(self):
        """(left, top, right, bottom) tuple."""
        if not hasattr(self, '_bbox'):
            self._bbox = extract_bbox(self)
        return self._bbox

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

    def compose(self, **kwargs):
        """
        Compose layer and masks (mask, vector mask, and clipping layers).

        :return: PIL Image object, or None if the layer has no pixels.
        """
        from psd_tools.api.composer import compose
        return compose(self, **kwargs)

    def descendants(self, include_clip=True):
        """
        Return a generator to iterate over all descendant layers.

        Example::

            # Iterate over all layers
            for layer in psd.descendants():
                print(layer)

            # Iterate over all layers in reverse order
            for layer in reversed(list(psd.descendants())):
                print(layer)

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
    """
    Group of layers.

    Example::

        group = psd[1]
        for layer in group:
            if layer.kind == 'pixel':
                print(layer.name)
    """
    def __init__(self, *args):
        super(Group, self).__init__(*args)
        self._layers = []


class Artboard(Group):
    """
    Artboard is a special kind of group that has a pre-defined viewbox.

    Example::

        artboard = psd[1]
        image = artboard.compose()
    """

    @classmethod
    def _move(kls, group):
        self = kls(group._psd, group._record, group._channels, group._parent)
        self._layers = group._layers
        for layer in self._layers:
            layer._parent = self
        for index in range(len(self.parent)):
            if group == self.parent[index]:
                self.parent._layers[index] = self
        return self

    @property
    def left(self):
        return self.bbox[0]

    @property
    def top(self):
        return self.bbox[1]

    @property
    def right(self):
        return self.bbox[2]

    @property
    def bottom(self):
        return self.bbox[3]

    @property
    def bbox(self):
        """(left, top, right, bottom) tuple."""
        if not hasattr(self, '_bbox'):
            data = None
            for key in ('ARTBOARD_DATA1', 'ARTBOARD_DATA2', 'ARTBOARD_DATA3'):
                if key in self.tagged_blocks:
                    data = self.tagged_blocks.get_data(key)
            assert data is not None
            rect = data.get(b'artboardRect')
            self._bbox = (
                int(rect.get(b'Left')),
                int(rect.get(b'Top ')),
                int(rect.get(b'Rght')),
                int(rect.get(b'Btom')),
            )
        return self._bbox

    def compose(self, bbox=None, **kwargs):
        """
        Compose the artboard.

        See :py:func:`~psd_tools.compose` for available extra arguments.

        :param bbox: Viewport tuple (left, top, right, bottom).
        :return: :py:class:`PIL.Image`, or `None` if there is no pixel.
        """
        from psd_tools.api.composer import compose
        return compose(self, bbox=bbox or self.bbox, **kwargs)


class PixelLayer(Layer):
    """
    Layer that has rasterized image in pixels.

    Example::

        assert layer.kind == 'pixel':
        image = layer.topil()
        image.save('layer.png')

        composed_image = layer.compose()
        composed_image.save('composed-layer.png')
    """
    pass


class SmartObjectLayer(Layer):
    """
    Layer that inserts external data.

    Use :py:attr:`~psd_tools.api.layers.SmartObjectLayer.smart_object`
    attribute to get the external data. See
    :py:class:`~psd_tools.api.smart_object.SmartObject`.

    Example::

        import io
        if layer.smart_object.filetype == 'jpg':
            image = Image.open(io.BytesIO(layer.smart_object.data))
    """
    @property
    def smart_object(self):
        """
        Associated smart object.

        :return: :py:class:`~psd_tools.api.smart_object.SmartObject`.
        """
        if not hasattr(self, '_smart_object'):
            self._smart_object = SmartObject(self)
        return self._smart_object

    @property
    @deprecated
    def unique_id(self):
        return self.smart_object.unique_id

    @property
    @deprecated
    def linked_data(self):
        return self.smart_object


class TypeLayer(Layer):
    """
    Layer that has text and styling information for fonts or paragraphs.

    Text is accessible at :py:attr:`~psd_tools.api.layers.TypeLayer.text`
    property. Styling information for paragraphs is in
    :py:attr:`~psd_tools.api.layers.TypeLayer.engine_dict`.
    Document styling information such as font list is is
    :py:attr:`~psd_tools.api.layers.TypeLayer.resource_dict`.

    Currently, textual information is read-only.

    Example::

        if layer.kind == 'type':
            print(layer.text)
            print(layer.engine_dict['StyleRun'])

            # Extract font for each substring in the text.
            text = layer.engine_dict['Editor']['Text'].value
            fontset = layer.resource_dict['FontSet']
            runlength = layer.engine_dict['StyleRun']['RunLengthArray']
            rundata = layer.engine_dict['StyleRun']['RunArray']
            index = 0
            for length, style in zip(runlength, rundata):
                substring = text[index:index + length]
                stylesheet = style['StyleSheet']['StyleSheetData']
                font = fontset[stylesheet['Font']]
                print('%r gets %s' % (substring, font))
                index += length
    """
    def __init__(self, *args):
        super(TypeLayer, self).__init__(*args)
        self._data = self.tagged_blocks.get_data('TYPE_TOOL_OBJECT_SETTING')

    @property
    def text(self):
        """
        Text in the layer. Read-only.

        .. note:: New-line character in Photoshop is `'\\\\r'`.
        """
        return self._data.text_data.get(b'Txt ').value.rstrip('\x00')

    @property
    def transform(self):
        """Matrix (xx, xy, yx, yy, tx, ty) applies affine transformation."""
        return self._data.transform

    @property
    def _engine_data(self):
        """Styling and resource information."""
        return self._data.text_data.get(b'EngineData').value

    @property
    def engine_dict(self):
        """Styling information dict."""
        return self._engine_data.get('EngineDict')

    @property
    def resource_dict(self):
        """Resource set."""
        return self._engine_data.get('ResourceDict')

    @property
    def document_resources(self):
        """Resource set relevant to the document."""
        return self._engine_data.get('DocumentResources')

    @property
    def warp(self):
        """Warp configuration."""
        return self._data.warp

    @property
    @deprecated
    def fontset(self):
        return self.document_resources.get('FontSet')

    @property
    @deprecated
    def engine_data(self):
        return self._engine_data

    @property
    @deprecated
    def full_text(self):
        return self.engine_dict['Editor']['Txt ']

    @property
    @deprecated
    def writing_direction(self):
        return self.engine_dict['Rendered']['Shapes']['WritingDirection']

    @deprecated
    def style_spans(self):
        text = self.engine_dict['Editor']['Text'].value
        fontset = self.document_resources['FontSet']
        style_run = self.engine_dict['StyleRun']
        runlength = style_run['RunLengthArray']
        runarray = style_run['RunArray']

        start = 0
        spans = []
        for run, size in zip(runarray, runlength):
            runtext = text[start:start + size]
            stylesheet = dict(run['StyleSheet']['StyleSheetData'])
            stylesheet['Text'] = runtext
            stylesheet['Font'] = fontset[stylesheet.get('Font', 0)]
            spans.append(stylesheet)
            start += size
        return spans


class ShapeLayer(Layer):
    """
    Layer that has drawing in vector mask.
    """
    @property
    def left(self):
        return self.bbox[0]

    @property
    def top(self):
        return self.bbox[1]

    @property
    def right(self):
        return self.bbox[2]

    @property
    def bottom(self):
        return self.bbox[3]

    @property
    def bbox(self):
        """(left, top, right, bottom) tuple."""
        if not hasattr(self, '_bbox'):
            if self.has_pixels():
                self._bbox = (
                    self._record.left,
                    self._record.top,
                    self._record.right,
                    self._record.bottom,
                )
            elif self.has_origination() and not any(
                x.invalidated for x in self.origination
            ):
                lefts, tops, rights, bottoms = zip(*[
                    x.bbox for x in self.origination
                ])
                self._bbox = (
                    int(min(lefts)), int(min(tops)),
                    int(max(rights)), int(max(bottoms))
                )
            elif self.has_vector_mask():
                bbox = self.vector_mask.bbox
                self._bbox = (
                    int(bbox[0] * self._psd.width),
                    int(bbox[1] * self._psd.height),
                    int(bbox[2] * self._psd.width),
                    int(bbox[3] * self._psd.height),
                )
            else:
                self._bbox = (0, 0, 0, 0)
        return self._bbox

    def has_stroke(self):
        """Returns True if the shape has a stroke."""
        return 'VECTOR_STROKE_DATA' in self.tagged_blocks

    @property
    def stroke(self):
        """Property for strokes."""
        if not hasattr(self, '_stroke'):
            self._stroke = None
            stroke = self.tagged_blocks.get_data('VECTOR_STROKE_DATA')
            if stroke:
                self._stroke = Stroke(stroke)
        return self._stroke

    # Stroke content data seems obsolete.

    # def has_stroke_content(self):
    #     """Returns True if the shape has stroke content data."""
    #     return 'VECTOR_STROKE_CONTENT_DATA' in self.tagged_blocks

    # @property
    # def stroke_content(self):
    #     """
    #     Property for stroke content.

    #     Stroke content is metadata associated with fill of the stroke.
    #     """
    #     return self.tagged_blocks.get_data('VECTOR_STROKE_CONTENT_DATA')


class AdjustmentLayer(Layer):
    """Layer that applies specified image adjustment effect."""
    def __init__(self, *args):
        super(AdjustmentLayer, self).__init__(*args)
        self._data = None
        if hasattr(self.__class__, '_KEY'):
            self._data = self.tagged_blocks.get_data(self.__class__._KEY)

    def compose(self, **kwargs):
        """
        Adjustment layer is never composed.

        :return: None
        """
        return None


class FillLayer(Layer):
    """Layer that fills the canvas region."""
    def __init__(self, *args):
        super(FillLayer, self).__init__(*args)
        self._data = None
        if hasattr(self.__class__, '_KEY'):
            self._data = self.tagged_blocks.get_data(self.__class__._KEY)

    @property
    def left(self):
        return self._record.left

    @property
    def top(self):
        return self._record.top

    @property
    def right(self):
        return self._record.right or self._psd.width

    @property
    def bottom(self):
        return self._record.bottom or self._psd.height
