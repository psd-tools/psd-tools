import numpy as np
from psd_tools.constants import ChannelID, Tag, BlendMode
import logging
from .blend import BLEND_FUNC, _normal
from .vector import create_fill, create_fill_desc, draw_vector_mask, draw_stroke


logger = logging.getLogger(__name__)


def composite(group, color=1.0, alpha=0.0, viewport=None, layer_filter=None,
              force=False):
    """
    Composite the given group of layers.
    """
    def _visible_filter(layer):
        return layer.is_visible()

    viewport = viewport or getattr(group, 'viewbox', None) or group.bbox

    if group.kind == 'psdimage' and len(group) == 0:
        color, shape = group.numpy('color'), group.numpy('shape')
        return color, shape, shape

    isolated = getattr(group, 'blend_mode', None) != BlendMode.PASS_THROUGH
    layer_filter = layer_filter or _visible_filter

    compositor = Compositor(
        viewport, color, alpha, isolated, layer_filter, force)

    for layer in (group if group.is_group() else [group]):
        if layer_filter(layer):
            compositor.apply(layer)

            needs_stroke = (force or not layer.has_pixels()) and \
                layer.has_stroke() and layer.stroke.enabled and \
                layer.stroke.fill_enabled
            if needs_stroke:
                compositor.apply_stroke(layer)

            # for effect in layer.effects:
            #     compositor.apply(effect)
    return compositor.finish()


def paste(viewport, bbox, values, background=None):
    """Change to the specified viewport."""
    shape = (
        viewport[3] - viewport[1], viewport[2] - viewport[0], values.shape[2])
    view = np.full(shape, background) if background else np.zeros(shape)
    inter = (max(viewport[0], bbox[0]), max(viewport[1], bbox[1]), min(
        viewport[2], bbox[2]), min(viewport[3], bbox[3]))
    if inter[0] >= inter[2] or inter[1] >= inter[3]:
        return view

    v = (inter[0] - viewport[0], inter[1] - viewport[1],
         inter[2] - viewport[0], inter[3] - viewport[1])
    b = (inter[0] - bbox[0], inter[1] - bbox[1],
         inter[2] - bbox[0], inter[3] - bbox[1])
    view[v[1]:v[3], v[0]:v[2], :] = values[b[1]:b[3], b[0]:b[2], :]
    return _clip(view)


class Compositor(object):
    """Composite context.

    Example::

        compositor = Compositor(group.bbox)
        for layer in group:
            compositor.apply(layer)
        color, shape, alpha = compositor.finish()
    """

    def __init__(self, viewport, color=1.0, alpha=0.0, isolated=False,
                 layer_filter=None, force=False):
        self._viewport = viewport
        self._layer_filter = layer_filter
        self._force = force

        height, width = viewport[3] - viewport[1], viewport[2] - viewport[0]
        if isolated:
            self._alpha_0 = np.zeros((height, width, 1))
        elif isinstance(alpha, np.ndarray):
            self._alpha_0 = alpha
        else:
            self._alpha_0 = np.full((height, width, 1), alpha)

        if isinstance(color, np.ndarray):
            self._color_0 = color
        else:
            self._color_0 = np.full((height, width, 3), color)

        self._shape_g = np.zeros((height, width, 1))
        self._alpha_g = np.zeros((height, width, 1))
        self._color = self._color_0
        self._alpha = self._alpha_0

    def apply(self, layer):
        logger.debug('Compositing %s' % (layer))

        if layer.is_group():
            # Compose in the group view, then paste to the current view.
            color, shape, alpha = composite(
                layer,
                paste(layer.bbox, self._viewport, self._color, 1.),
                paste(layer.bbox, self._viewport, self._alpha),
                layer.bbox,
                layer_filter=self._layer_filter,
                force=self._force)
            color = paste(self._viewport, layer.bbox, color, 1.)
            shape = paste(self._viewport, layer.bbox, shape)
            alpha = paste(self._viewport, layer.bbox, alpha)
        else:
            color, shape, alpha = _get_object(
                layer, self._viewport, self._force)

        # TODO: Consider clipping.
        shape_mask, opacity_mask = _get_mask(layer, self._viewport)
        shape_const, opacity_const = _get_const(layer)

        shape *= shape_mask * shape_const
        alpha *= (shape_mask * opacity_mask) * (shape_const * opacity_const)
        knockout = bool(layer.tagged_blocks.get_data(Tag.KNOCKOUT_SETTING, 0))

        self._apply_source(color, shape, alpha, knockout, layer.blend_mode)

    def apply_stroke(self, layer):
        logger.debug('Compositing stroke of %s' % (layer))

        desc = layer.stroke._data
        height = self._viewport[3] - self._viewport[1]
        width = self._viewport[2] - self._viewport[0]

        # TODO: Check origin of the fill.
        lw = int(desc.get('strokeStyleLineWidth', 1.))
        adjusted_bbox = tuple(
            x + d for x, d in zip(layer.bbox, (-lw, -lw, lw, lw)))

        color, shape = create_fill_desc(layer, desc.get('strokeStyleContent'),
                                        adjusted_bbox)
        color = paste(self._viewport, adjusted_bbox, color, 1.)
        if shape is None:
            shape = np.ones((height, width, 1))
        else:
            shape = paste(self._viewport, adjusted_bbox, shape)
        alpha = shape * 1.
        shape_mask = draw_stroke(layer)
        if shape_mask.shape[0] != height or shape_mask.shape[1] != width:
            bbox = (0, 0, shape_mask.shape[1], shape_mask.shape[0])
            shape_mask = paste(self._viewport, bbox, shape_mask)
        opacity_mask = float(desc.get('strokeStyleOpacity', 100.)) / 100.
        shape_const, opacity_const = _get_const(layer)
        shape *= shape_mask * shape_const
        alpha *= (shape_mask * opacity_mask) * (shape_const * opacity_const)

        blend_mode = desc.get('strokeStyleBlendMode').enum
        self._apply_source(color, shape, alpha, False, blend_mode)

    def _apply_source(self, color, shape, alpha, knockout, blend_mode):
        self._shape_g = _union(self._shape_g, shape)
        if knockout:
            self._alpha_g = (1. - shape) * self._alpha_g + \
                (shape - alpha) * self._alpha_0 + alpha
        else:
            self._alpha_g = _union(self._alpha_g, alpha)
        alpha_previous = self._alpha
        self._alpha = _union(self._alpha_0, self._alpha_g)

        alpha_b = self._alpha_0 if knockout else alpha_previous
        color_b = self._color_0 if knockout else self._color

        blend_fn = BLEND_FUNC.get(blend_mode, _normal)
        color_t = (shape - alpha) * alpha_b * color_b + alpha * \
            ((1. - alpha_b) * color + alpha_b * blend_fn(color_b, color))
        self._color = _clip(_divide(
            (1. - shape) * alpha_previous * self._color + color_t,
            np.repeat(self._alpha, 3, axis=2)))

    def finish(self):
        return self.color, self.shape, self.alpha

    @property
    def color(self):
        return _clip(self._color + (self._color - self._color_0) * (
            _divide(self._alpha_0, self._alpha_g) - self._alpha_0))

    @property
    def shape(self):
        return self._shape_g

    @property
    def alpha(self):
        return self._alpha_g


