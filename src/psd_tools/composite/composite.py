"""Composite implementation for layer rendering and blending."""

import logging
from typing import Callable, Optional, Union, cast

import numpy as np
from PIL import Image

from psd_tools.api import numpy_io, pil_io
from psd_tools.api.layers import AdjustmentLayer, GroupMixin, Layer
from psd_tools.api.psd_image import PSDImage
from psd_tools.api.utils import EXPECTED_CHANNELS
from psd_tools.composite import paint, utils, vector
from psd_tools.composite.blend import BLEND_FUNC, normal
from psd_tools.composite.effects import draw_stroke_effect
from psd_tools.constants import BlendMode, ColorMode, Resource, Tag

logger = logging.getLogger(__name__)


def composite_pil(
    layer: Union[Layer, PSDImage],
    color: Union[float, tuple[float, ...], np.ndarray],
    alpha: Union[float, np.ndarray],
    viewport: Optional[tuple[int, int, int, int]],
    layer_filter: Optional[Callable],
    force: bool,
    as_layer: bool = False,
    apply_icc: bool = True,
) -> Union[Image.Image, None]:
    """
    Composite layers and return a PIL Image.

    This function composites the given layer or document into a PIL Image,
    applying blend modes, effects, and color management.

    Args:
        layer: Layer or PSDImage to composite
        color: Initial backdrop color (0.0-1.0). Can be scalar, tuple, or ndarray
        alpha: Initial backdrop alpha (0.0-1.0). Can be scalar or ndarray
        viewport: Bounding box (left, top, right, bottom) to composite. If None, uses layer bounds
        layer_filter: Optional callable to filter which layers to composite. Should return True to include
        force: If True, force re-rendering of all layers (ignore cached pixels)
        as_layer: If True, apply layer blend modes (default: False for document-level compositing)
        apply_icc: If True, apply ICC profile color correction (default: True)

    Returns:
        PIL Image with composited result, or None if viewport is empty

    Note:
        - Requires optional composite dependencies (aggdraw, scipy, scikit-image)
        - LAB and Duotone color modes have limited blending support
        - Alpha channel handling varies by color mode
    """
    UNSUPPORTED_MODES = {
        ColorMode.DUOTONE,
        ColorMode.LAB,
    }
    psd_image = getattr(layer, "_psd", layer)
    assert isinstance(psd_image, PSDImage)
    color_mode = psd_image.color_mode
    if color_mode in UNSUPPORTED_MODES:
        logger.warning("Unsupported blending color space: %s" % (color_mode))

    color, _, alpha = composite(
        layer,
        color=color,
        alpha=alpha,
        viewport=viewport,
        layer_filter=layer_filter,
        force=force,
        as_layer=as_layer,
    )

    mode = pil_io.get_pil_mode(color_mode)
    if mode == "P":
        mode = "RGB"
    # Skip only when there is a preview image and it has no alpha.
    delay_alpha_application = color_mode not in (ColorMode.GRAYSCALE, ColorMode.RGB)
    skip_alpha = not force and (
        delay_alpha_application
        or (
            isinstance(layer, PSDImage)
            and layer.has_preview()
            and not numpy_io.has_transparency(layer)
        )
    )
    logger.debug("Skipping alpha: %g" % skip_alpha)
    if not skip_alpha:
        color = np.concatenate((color, alpha), 2)
        mode += "A"
    assert isinstance(color, np.ndarray)
    if mode in ("1", "L"):
        color = color[:, :, 0]
    if color.shape[0] == 0 or color.shape[1] == 0:
        return None
    image = Image.fromarray((255 * color).astype(np.uint8), mode)
    alpha_as_image = None
    if not force and delay_alpha_application:
        alpha_as_image = Image.fromarray(
            (255 * np.squeeze(alpha, axis=2)).astype(np.uint8), "L"
        )
    icc = None
    psd_image = layer if isinstance(layer, PSDImage) else layer._psd
    assert psd_image is not None
    if apply_icc and Resource.ICC_PROFILE in psd_image.image_resources:
        icc = psd_image.image_resources.get_data(Resource.ICC_PROFILE)
    return pil_io.post_process(image, alpha_as_image, icc)


