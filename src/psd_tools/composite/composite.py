"""Composite implementation for layer rendering and blending."""

import logging
from collections.abc import Sequence
from typing import Callable, cast

import numpy as np
from PIL import Image

from psd_tools.api import pil_io
from psd_tools.api.layers import AdjustmentLayer, GroupMixin, Layer
from psd_tools.api.protocols import LayerProtocol, PSDProtocol
from psd_tools.api.psd_image import PSDImage
from psd_tools.api.utils import EXPECTED_CHANNELS, check_pixel_size
from psd_tools.composite import paint, utils, vector
from psd_tools.composite.adjustments import ADJUSTMENT_FUNC
from psd_tools.composite.blend import BLEND_FUNC, normal
from psd_tools.composite.effects import draw_stroke_effect
from psd_tools.constants import (
    BlendMode,
    ChannelID,
    ColorMode,
    Knockout,
    Resource,
    Tag,
)

logger = logging.getLogger(__name__)


def composite_pil(
    layer: Layer | PSDImage,
    color: float | Sequence[float] | np.ndarray,
    alpha: float | np.ndarray,
    viewport: tuple[int, int, int, int] | None,
    layer_filter: Callable[[Layer], bool] | None,
    force: bool,
    as_layer: bool = False,
    apply_icc: bool = True,
) -> Image.Image | None:
    """
    Composite layers and return a PIL Image.

    This function composites the given layer or document into a PIL Image,
    applying blend modes, effects, and color management.

    Args:
        layer: Layer or PSDImage to composite
        color: Initial backdrop color (0.0-1.0). Can be a scalar, a
            per-channel sequence, or an ndarray
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

    backdrop_alpha = alpha
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
    # Skip alpha when the color mode requires deferred alpha handling, or
    # when the backdrop is fully opaque (the result is guaranteed opaque).
    delay_alpha_application = color_mode not in (ColorMode.GRAYSCALE, ColorMode.RGB)
    uniform_alpha = _uniform_alpha(backdrop_alpha)
    has_opaque_backdrop = uniform_alpha is not None and uniform_alpha >= 1.0
    skip_alpha = not force and (delay_alpha_application or has_opaque_backdrop)
    logger.debug("Skipping alpha: %s", skip_alpha)
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
    group: Layer | PSDImage,
    color: float | Sequence[float] | np.ndarray = 1.0,
    alpha: float | np.ndarray = 0.0,
    viewport: tuple[int, int, int, int] | None = None,
    layer_filter: Callable[[Layer], bool] | None = None,
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
        color: Initial backdrop color (0.0-1.0, default: 1.0). Can be a scalar
            applied to all channels, a per-channel sequence, or a full
            (height, width, channels) ndarray.
        alpha: Initial backdrop alpha (0.0-1.0, default: 0.0). Can be scalar or ndarray.
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
        - Requires optional composite dependencies (aggdraw, scipy, scikit-image)
          for vector shape rendering, gradient fills, and layer effects.
        - Adjustment layers have limited support.
        - Text rendering is not supported (text layers show as raster if available).
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
        # group.numpy() applies check_pixel_size(group.width, group.height) internally
        # for each call (color + shape), so skip the viewport-based check here to
        # avoid an additional warning/raise on top of those already emitted.
        backdrop_color = color
        backdrop_alpha = alpha
        color, shape = group.numpy("color"), group.numpy("shape")
        if viewport != group.viewbox:
            color = paste(viewport, group.bbox, color, 1.0)
            shape = paste(viewport, group.bbox, shape)
        # A uniformly transparent backdrop contributes nothing, and blending it
        # in anyway would turn fully uncovered pixels white via divide()'s
        # 0 / 0 fallback. Normalize only once past that check, so the backdrop
        # is not expanded to a full canvas for the common default.
        if _uniform_alpha(backdrop_alpha) != 0.0:
            # Sized from the array in hand rather than from the color mode:
            # a multichannel document carries a channel count of its own that
            # EXPECTED_CHANNELS does not predict.
            backdrop = _normalize_backdrop(backdrop_color, backdrop_alpha, *color.shape)
            color, shape = _blend_backdrop(color, shape, *backdrop)
        return color, shape, shape

    _w = viewport[2] - viewport[0]
    _h = viewport[3] - viewport[1]
    _psd = group if isinstance(group, PSDImage) else group._psd
    check_pixel_size(
        _w,
        _h,
        _psd.channels if _psd is not None else 1,
        max_alloc_bytes=_psd._max_alloc_bytes if _psd is not None else None,
    )

    isolated = False
    if not isinstance(group, PSDImage):
        isolated = group.blend_mode != BlendMode.PASS_THROUGH

    # The compositor works exclusively in full-canvas arrays; the scalar and
    # per-channel spellings are a convenience of the public signature, so they
    # are resolved here, once, rather than at each point of use. An isolated
    # group starts transparent, so the caller's alpha is dropped before the
    # canvas is built rather than after.
    backdrop_color, backdrop_alpha = _normalize_backdrop(
        color,
        0.0 if isolated else alpha,
        _h,
        _w,
        EXPECTED_CHANNELS[_psd.color_mode] if _psd is not None else None,
    )

    layer_filter = layer_filter or Layer.is_visible

    compositor = Compositor(
        viewport,
        backdrop_color,
        backdrop_alpha,
        layer_filter,
        force,
        document_backdrop=lambda: _document_backdrop(_psd, viewport),
    )
    target_group = group if isinstance(group, GroupMixin) and not as_layer else [group]
    for layer in target_group:  # type: ignore
        compositor.apply(layer)  # type: ignore[arg-type]
    return compositor.finish()


def paste(
    viewport: tuple[int, int, int, int],
    bbox: tuple[int, int, int, int],
    values: np.ndarray,
    background: float | None = None,
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


def _is_background_layer(layer: "LayerProtocol") -> bool:
    """Whether the layer is Photoshop's Background layer.

    A Background layer is opaque by construction and carries no transparency
    channel, which is what distinguishes it from an ordinary bottom layer that
    merely happens to be fully opaque.
    """
    record = getattr(layer, "_record", None)
    if record is None:
        return False
    return not any(
        channel.id == ChannelID.TRANSPARENCY_MASK for channel in record.channel_info
    )


def _read_knockout(layer: Layer) -> Knockout:
    """Read a layer's knockout setting, tolerating undefined values.

    The tagged block is a raw byte, so a corrupt file -- or one written by a
    future Photoshop or a third-party tool -- can carry a value outside the
    enum. Fall back to NONE with a warning rather than raising: compositing a
    malformed document should degrade, not crash.
    """
    value = layer.tagged_blocks.get_data(Tag.KNOCKOUT_SETTING, 0)
    try:
        return Knockout(value)
    except ValueError:
        logger.warning(
            "Unknown knockout setting %r in %s; compositing without knockout",
            value,
            layer,
        )
        return Knockout.NONE


def _document_backdrop(
    psd: "PSDProtocol | None", viewport: tuple[int, int, int, int]
) -> tuple[np.ndarray, np.ndarray] | None:
    """The backdrop that deep knockout knocks out to.

    Photoshop treats the Background layer as the canvas rather than as an
    ordinary layer: deep knockout removes every ordinary layer beneath the
    knockout group and stops there. Verified against Photoshop 2026 -- with the
    Background converted to an ordinary layer, the same document knocks all the
    way through to transparency instead.

    Returns None when the document has no Background layer, in which case deep
    knockout falls back to the compositor's own initial backdrop.
    """
    if psd is None or len(psd) == 0:
        return None
    bottom = psd[0]
    if not _is_background_layer(bottom):
        return None
    color = bottom.numpy("color")
    if color is None:
        return None
    color = paste(viewport, bottom.bbox, color, 1.0)
    alpha = np.ones((color.shape[0], color.shape[1], 1), dtype=np.float32)
    return color, alpha


def _uniform_alpha(alpha: float | np.ndarray) -> float | None:
    """The backdrop alpha as a plain float when it is a single scalar.

    Returns None for an array-valued backdrop, whose per-pixel alpha cannot be
    reduced to one number. Tested by dimensionality rather than by type so that
    ``1``, ``1.0``, ``np.float32(1.0)`` and ``np.array(1.0)`` all behave alike.
    """
    return float(alpha) if np.ndim(alpha) == 0 else None


def _to_canvas(
    value: float | Sequence[float] | np.ndarray,
    shape: tuple[int, int, int],
    name: str,
) -> np.ndarray:
    """Expand a backdrop component to a full ``(height, width, channels)`` array.

    An array that is already per-pixel is taken as given -- including one whose
    channel count differs from the document's, which the compositor widens on
    demand. Anything else (a scalar, a per-channel sequence) is broadcast.
    """
    array = np.asarray(value, dtype=np.float32)
    if array.ndim == 3:
        if array.shape[:2] != shape[:2]:
            raise ValueError(
                "Backdrop %s covers %r, expected %r to match the viewport"
                % (name, array.shape[:2], shape[:2])
            )
        return array
    try:
        return np.full(shape, array, dtype=np.float32)
    except ValueError:
        raise ValueError(
            "Backdrop %s %r cannot be expanded to %r; pass a scalar, a "
            "per-channel sequence, or a full (height, width, channels) array"
            % (name, value, shape)
        ) from None


def _normalize_backdrop(
    color: float | Sequence[float] | np.ndarray,
    alpha: float | np.ndarray,
    height: int,
    width: int,
    channels: int | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Resolve a backdrop given in any accepted spelling to a pair of arrays.

    The public entry points accept the backdrop as a scalar, a per-channel
    sequence or a ready-made array because that is convenient to call; the
    compositor only ever works with arrays. Converting once here keeps the
    three spellings from being re-interpreted -- inconsistently -- at each use
    site.

    This does materialize a full canvas even for a constant backdrop, exactly
    as ``Compositor`` did before: the scalar spelling is an API convenience,
    not an allocation-avoidance path. (``_get_mask``/``_get_const`` keep their
    scalars for that reason instead.)

    ``channels`` is the document's channel count, or None to infer it from
    ``color`` where no document is available to name a color mode -- the same
    defensive fallback ``check_pixel_size()`` is given in ``composite()``.
    """
    if channels is None:
        channels = 1 if np.ndim(color) == 0 else int(np.shape(color)[-1])
    return (
        _to_canvas(color, (height, width, channels), "color"),
        _to_canvas(alpha, (height, width, 1), "alpha"),
    )


