import numpy as np
from psd_tools.constants import Tag, BlendMode, ColorMode
from psd_tools.api.layers import AdjustmentLayer, Layer
from psd_tools.api.numpy_io import EXPECTED_CHANNELS

import logging
from .blend import BLEND_FUNC, normal
from .vector import (
    create_fill, create_fill_desc, draw_vector_mask, draw_stroke,
    draw_solid_color_fill, draw_pattern_fill, draw_gradient_fill
)
from .effects import draw_stroke_effect

logger = logging.getLogger(__name__)


def composite_pil(
    layer, color, alpha, viewport, layer_filter, force, as_layer=False
):
    from PIL import Image
    from psd_tools.api.pil_io import get_pil_mode
    from psd_tools.api.numpy_io import has_transparency

    UNSUPPORTED_MODES = {
        ColorMode.DUOTONE,
        ColorMode.LAB,
    }
    color_mode = getattr(layer, '_psd', layer).color_mode
    if color_mode in UNSUPPORTED_MODES:
        logger.warning('Unsupported blending color space: %s' % (color_mode))

    color, _, alpha = composite(
        layer,
        color=color,
        alpha=alpha,
        viewport=viewport,
        layer_filter=layer_filter,
        force=force,
        as_layer=as_layer
    )

    mode = get_pil_mode(color_mode)
    if mode == 'P':
        mode = 'RGB'
    # Skip only when there is a preview image and it has no alpha.
    skip_alpha = not force and (
        color_mode not in (ColorMode.GRAYSCALE, ColorMode.RGB) or (
            layer.kind == 'psdimage' and layer.has_preview() and
            not has_transparency(layer)
        )
    )
    logger.debug('Skipping alpha: %g' % skip_alpha)
    if not skip_alpha:
        color = np.concatenate((color, alpha), 2)
        mode += 'A'
    if mode in ('1', 'L'):
        color = color[:, :, 0]
    if color.shape[0] == 0 or color.shape[1] == 0:
        return None
    return Image.fromarray((255 * color).astype(np.uint8), mode)


def composite(
    group,
    color=1.0,
    alpha=0.0,
    viewport=None,
    layer_filter=None,
    force=False,
    as_layer=False,
):
    """
    Composite the given group of layers.
    """
    viewport = viewport or getattr(group, 'viewbox', None) or group.bbox
    if viewport == (0, 0, 0, 0):
        viewport = getattr(group, '_psd').viewbox

    if getattr(group, 'kind', None) == 'psdimage' and len(group) == 0:
        color, shape = group.numpy('color'), group.numpy('shape')
        if viewport != group.viewbox:
            color = paste(viewport, group.bbox, color, 1.)
            shape = paste(viewport, group.bbox, shape)
        return color, shape, shape

    if not isinstance(color, np.ndarray) and not hasattr(color, '__iter__'):
        color_mode = getattr(group, '_psd', group).color_mode
        color = (color, ) * EXPECTED_CHANNELS.get(color_mode)

    isolated = False
    if hasattr(group, 'blend_mode'):
        isolated = group.blend_mode != BlendMode.PASS_THROUGH

    layer_filter = layer_filter or Layer.is_visible

    compositor = Compositor(
        viewport, color, alpha, isolated, layer_filter, force
    )
    for layer in (
        group if hasattr(group, '__iter__') and not as_layer else [group]
    ):
        compositor.apply(layer)

    return compositor.finish()


def paste(viewport, bbox, values, background=None):
    """Change to the specified viewport."""
    shape = (
        viewport[3] - viewport[1], viewport[2] - viewport[0], values.shape[2]
    )
    view = np.full(shape, background, dtype=np.float32
                   ) if background else np.zeros(shape, dtype=np.float32)
    inter = _intersect(viewport, bbox)
    if inter == (0, 0, 0, 0):
        return view

    v = (
        inter[0] - viewport[0], inter[1] - viewport[1], inter[2] - viewport[0],
        inter[3] - viewport[1]
    )
    b = (
        inter[0] - bbox[0], inter[1] - bbox[1], inter[2] - bbox[0],
        inter[3] - bbox[1]
    )
    view[v[1]:v[3], v[0]:v[2], :] = values[b[1]:b[3], b[0]:b[2], :]
    return view