def composite(
    group: Union[Layer, PSDImage],
    color: Union[float, tuple[float, ...], np.ndarray] = 1.0,
    alpha: Union[float, np.ndarray] = 0.0,
    viewport: Optional[tuple[int, int, int, int]] = None,
    layer_filter: Optional[Callable] = None,
    force: bool = False,
    as_layer: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Composite layers and return NumPy arrays.

    This function composites the given layer or document into NumPy arrays
    representing color, shape, and alpha channels. It applies layer blending,
    effects, masks, and clipping according to the PSD specification.

    Args:
        group: Layer or PSDImage to composite
        color: Initial backdrop color (0.0-1.0, default: 1.0). Can be:
            - Scalar (float): Applied to all channels
            - Tuple: Per-channel values (R,G,B or C,M,Y,K)
            - ndarray: Full backdrop image
        alpha: Initial backdrop alpha (0.0-1.0, default: 0.0). Can be scalar or ndarray
        viewport: Bounding box (left, top, right, bottom) to composite. If None, uses layer bounds
        layer_filter: Optional callable(layer) -> bool to filter which layers to composite
        force: If True, force re-rendering of all layers including vector shapes and fills
        as_layer: If True, treat the group as a layer (apply blend mode to backdrop)

    Returns:
        Tuple of (color, shape, alpha) as float32 ndarrays with shape (height, width, channels):
            - color: RGB/CMYK/Grayscale values in range [0.0, 1.0]
            - shape: Layer shape/coverage mask in range [0.0, 1.0]
            - alpha: Composite alpha channel in range [0.0, 1.0]

    Examples:
        >>> from psd_tools import PSDImage
        >>> psd = PSDImage.open('example.psd')
        >>> color, shape, alpha = composite(psd)
        >>> # Apply custom backdrop
        >>> color, shape, alpha = composite(psd, color=(1.0, 0.0, 0.0), alpha=1.0)
        >>> # Force re-render vector layers
        >>> color, shape, alpha = composite(psd, force=True)
        >>> # Composite only visible layers
        >>> color, shape, alpha = composite(psd, layer_filter=lambda l: l.visible)

    Note:
        - Requires optional composite dependencies (aggdraw, scipy, scikit-image) for:
            - Vector shape rendering (aggdraw)
            - Gradient fills (scipy)
            - Layer effects (scikit-image)
        - Adjustment layers have limited support
        - Text rendering is not supported (text layers show as raster if available)
    """
    if viewport is None:
        if isinstance(group, PSDImage):
            viewport = group.viewbox
        else:
            viewport = group.bbox
            if viewport == (0, 0, 0, 0):
                assert group._psd is not None
                viewport = group._psd.viewbox
    assert viewport is not None

    if isinstance(group, PSDImage) and len(group) == 0:
        color, shape = group.numpy("color"), group.numpy("shape")
        if viewport != group.viewbox:
            color = paste(viewport, group.bbox, color, 1.0)
            shape = paste(viewport, group.bbox, shape)
        return color, shape, shape

    if isinstance(color, float):
        psd_image = group if isinstance(group, PSDImage) else group._psd
        assert psd_image is not None
        color_mode = psd_image.color_mode
        assert isinstance(color_mode, ColorMode)
        color = (color,) * EXPECTED_CHANNELS[color_mode]

    isolated = False
    if not isinstance(group, PSDImage):
        isolated = group.blend_mode != BlendMode.PASS_THROUGH

    layer_filter = layer_filter or Layer.is_visible

    compositor = Compositor(viewport, color, alpha, isolated, layer_filter, force)
    target_group = group if isinstance(group, GroupMixin) and not as_layer else [group]
    for layer in target_group:  # type: ignore
        compositor.apply(layer)  # type: ignore[arg-type]
    return compositor.finish()


def paste(
    viewport: tuple[int, int, int, int],
    bbox: tuple[int, int, int, int],
    values: np.ndarray,
    background: Optional[float] = None,
) -> np.ndarray:
    """Change to the specified viewport."""
    shape = (viewport[3] - viewport[1], viewport[2] - viewport[0], values.shape[2])
    view = (
        np.full(shape, background, dtype=np.float32)
        if background
        else np.zeros(shape, dtype=np.float32)
    )
    inter = utils.intersect(viewport, bbox)
    if inter == (0, 0, 0, 0):
        return view

    v = (
        inter[0] - viewport[0],
        inter[1] - viewport[1],
        inter[2] - viewport[0],
        inter[3] - viewport[1],
    )
    b = (inter[0] - bbox[0], inter[1] - bbox[1], inter[2] - bbox[0], inter[3] - bbox[1])
    view[v[1] : v[3], v[0] : v[2], :] = values[b[1] : b[3], b[0] : b[2], :]
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
        viewport: tuple[int, int, int, int],
        color: Union[float, tuple[float, ...], np.ndarray] = 1.0,
        alpha: Union[float, np.ndarray] = 0.0,
        isolated: bool = False,
        layer_filter: Optional[Callable] = None,
        force: bool = False,
    ):
        self._viewport = viewport
        self._layer_filter = layer_filter
        self._force = force
        self._clip_mask = 1.0

        if isolated:
            self._alpha_0 = np.zeros((self.height, self.width, 1), dtype=np.float32)
        elif isinstance(alpha, np.ndarray):
            self._alpha_0 = alpha
        else:
            self._alpha_0 = np.full(
                (self.height, self.width, 1), alpha, dtype=np.float32
            )

        if isinstance(color, np.ndarray):
            self._color_0 = color
        else:
            channels = 1 if isinstance(color, float) else len(color)
            self._color_0 = np.full(
                (self.height, self.width, channels), color, dtype=np.float32
            )

        self._shape_g = np.zeros((self.height, self.width, 1), dtype=np.float32)
        self._alpha_g = np.zeros((self.height, self.width, 1), dtype=np.float32)
        self._color = self._color_0
        self._alpha = self._alpha_0

    def apply(self, layer: Layer, clip_compositing: bool = False) -> None:
        logger.debug("Compositing %s" % layer)

        if self._layer_filter is not None and not self._layer_filter(layer):
            logger.debug("Ignore %s" % layer)
            return
        if isinstance(layer, AdjustmentLayer):
            logger.debug("Ignore adjustment %s" % layer)
            return
        if utils.intersect(self._viewport, layer.bbox) == (0, 0, 0, 0):
            logger.debug("Out of viewport %s" % (layer))
            return
        if not clip_compositing and layer.clipping:
            return

        knockout = bool(layer.tagged_blocks.get_data(Tag.KNOCKOUT_SETTING, 0))
        if isinstance(layer, GroupMixin):
            color, shape, alpha = self._get_group(layer, knockout)
        else:
            color, shape, alpha = self._get_object(layer)

        # Composite clip layers.
        if layer.has_clip_layers():
            color = self._apply_clip_layers(layer, color, alpha)

        # Apply masks and opacity.
        shape_mask, opacity_mask = self._get_mask(layer)
        shape_const, opacity_const = self._get_const(layer)
        shape *= shape_mask
        alpha *= shape_mask * opacity_mask * opacity_const

        # TODO: Tag.BLEND_INTERIOR_ELEMENTS controls how inner effects apply.

        # TODO: Apply before effects
        self._apply_source(
            color, shape * shape_const, alpha * shape_const, layer.blend_mode, knockout
        )

        # TODO: Apply after effects
        self._apply_color_overlay(layer, color, shape, alpha)
        self._apply_pattern_overlay(layer, color, shape, alpha)
        self._apply_gradient_overlay(layer, color, shape, alpha)
        if (
            (self._force and layer.has_vector_mask())
            or (not layer.has_pixels())
            and utils.has_fill(layer)
        ):
            self._apply_stroke_effect(layer, color, shape_mask, alpha)
        else:
            self._apply_stroke_effect(layer, color, shape, alpha)

    def _apply_source(
        self,
        color: np.ndarray,
        shape: np.ndarray,
        alpha: np.ndarray,
        blend_mode: BlendMode,
        knockout: bool = False,
    ) -> None:
        if self._color_0.shape[2] == 1 and 1 < color.shape[2]:
            self._color_0 = np.repeat(self._color_0, color.shape[2], axis=2)
        if self._color.shape[2] == 1 and 1 < color.shape[2]:
            self._color = np.repeat(self._color, color.shape[2], axis=2)

        self._shape_g = cast(np.ndarray, utils.union(self._shape_g, shape))
        if knockout:
            self._alpha_g = (
                (1.0 - shape) * self._alpha_g + (shape - alpha) * self._alpha_0 + alpha
            )
        else:
            self._alpha_g = cast(np.ndarray, utils.union(self._alpha_g, alpha))
        alpha_previous = self._alpha
        self._alpha = cast(np.ndarray, utils.union(self._alpha_0, self._alpha_g))

        alpha_b = self._alpha_0 if knockout else alpha_previous
        color_b = self._color_0 if knockout else self._color

        blend_fn = BLEND_FUNC.get(blend_mode, normal)
        color_t = (shape - alpha) * alpha_b * color_b + alpha * (
            (1.0 - alpha_b) * color + alpha_b * blend_fn(color_b, color)
        )
        self._color = utils.clip(
            utils.divide(
                (1.0 - shape) * alpha_previous * self._color + color_t, self._alpha
            )
        )

    def finish(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return self.color, self.shape, self.alpha

    @property
    def viewport(self) -> tuple[int, int, int, int]:
        return self._viewport

    @property
    def width(self) -> int:
        return self._viewport[2] - self._viewport[0]

    @property
    def height(self) -> int:
        return self._viewport[3] - self._viewport[1]

    @property
    def color(self) -> np.ndarray:
        return utils.clip(
            self._color
            + (self._color - self._color_0)
            * (utils.divide(self._alpha_0, self._alpha_g) - self._alpha_0)
        )

    @property
    def shape(self) -> np.ndarray:
        return self._shape_g

    @property
    def alpha(self) -> np.ndarray:
        return self._alpha_g

    def _get_group(
        self, layer: Layer, knockout: bool
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        viewport = utils.intersect(self._viewport, layer.bbox)
        if knockout:
            color_b = self._color_0
            alpha_b = self._alpha_0
        else:
            color_b = self._color
            alpha_b = self._alpha

        color, shape, alpha = composite(
            layer,
            paste(viewport, self._viewport, color_b, 1.0),
            paste(viewport, self._viewport, alpha_b),
            viewport,
            layer_filter=self._layer_filter,
            force=self._force,
        )
        color = paste(self._viewport, viewport, color, 1.0)
        shape = paste(self._viewport, viewport, shape)
        alpha = paste(self._viewport, viewport, alpha)

        assert color is not None
        assert shape is not None
        assert alpha is not None
        return color, shape, alpha

    def _get_object(self, layer: Layer) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Get object attributes."""
        color, shape = layer.numpy("color"), layer.numpy("shape")
        if (self._force or not layer.has_pixels()) and utils.has_fill(layer):
            color, shape = paint.create_fill(layer, layer.bbox)
            if shape is None:
                shape = np.ones((layer.height, layer.width, 1), dtype=np.float32)

        if color is None and shape is None:
            # Empty pixel layer.
            color = np.ones((self.height, self.width, 1), dtype=np.float32)
            shape = np.zeros((self.height, self.width, 1), dtype=np.float32)

        if color is None:
            color = np.ones((self.height, self.width, 1), dtype=np.float32)
        else:
            color = paste(self._viewport, layer.bbox, color, 1.0)
        if shape is None:
            shape = np.ones((self.height, self.width, 1), dtype=np.float32)
        else:
            shape = paste(self._viewport, layer.bbox, shape)

        alpha = shape * 1.0  # Constant factor is always 1.

        # TODO: Prepare a test case for clipping mask with stroke to check the order.
        # Apply stroke if any.
        if (
            layer.has_vector_mask()
            and layer.stroke is not None
            and layer.stroke.enabled
        ):
            color_s, shape_s, alpha_s = self._get_stroke(layer)
            compositor = Compositor(self._viewport, color, alpha)
            compositor._apply_source(color_s, shape_s, alpha_s, layer.stroke.blend_mode)
            color, _, _ = compositor.finish()

        assert color is not None
        assert shape is not None
        assert alpha is not None
        return color, shape, alpha

    def _apply_clip_layers(
        self, layer: Layer, color: np.ndarray, alpha: np.ndarray
    ) -> np.ndarray:
        # TODO: Consider Tag.BLEND_CLIPPING_ELEMENTS.
        compositor = Compositor(
            self._viewport,
            color,
            alpha,
            layer_filter=self._layer_filter,
            force=self._force,
        )
        for clip_layer in layer.clip_layers:
            compositor.apply(clip_layer, clip_compositing=True)
        return compositor._color

    def _get_mask(self, layer: Layer) -> tuple[Union[float, np.ndarray], float]:
        """Get mask attributes."""
        shape: Union[float, np.ndarray] = 1.0
        opacity: float = 1.0
        if layer.mask is not None and not layer.mask.disabled:
            # TODO: When force, ignore real mask.
            mask = layer.numpy("mask", real_mask=not self._force)
            if mask is not None:
                shape = paste(
                    self._viewport,
                    layer.mask.bbox,
                    mask,
                    layer.mask.background_color / 255.0,
                )
            if layer.mask.parameters:
                density = layer.mask.parameters.user_mask_density
                if density is None:
                    density = layer.mask.parameters.vector_mask_density
                if density is None:
                    density = 255
                opacity = float(density) / 255.0

        if (
            layer.vector_mask is not None
            and not layer.vector_mask.disabled
            and (
                self._force
                or not layer.has_pixels()
                or (
                    not utils.has_fill(layer)
                    and layer.mask is not None
                    and not layer.mask.has_real()
                )
            )
        ):
            shape_v = vector.draw_vector_mask(layer)
            shape_v = paste(self._viewport, layer._psd.viewbox, shape_v)
            shape *= shape_v

        assert shape is not None
        assert opacity is not None
        return shape, opacity

    def _get_const(self, layer: Layer) -> tuple[float, float]:
        """Get constant attributes."""
        shape = layer.tagged_blocks.get_data(Tag.BLEND_FILL_OPACITY, 255) / 255.0
        opacity = layer.opacity / 255.0
        assert shape is not None
        assert opacity is not None
        return float(shape), opacity

    def _get_stroke(self, layer):
        """Get stroke source."""
        desc = layer.stroke._data
        width = int(desc.get("strokeStyleLineWidth", 1.0))
        viewport = tuple(
            x + d for x, d in zip(layer.bbox, (-width, -width, width, width))
        )
        color, _ = paint.create_fill_desc(
            layer, desc.get("strokeStyleContent"), viewport
        )
        color = paste(self._viewport, viewport, color, 1.0)
        shape = vector.draw_stroke(layer)
        if shape.shape[0] != self.height or shape.shape[1] != self.width:
            bbox = (0, 0, shape.shape[1], shape.shape[0])
            shape = paste(self._viewport, bbox, shape)
        opacity = desc.get("strokeStyleOpacity", 100.0) / 100.0
        alpha = shape * opacity
        return color, shape, alpha

    def _apply_color_overlay(self, layer, color, shape, alpha):
        for effect in layer.effects.find("coloroverlay"):
            color, shape_e = paint.draw_solid_color_fill(
                layer.bbox, layer._psd.color_mode, effect.value
            )
            color = paste(self._viewport, layer.bbox, color, 1.0)
            if shape_e is None:
                shape_e = np.ones((self.height, self.width, 1), dtype=np.float32)
            else:
                shape_e = paste(self._viewport, layer.bbox, shape_e)
            opacity = effect.opacity / 100.0
            self._apply_source(
                color, shape * shape_e, alpha * shape_e * opacity, effect.blend_mode
            )

    def _apply_pattern_overlay(self, layer, color, shape, alpha):
        channels = color.shape[-1]
        for effect in layer.effects.find("patternoverlay"):
            color, shape_e = paint.draw_pattern_fill(
                layer.bbox, layer._psd, effect.value
            )
            if color.shape[-1] == 1 and color.shape[-1] < channels:
                # Pattern has different # color channels here.
                color = np.full([layer.height, layer.width, channels], color)
            assert color.shape[-1] == channels, "Inconsistent pattern channels."

            color = paste(self._viewport, layer.bbox, color, 1.0)
            if shape_e is None:
                shape_e = np.ones((self.height, self.width, 1), dtype=np.float32)
            else:
                shape_e = paste(self._viewport, layer.bbox, shape_e)
            opacity = effect.opacity / 100.0
            self._apply_source(
                color, shape * shape_e, alpha * shape_e * opacity, effect.blend_mode
            )

    def _apply_gradient_overlay(self, layer, color, shape, alpha):
        for effect in layer.effects.find("gradientoverlay"):
            color, shape_e = paint.draw_gradient_fill(
                layer.bbox, layer._psd.color_mode, effect.value
            )
            color = paste(self._viewport, layer.bbox, color, 1.0)
            if shape_e is None:
                shape_e = np.ones((self.height, self.width, 1), dtype=np.float32)
            else:
                shape_e = paste(self._viewport, layer.bbox, shape_e)
            opacity = effect.opacity / 100.0
            self._apply_source(
                color, shape * shape_e, alpha * shape_e * opacity, effect.blend_mode
            )

    def _apply_stroke_effect(self, layer, color, shape, alpha):
        for effect in layer.effects.find("stroke"):
            # Effect must happen at the layer viewport.
            shape_in_bbox = paste(layer.bbox, self._viewport, shape)
            color, shape_in_bbox = draw_stroke_effect(
                layer.bbox, shape_in_bbox, effect.value, layer._psd
            )
            color = paste(self._viewport, layer.bbox, color)
            shape = paste(self._viewport, layer.bbox, shape_in_bbox)
            opacity = effect.opacity / 100.0
            self._apply_source(color, shape, shape * opacity, effect.blend_mode)
