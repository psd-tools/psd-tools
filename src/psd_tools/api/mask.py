"""
Mask module.

Masks are used to determine the visible area of a layer.
There are two types of masks: user mask and vector mask.
User mask refers to any pixel-based mask, whereas vector mask refers to a mask from a shape path.

Masks are accessible from the layer's `mask` property::

    from psd_tools import PSDImage

    psdimage = PSDImage.open('example.psd')
    layer = psdimage[0]
    mask = layer.mask
    assert mask is not None
    print(mask.bbox)  # (left, top, right, bottom)

    mask_image = mask.topil()  # Show the mask as a PIL Image.
    if mask_image is not None:
        mask_image.save("mask.png")

To create a new mask, use the layer's :py:func:`~psd_tools.api.layers.Layer.create_mask` method::

    from psd_tools import PSDImage
    from PIL import Image

    psdimage = PSDImage.new(mode="RGB", size=(128, 128))
    layer = psdimage.create_pixel_layer(Image.new("RGB", (128, 128)))
    layer.create_mask(Image.new("L", (128, 128), 255))

Note that creating a pixel layer from RGBA image will automatically create a user mask::

    psdimage = PSDImage.new(mode="RGB", size=(128, 128))
    layer = psdimage.create_pixel_layer(Image.new("RGBA", (128, 128)))

"""

import logging
from typing import Any, cast

from PIL import Image

from psd_tools.api.protocols import LayerProtocol, MaskProtocol
from psd_tools.constants import ChannelID
from psd_tools.psd.layer_and_mask import MaskData, MaskFlags

logger = logging.getLogger(__name__)


class Mask(MaskProtocol):
    """Mask data attached to a layer.

    There are two distinct internal mask data: user mask and vector mask.
    User mask refers any pixel-based mask whereas vector mask refers a mask
    from a shape path. Internally, two masks are combined and referred
    real mask.
    """

    def __init__(self, layer: LayerProtocol):
        self._layer = layer
        self._data: MaskData = cast(MaskData, layer._record.mask_data)

    @property
    def background_color(self) -> int:
        """Background color."""
        if self.has_real():
            real_bg = self._data.real_background_color
            return real_bg if real_bg is not None else self._data.background_color
        return self._data.background_color

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """BBox"""
        return self.left, self.top, self.right, self.bottom

    @property
    def left(self) -> int:
        """Left coordinate."""
        if self.has_real():
            return (
                self._data.real_left
                if self._data.real_left is not None
                else self._data.left
            )
        return self._data.left

    @property
    def right(self) -> int:
        """Right coordinate."""
        if self.has_real():
            return (
                self._data.real_right
                if self._data.real_right is not None
                else self._data.right
            )
        return self._data.right

    @property
    def top(self) -> int:
        """Top coordinate."""
        if self.has_real():
            return (
                self._data.real_top
                if self._data.real_top is not None
                else self._data.top
            )
        return self._data.top

    @property
    def bottom(self) -> int:
        """Bottom coordinate."""
        if self.has_real():
            return (
                self._data.real_bottom
                if self._data.real_bottom is not None
                else self._data.bottom
            )
        return self._data.bottom

    @property
    def width(self) -> int:
        """Width."""
        return self.right - self.left

    @property
    def height(self) -> int:
        """Height."""
        return self.bottom - self.top

    @property
    def size(self) -> tuple[int, int]:
        """(Width, Height) tuple."""
        return self.width, self.height

    @property
    def disabled(self) -> bool:
        """Disabled."""
        return self._data.flags.mask_disabled

    @disabled.setter
    def disabled(self, value: bool) -> None:
        self._data.flags.mask_disabled = value
        self._layer._psd._mark_updated()

    @property
    def flags(self) -> MaskFlags:
        """Flags."""
        return self._data.flags

    @property
    def parameters(self) -> Any:
        """Parameters."""
        return self._data.parameters

    @property
    def real_flags(self) -> MaskFlags | None:
        """Real flag."""
        return cast(MaskFlags | None, self._data.real_flags)

    @property
    def data(self) -> MaskData:
        """Return raw mask data, or None if no data."""
        return self._data

    def has_real(self) -> bool:
        """Return True if the mask has real flags."""
        return self.real_flags is not None and self.real_flags.parameters_applied

    def topil(
        self, real: bool = True, layer_sized: bool = False, **kwargs: Any
    ) -> Image.Image | None:
        """
        Get PIL Image of the mask.

        :param real: When True, returns pixel + vector mask combined.
        :param layer_sized: When True, returns a layer-sized image pre-filled with
            ``background_color``, with the mask data pasted at the correct position.
            When False (default), returns the raw stored mask data at mask dimensions.
        :return: PIL Image object, or None if the mask is empty.
        """
        if real and self.has_real():
            channel = ChannelID.REAL_USER_LAYER_MASK
            offset_left = (self._data.real_left or 0) - self._layer.left
            offset_top = (self._data.real_top or 0) - self._layer.top
            real_bg = self._data.real_background_color
            bg = real_bg if real_bg is not None else self._data.background_color
        else:
            channel = ChannelID.USER_LAYER_MASK
            offset_left = self._data.left - self._layer.left
            offset_top = self._data.top - self._layer.top
            bg = self._data.background_color

        raw = self._layer.topil(channel, **kwargs)
        if raw is None or not layer_sized:
            return raw

        # Compose a full layer-sized mask applying background_color outside stored bbox.
        # Out-of-bounds mask data is clipped naturally by Image.paste.
        full = Image.new(raw.mode, self._layer.size, bg)
        full.paste(raw, (offset_left, offset_top))
        return full

    def __repr__(self) -> str:
        return "%s(offset=(%d,%d) size=%dx%d)" % (
            self.__class__.__name__,
            self.left,
            self.top,
            self.width,
            self.height,
        )