class Compositor(object):
    """Composite context.

    Example::

        compositor = Compositor(group.bbox)
        for layer in group:
            compositor.apply(layer)
        color, shape, alpha = compositor.finish()
    """
    def __init__(
        self,
        viewport,
        color=1.0,
        alpha=0.0,
        isolated=False,
        layer_filter=None,
        force=False,
    ):
        self._viewport = viewport
        self._layer_filter = layer_filter
        self._force = force
        self._clip_mask = 1.

        if isolated:
            self._alpha_0 = np.zeros((self.height, self.width, 1),
                                     dtype=np.float32)
        elif isinstance(alpha, np.ndarray):
            self._alpha_0 = alpha
        else:
            self._alpha_0 = np.full((self.height, self.width, 1),
                                    alpha,
                                    dtype=np.float32)

        if isinstance(color, np.ndarray):
            self._color_0 = color
        else:
            channels = len(color) if hasattr(color, '__iter__') else 1
            self._color_0 = np.full((self.height, self.width, channels),
                                    color,
                                    dtype=np.float32)

        self._shape_g = np.zeros((self.height, self.width, 1),
                                 dtype=np.float32)
        self._alpha_g = np.zeros((self.height, self.width, 1),
                                 dtype=np.float32)
        self._color = self._color_0
        self._alpha = self._alpha_0

    def apply(self, layer):
        logger.debug('Compositing %s' % layer)

        if not self._layer_filter(layer):
            logger.debug('Ignore %s' % layer)
            return
        if isinstance(layer, AdjustmentLayer):
            logger.debug('Ignore adjustment %s' % layer)
            return
        if _intersect(self._viewport, layer.bbox) == (0, 0, 0, 0):
            logger.debug('Out of viewport %s' % (layer))
            return

        knockout = bool(layer.tagged_blocks.get_data(Tag.KNOCKOUT_SETTING, 0))
        if layer.is_group():
            color, shape, alpha = self._get_group(layer, knockout)
        else:
            color, shape, alpha = self._get_object(layer)

        shape_mask, opacity_mask = self._get_mask(layer)
        shape_const, opacity_const = self._get_const(layer)
        shape *= shape_mask
        alpha *= shape_mask * opacity_mask * opacity_const

        # TODO: Tag.BLEND_INTERIOR_ELEMENTS controls how inner effects apply.

        # TODO: Apply before effects
        self._apply_source(
            color, shape * shape_const, alpha * shape_const, layer.blend_mode,
            knockout
        )

        # TODO: Apply after effects
        self._apply_color_overlay(layer, color, shape, alpha)
        self._apply_pattern_overlay(layer, color, shape, alpha)
        self._apply_gradient_overlay(layer, color, shape, alpha)
        if ((self._force and layer.has_vector_mask()) or (
            not layer.has_pixels()) and has_fill(layer)):
            self._apply_stroke_effect(layer, color, shape_mask, alpha)
        else:
            self._apply_stroke_effect(layer, color, shape, alpha)

    def _apply_source(self, color, shape, alpha, blend_mode, knockout=False):
        if self._color_0.shape[2] == 1 and 1 < color.shape[2]:
            self._color_0 = np.repeat(self._color_0, color.shape[2], axis=2)
        if self._color.shape[2] == 1 and 1 < color.shape[2]:
            self._color = np.repeat(self._color, color.shape[2], axis=2)

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

        blend_fn = BLEND_FUNC.get(blend_mode, normal)
        color_t = (shape - alpha) * alpha_b * color_b + alpha * \
            ((1. - alpha_b) * color + alpha_b * blend_fn(color_b, color))
        self._color = _clip(
            _divide((1. - shape) * alpha_previous * self._color + color_t,
                    self._alpha)
        )

    def finish(self):
        return self.color, self.shape, self.alpha

    @property
    def viewport(self):
        return self._viewport

    @property
    def width(self):
        return self._viewport[2] - self._viewport[0]

    @property
    def height(self):
        return self._viewport[3] - self._viewport[1]

    @property
    def color(self):
        return _clip(
            self._color + (self._color - self._color_0) *
            (_divide(self._alpha_0, self._alpha_g) - self._alpha_0)
        )

    @property
    def shape(self):
        return self._shape_g

    @property
    def alpha(self):
        return self._alpha_g

    def _get_group(self, layer, knockout):
        viewport = _intersect(self._viewport, layer.bbox)
        if knockout:
            color_b = self._color_0
            alpha_b = self._alpha_0
        else:
            color_b = self._color
            alpha_b = self._alpha

        color, shape, alpha = composite(
            layer,
            paste(viewport, self._viewport, color_b, 1.),
            paste(viewport, self._viewport, alpha_b),
            viewport,
            layer_filter=self._layer_filter,
            force=self._force
        )
        color = paste(self._viewport, viewport, color, 1.)
        shape = paste(self._viewport, viewport, shape)
        alpha = paste(self._viewport, viewport, alpha)

        # Composite clip layers.
        if layer.has_clip_layers():
            color = self._apply_clip_layers(layer, color, alpha)

        assert color is not None
        assert shape is not None
        assert alpha is not None
        return color, shape, alpha

    def _get_object(self, layer):
        """Get object attributes."""
        color, shape = layer.numpy('color'), layer.numpy('shape')
        if (self._force or not layer.has_pixels()) and has_fill(layer):
            color, shape = create_fill(layer, layer.bbox)
            if shape is None:
                shape = np.ones((layer.height, layer.width, 1),
                                dtype=np.float32)

        if color is None and shape is None:
            # Empty pixel layer.
            color = np.ones((self.height, self.width, 1), dtype=np.float32)
            shape = np.zeros((self.height, self.width, 1), dtype=np.float32)

        if color is None:
            color = np.ones((self.height, self.width, 1), dtype=np.float32)
        else:
            color = paste(self._viewport, layer.bbox, color, 1.)
        if shape is None:
            shape = np.ones((self.height, self.width, 1), dtype=np.float32)
        else:
            shape = paste(self._viewport, layer.bbox, shape)

        alpha = shape * 1.  # Constant factor is always 1.

        # Composite clip layers.
        if layer.has_clip_layers():
            color = self._apply_clip_layers(layer, color, alpha)

        # Apply stroke if any.
        if layer.has_stroke() and layer.stroke.enabled:
            color_s, shape_s, alpha_s = self._get_stroke(layer)
            compositor = Compositor(self._viewport, color, alpha)
            compositor._apply_source(
                color_s, shape_s, alpha_s, layer.stroke.blend_mode
            )
            color, _, _ = compositor.finish()

        assert color is not None
        assert shape is not None
        assert alpha is not None
        return color, shape, alpha

    def _apply_clip_layers(self, layer, color, alpha):
        # TODO: Consider Tag.BLEND_CLIPPING_ELEMENTS.
        compositor = Compositor(
            self._viewport,
            color,
            alpha,
            layer_filter=self._layer_filter,
            force=self._force
        )
        for clip_layer in layer.clip_layers:
            compositor.apply(clip_layer)
        return compositor._color

    def _get_mask(self, layer):
        """Get mask attributes."""
        shape = 1.
        opacity = 1.
        if layer.has_mask() and not layer.mask.disabled:
            # TODO: When force, ignore real mask.
            mask = layer.numpy('mask', real_mask=not self._force)
            if mask is not None:
                shape = paste(
                    self._viewport, layer.mask.bbox, mask,
                    layer.mask.background_color / 255.
                )
            if layer.mask.parameters:
                density = layer.mask.parameters.user_mask_density
                if density is None:
                    density = layer.mask.parameters.vector_mask_density
                if density is None:
                    density = 255
                opacity = float(density) / 255.

        if layer.has_vector_mask() and not layer.vector_mask.disabled and (
            self._force or not layer.has_pixels() or (
                not has_fill(layer) and layer.has_mask() and
                not layer.mask._has_real()
            )
        ):
            shape_v = draw_vector_mask(layer)
            shape_v = paste(self._viewport, layer._psd.viewbox, shape_v)
            shape *= shape_v

        assert shape is not None
        assert opacity is not None
        return shape, opacity

    def _get_const(self, layer):
        """Get constant attributes."""
        shape = layer.tagged_blocks.get_data(
            Tag.BLEND_FILL_OPACITY, 255
        ) / 255.
        opacity = layer.opacity / 255.
        assert shape is not None
        assert opacity is not None
        return shape, opacity

    def _get_stroke(self, layer):
        """Get stroke source."""
        desc = layer.stroke._data
        width = int(desc.get('strokeStyleLineWidth', 1.))
        viewport = tuple(
            x + d for x, d in zip(layer.bbox, (-width, -width, width, width))
        )
        color, _ = create_fill_desc(
            layer, desc.get('strokeStyleContent'), viewport
        )
        color = paste(self._viewport, viewport, color, 1.)
        shape = draw_stroke(layer)
        if shape.shape[0] != self.height or shape.shape[1] != self.width:
            bbox = (0, 0, shape.shape[1], shape.shape[0])
            shape = paste(self._viewport, bbox, shape)
        opacity = desc.get('strokeStyleOpacity', 100.) / 100.
        alpha = shape * opacity
        return color, shape, alpha

    def _apply_color_overlay(self, layer, color, shape, alpha):
        for effect in layer.effects.find('coloroverlay'):
            color, shape_e = draw_solid_color_fill(layer.bbox, effect.value)
            color = paste(self._viewport, layer.bbox, color, 1.)
            if shape_e is None:
                shape_e = np.ones((self.height, self.width, 1),
                                  dtype=np.float32)
            else:
                shape_e = paste(self._viewport, layer.bbox, shape_e)
            opacity = effect.opacity / 100.
            self._apply_source(
                color, shape * shape_e, alpha * shape_e * opacity,
                effect.blend_mode
            )

    def _apply_pattern_overlay(self, layer, color, shape, alpha):
        for effect in layer.effects.find('patternoverlay'):
            color, shape_e = draw_pattern_fill(
                layer.bbox, layer._psd, effect.value
            )
            color = paste(self._viewport, layer.bbox, color, 1.)
            if shape_e is None:
                shape_e = np.ones((self.height, self.width, 1),
                                  dtype=np.float32)
            else:
                shape_e = paste(self._viewport, layer.bbox, shape_e)
            opacity = effect.opacity / 100.
            self._apply_source(
                color, shape * shape_e, alpha * shape_e * opacity,
                effect.blend_mode
            )

    def _apply_gradient_overlay(self, layer, color, shape, alpha):
        for effect in layer.effects.find('gradientoverlay'):
            color, shape_e = draw_gradient_fill(layer.bbox, effect.value)
            color = paste(self._viewport, layer.bbox, color, 1.)
            if shape_e is None:
                shape_e = np.ones((self.height, self.width, 1),
                                  dtype=np.float32)
            else:
                shape_e = paste(self._viewport, layer.bbox, shape_e)
            opacity = effect.opacity / 100.
            self._apply_source(
                color, shape * shape_e, alpha * shape_e * opacity,
                effect.blend_mode
            )

    def _apply_stroke_effect(self, layer, color, shape, alpha):
        for effect in layer.effects.find('stroke'):
            # Effect must happen at the layer viewport.
            shape = paste(layer.bbox, self._viewport, shape)
            color, shape_e = draw_stroke_effect(
                layer.bbox, shape, effect.value, layer._psd
            )
            color = paste(self._viewport, layer.bbox, color)
            shape_e = paste(self._viewport, layer.bbox, shape_e)
            opacity = effect.opacity / 100.
            self._apply_source(
                color, shape_e, shape_e * opacity, effect.blend_mode
            )


def _intersect(a, b):
    inter = (
        max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    )
    if inter[0] >= inter[2] or inter[1] >= inter[3]:
        return (0, 0, 0, 0)
    return inter


def has_fill(layer):
    FILL_TAGS = (
        Tag.SOLID_COLOR_SHEET_SETTING,
        Tag.PATTERN_FILL_SETTING,
        Tag.GRADIENT_FILL_SETTING,
        Tag.VECTOR_STROKE_CONTENT_DATA,
    )
    return any(tag in layer.tagged_blocks for tag in FILL_TAGS)


def _union(backdrop, source):
    """Generalized union of shape."""
    return backdrop + source - (backdrop * source)


def _clip(x):
    """Clip between [0, 1]."""
    return np.clip(x, 0., 1.)


def _divide(a, b):
    """Safe division for color ops."""
    with np.errstate(divide='ignore', invalid='ignore'):
        c = np.true_divide(a, b)
        c[~np.isfinite(c)] = 1.
    return c