def _union(backdrop, source):
    """Generalized union of shape."""
    return backdrop + source - (backdrop * source)


def _clip(x):
    """Clip between [0, 1]."""
    return np.minimum(1., np.maximum(0., x))


def _divide(a, b):
    """Safe division for color ops."""
    index = b != 0
    c = np.ones_like(b)  # In Photoshop, undefined color is white.
    c[index] = (a[index] if isinstance(a, np.ndarray) else a) / b[index]
    return c


def _get_object(layer, viewport, force):
    """Get object attributes."""
    height, width = viewport[3] - viewport[1], viewport[2] - viewport[0]
    color, shape = layer.numpy('color'), layer.numpy('shape')
    FILL_TAGS = (
        Tag.SOLID_COLOR_SHEET_SETTING,
        Tag.PATTERN_FILL_SETTING,
        Tag.GRADIENT_FILL_SETTING,
    )
    has_fill = any(tag in layer.tagged_blocks for tag in FILL_TAGS)
    if (force or not layer.has_pixels()) and has_fill:
        color, shape = create_fill(layer, layer.bbox)
        if shape is None:
            shape = np.ones((layer.height, layer.width, 1))

    if color is None:
        color = np.ones((height, width, 3))
    else:
        color = paste(viewport, layer.bbox, color, 1.)
    if shape is None:
        shape = np.ones((height, width, 1))
    else:
        shape = paste(viewport, layer.bbox, shape)

    alpha = shape * 1.  # Constant factor is always 1.
    return color, shape, alpha


def _get_mask(layer, viewport):
    """Get mask attributes."""
    height, width = viewport[3] - viewport[1], viewport[2] - viewport[0]
    shape = 1.
    opacity = 1.
    if layer.has_mask():
        mask = layer.numpy('mask')
        if mask is not None:
            shape = paste(viewport, layer.mask.bbox, mask,
                          layer.mask.background_color / 255.)
        if layer.mask.parameters:
            density = layer.mask.parameters.user_mask_density
            if density is None:
                density = layer.mask.parameters.vector_mask_density
            if density is None:
                opacity = 255
            opacity = float(density) / 255.
    elif layer.has_vector_mask():
        shape = draw_vector_mask(layer)
        shape = paste(viewport, (layer._psd.viewbox), shape)
    return shape, opacity


def _get_const(layer):
    """Get constant attributes."""
    shape = layer.tagged_blocks.get_data(Tag.BLEND_FILL_OPACITY, 255) / 255.
    opacity = layer.opacity / 255.
    return shape, opacity