def _blend_backdrop(
    color: np.ndarray,
    shape: np.ndarray,
    backdrop_color: np.ndarray,
    backdrop_alpha: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Blend foreground color/shape over a backdrop using standard "over" compositing."""
    result_alpha = utils.union(shape, backdrop_alpha)
    result_color = utils.clip(
        utils.divide(
            color * shape + backdrop_color * backdrop_alpha * (1.0 - shape),
            result_alpha,
        )
    )
    return result_color, result_alpha


class Compositor(object):
    """Composite context.

    ``color`` and ``alpha`` are the initial backdrop, and must already be
    ``(height, width, channels)`` arrays covering ``viewport``; the public
    entry points normalize the spellings they accept via
    ``_normalize_backdrop()``. An isolated group composites against a
    transparent backdrop, which the caller expresses by passing a zero
    ``alpha`` -- so that canvas is never built only to be discarded.

    Example::

        color, alpha = _normalize_backdrop(1.0, 0.0, height, width, channels)
        compositor = Compositor(group.bbox, color, alpha)
        for layer in group:
            compositor.apply(layer)
        color, shape, alpha = compositor.finish()
    """

    def __init__(
        self,
        viewport: tuple[int, int, int, int],
        color: np.ndarray,
        alpha: np.ndarray,
        layer_filter: Callable[[Layer], bool] | None = None,
        force: bool = False,
        adjustment_isolated: bool = False,
        document_backdrop: Callable[[], tuple[np.ndarray, np.ndarray] | None]
        | None = None,
    ):
        self._viewport = viewport
        self._layer_filter = layer_filter
        self._force = force
        self._clip_mask = 1.0
        self._adjustment_isolated = adjustment_isolated
        # What Knockout.DEEP knocks out to. Inherited by pass-through
        # sub-compositors and reset at every isolation boundary, so deep
        # knockout escapes pass-through groups but stops at an isolated one.
        # None means "this compositor's own initial backdrop".
        #
        # Resolved lazily: it decodes the Background layer, and the vast
        # majority of documents never contain a deep knockout at all.
        self._document_backdrop_fn = document_backdrop
        self._document_backdrop_resolved = False
        self._document_backdrop: tuple[np.ndarray, np.ndarray] | None = None

        self._alpha_0 = alpha
        self._color_0 = color

        self._shape_g = np.zeros((self.height, self.width, 1), dtype=np.float32)
        self._alpha_g = np.zeros((self.height, self.width, 1), dtype=np.float32)
        self._color = self._color_0
        self._alpha = self._alpha_0

    def apply(self, layer: Layer, clip_compositing: bool = False) -> None:
        logger.debug("Compositing %s" % layer)

        if self._layer_filter is not None and not self._layer_filter(layer):
            logger.debug("Ignore %s" % layer)
            return
        if (utils.intersect(self._viewport, layer.bbox) == (0, 0, 0, 0)) and not (
            isinstance(layer, AdjustmentLayer) or isinstance(layer, GroupMixin)
        ):
            logger.debug("Out of viewport %s" % (layer))
            return
        if not clip_compositing and layer.clipping:
            return

        is_adjustment_isolated = None
        knockout = _read_knockout(layer)
        if isinstance(layer, AdjustmentLayer):
            self._apply_adjustment(layer)
            return
        elif isinstance(layer, GroupMixin):
            color, shape, alpha, is_adjustment_isolated = self._get_group(
                layer, knockout
            )
        else:
            color, shape, alpha = self._get_object(layer)

        # Composite clip layers.
        if layer.has_clip_layers():
            color = self._apply_clip_layers(layer, color, alpha)

        # Apply masks and opacity.
        shape_mask, opacity_mask = self._get_mask(layer)
        shape_const, opacity_const = self._get_const(layer)
        mask = shape_mask * opacity_mask * opacity_const
        shape *= shape_mask
        alpha *= mask

        # TODO: Tag.BLEND_INTERIOR_ELEMENTS controls how inner effects apply.

        full_passthrough = (
            layer.blend_mode == BlendMode.PASS_THROUGH
            and is_adjustment_isolated is False
        )  # when adjustments are isolated, passthrough composing fallbacks to over composing
        if full_passthrough:
            self._apply_passthrough_source(
                color, shape * shape_const, alpha * shape_const, mask * shape_const
            )
        else:
            # Fill opacity (``shape_const``) scales how much the source
            # contributes, but under knockout the hole is punched by the
            # source's full coverage -- so ``shape`` stays unscaled there and
            # ``(1 - shape)`` in _apply_source() removes the whole backdrop.
            self._apply_source(
                color,
                shape if knockout else shape * shape_const,
                alpha * shape_const,
                layer.blend_mode,
                knockout,
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

    def _apply_passthrough_source(
        self,
        color: np.ndarray,
        shape: np.ndarray,
        alpha: np.ndarray,
        mask: float | np.ndarray,
    ) -> None:
        if self._color_0.shape[2] == 1 and 1 < color.shape[2]:
            self._color_0 = np.repeat(self._color_0, color.shape[2], axis=2)
        if self._color.shape[2] == 1 and 1 < color.shape[2]:
            self._color = np.repeat(self._color, color.shape[2], axis=2)

        # ``color`` is the group already composited over this backdrop, because a
        # pass-through group is rendered by a non-isolated sub-compositor seeded
        # with the backdrop. Re-applying the group therefore means interpolating
        # between the backdrop and that result by the group opacity/mask, which
        # must happen in premultiplied space so a transparent (or partially
        # transparent) backdrop does not bleed its color into the result.
        #
        # TODO(#707): knockout is ignored here while _get_group() honors it, so
        # a knockout pass-through group interpolates against a different backdrop
        # than it was composited over, and the result varies with nesting depth.
        color_b = self._color
        alpha_b = self._alpha

        self._shape_g = cast(np.ndarray, utils.union(self._shape_g, shape))
        self._alpha_g = cast(np.ndarray, utils.union(self._alpha_g, alpha))
        # union(alpha_b, alpha) -- ``alpha`` is the group alpha already scaled by
        # ``mask``, which is what the premultiplied interpolation resolves to.
        self._alpha = cast(np.ndarray, utils.union(self._alpha_0, self._alpha_g))

        color_t = (1.0 - mask) * alpha_b * color_b + (
            mask * alpha_b + alpha * (1.0 - alpha_b)
        ) * color
        self._color = utils.clip(
            np.where(
                self._alpha > 0.0,
                utils.divide(color_t, self._alpha),
                # Fully transparent, so the color is arbitrary; ``color`` merely
                # avoids utils.divide()'s 0 / 0 -> 1.0 (white) fallback.
                color,
            )
        )

    def _resolve_document_backdrop(self) -> tuple[np.ndarray, np.ndarray] | None:
        if not self._document_backdrop_resolved:
            self._document_backdrop_resolved = True
            if self._document_backdrop_fn is not None:
                self._document_backdrop = self._document_backdrop_fn()
        return self._document_backdrop

    def _knockout_backdrop(
        self, knockout: Knockout, color: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """The (color, alpha) pair that ``knockout`` knocks out to.

        SHALLOW knocks out to this compositor's own initial backdrop, i.e. the
        enclosing group's. DEEP knocks out to the document backdrop, which is
        inherited across pass-through groups and reset at isolation boundaries;
        where there is none it degrades to the same backdrop as SHALLOW.
        """
        if knockout == Knockout.DEEP:
            resolved = self._resolve_document_backdrop()
            if resolved is not None:
                color_b, alpha_b = resolved
                if color_b.shape[2] == 1 and 1 < color.shape[2]:
                    color_b = np.repeat(color_b, color.shape[2], axis=2)
                return color_b, alpha_b
        return self._color_0, self._alpha_0

    def _apply_source(
        self,
        color: np.ndarray,
        shape: np.ndarray,
        alpha: np.ndarray,
        blend_mode: BlendMode,
        knockout: Knockout = Knockout.NONE,
    ) -> None:
        if self._color_0.shape[2] == 1 and 1 < color.shape[2]:
            self._color_0 = np.repeat(self._color_0, color.shape[2], axis=2)
        if self._color.shape[2] == 1 and 1 < color.shape[2]:
            self._color = np.repeat(self._color, color.shape[2], axis=2)

        knockout_color, knockout_alpha = self._knockout_backdrop(knockout, color)

        self._shape_g = cast(np.ndarray, utils.union(self._shape_g, shape))
        if knockout:
            self._alpha_g = (
                (1.0 - shape) * self._alpha_g + (shape - alpha) * knockout_alpha + alpha
            )
        else:
            self._alpha_g = cast(np.ndarray, utils.union(self._alpha_g, alpha))
        alpha_previous = self._alpha
        self._alpha = cast(np.ndarray, utils.union(self._alpha_0, self._alpha_g))

        alpha_b = knockout_alpha if knockout else alpha_previous
        color_b = knockout_color if knockout else self._color

        blend_fn = BLEND_FUNC.get(blend_mode, normal)
        color_t = (shape - alpha) * alpha_b * color_b + alpha * (
            (1.0 - alpha_b) * color + alpha_b * blend_fn(color_b, color)
        )
        self._color = utils.clip(
            utils.divide(
                (1.0 - shape) * alpha_previous * self._color + color_t, self._alpha
            )
        )

    def _apply_adjustment(self, layer: AdjustmentLayer) -> None:
        adjustment_fn = ADJUSTMENT_FUNC.get(layer.kind)
        colormode = layer._psd.color_mode

        if adjustment_fn is None:
            logger.debug("Unsupported adjustment layer: %s", layer.kind)
            return
        if colormode not in (ColorMode.CMYK, ColorMode.GRAYSCALE, ColorMode.RGB):
            logger.debug(
                "Unsupported color mode for adjustment %s: %s", layer.kind, colormode
            )
            return

        backdrop_color = self._color
        transformed_color = adjustment_fn(backdrop_color, colormode, layer)

        if layer.has_clip_layers():
            transformed_color = self._apply_clip_layers(
                layer, transformed_color, self._alpha
            )

        shape_mask, opacity_mask = self._get_mask(layer)
        shape_const, opacity_const = self._get_const(layer)

        shape = shape_mask * shape_const
        opacity = shape * opacity_mask * opacity_const

        blend_fn = BLEND_FUNC.get(layer.blend_mode, normal)
        blended = blend_fn(backdrop_color, transformed_color)

        if self._adjustment_isolated:
            self._color = utils.clip(
                backdrop_color + self._shape_g * opacity * (blended - backdrop_color)
            )
        else:
            self._color = utils.clip(
                backdrop_color + opacity * (blended - backdrop_color)
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
        self, layer: Layer, knockout: Knockout
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, bool]:
        is_passthrough = layer.blend_mode == BlendMode.PASS_THROUGH
        viewport = (
            self._viewport
            if is_passthrough
            else utils.intersect(self._viewport, layer.bbox)
        )
        if knockout:
            color_b, alpha_b = self._knockout_backdrop(knockout, self._color_0)
        else:
            color_b = self._color
            alpha_b = self._alpha

        # adjustments don't pass-through layers if the group layer has clip layers or its fill attribute is not 100.
        shape_const, _ = self._get_const(layer)
        isolate_adjustments = shape_const < 1.0 or layer.has_clip_layers()

        # A pass-through group is not an isolation boundary, so deep knockout
        # inside it still reaches the document backdrop; an isolated group is,
        # so deep knockout there stops at the group's own backdrop.
        document_backdrop = None
        if is_passthrough and self._document_backdrop_fn is not None:
            parent_viewport = self._viewport
            resolve_parent = self._resolve_document_backdrop

            def document_backdrop() -> tuple[np.ndarray, np.ndarray] | None:
                resolved = resolve_parent()
                if resolved is None:
                    return None
                backdrop_color, backdrop_alpha = resolved
                return (
                    paste(viewport, parent_viewport, backdrop_color, 1.0),
                    paste(viewport, parent_viewport, backdrop_alpha),
                )

        # Only a pass-through group inherits the enclosing alpha; an isolated
        # one starts transparent, so that paste is skipped rather than made and
        # thrown away.
        group_alpha = (
            paste(viewport, self._viewport, alpha_b)
            if is_passthrough
            else np.zeros(
                (viewport[3] - viewport[1], viewport[2] - viewport[0], 1),
                dtype=np.float32,
            )
        )
        group_compositor = Compositor(
            viewport,
            color=paste(viewport, self._viewport, color_b, 1.0),
            alpha=group_alpha,
            layer_filter=self._layer_filter,
            force=self._force,
            adjustment_isolated=self._adjustment_isolated or isolate_adjustments,
            document_backdrop=document_backdrop,
        )

        for sublayer in cast(GroupMixin, layer):
            group_compositor.apply(sublayer)

        if isolate_adjustments:
            color = group_compositor.color  # prevents backdrop color contamination
        else:
            color = group_compositor._color
        shape = group_compositor._shape_g
        alpha = group_compositor._alpha_g

        color = paste(self._viewport, viewport, color, 1.0)
        shape = paste(self._viewport, viewport, shape)
        alpha = paste(self._viewport, viewport, alpha)

        assert color is not None
        assert shape is not None
        assert alpha is not None
        return color, shape, alpha, isolate_adjustments

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

    def _get_mask(self, layer: Layer) -> tuple[float | np.ndarray, float]:
        """Get mask attributes.

        The scalar 1.0 default is an allocation-avoidance path, not an API
        convenience like the backdrop spellings: most layers have no mask, and
        materializing an all-ones canvas for each of them is pure waste.
        """
        shape: float | np.ndarray = 1.0
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

                density = float(density) / 255.0
                shape = density * shape + (1 - density)

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

            if layer.mask is not None and layer.mask.parameters:
                density_v = layer.mask.parameters.vector_mask_density
            else:
                density_v = None

            if density_v is not None:
                d = float(density_v) / 255.0
                shape = d * shape + (1.0 - d)

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

    def _get_stroke(self, layer: Layer) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Get stroke source."""
        if layer.stroke is None:
            raise ValueError("Layer does not have stroke data.")
        desc = layer.stroke._data
        width = int(desc.get("strokeStyleLineWidth", 1.0))
        viewport = cast(
            tuple[int, int, int, int],
            tuple(x + d for x, d in zip(layer.bbox, (-width, -width, width, width))),
        )
        color, _ = paint.create_fill_desc(
            layer, desc.get("strokeStyleContent"), viewport
        )
        if color is None:
            raise ValueError(
                "Unsupported stroke fill descriptor in layer strokeStyleContent"
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
