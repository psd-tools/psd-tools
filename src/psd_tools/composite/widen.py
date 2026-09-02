"""Widening a single-channel array to a document's channel count.

The compositor's canvases keep a fixed width for their whole lifetime, so a
backdrop that arrives one channel wide has to be widened once at the point it
is handed over, and a source that arrives one channel wide is widened at the
same point so that what a grey means is the document's answer rather than the
blend arithmetic's (#749). Replicating the value across every channel is
correct for RGB -- a grey ``g`` is ``(g, g, g)`` -- and wrong for everything
else: ``(g, g, g, g)`` in CMYK is a heavily over-inked colour, and a lightness
copied into Lab's a/b axes is not neutral (#722).

What Photoshop actually does for CMYK is a profile-driven conversion, not a
formula. Scripted against Photoshop 2026 with its default CMYK working space,
a mid grey is a heavy CMY build carrying almost no black::

    grey  Photoshop        K-only guess    replication
    0.25  67.5 60.6 59.6 46.7   0  0  0 75   75 75 75 75
    0.50  51.6 43.2 43.2  7.6   0  0  0 50   50 50 50 50
    0.75  24.7 19.6 20.1  0.0   0  0  0 25   25 25 25 25

(all three in ink %, so they compare; the arrays themselves hold ``1 - ink``.)
So this module transforms through the document's own embedded ICC profile and
falls back to a formula only when there is no profile to use.

The numbers above are Photoshop's default CMYK space, U.S. Web Coated (SWOP)
v2. ``tests/psd_files/cmyk-gray-ramp.psd`` is the same experiment saved as a
fixture -- a grey ramp converted to CMYK by Photoshop with that profile
embedded -- and is what the tests pin this against, to within 3.6/255 where
replication is out by 107/255.
"""

from __future__ import annotations

import hashlib
import io
import logging
from typing import TYPE_CHECKING, Callable

import numpy as np

from psd_tools.color_convert import LAB_NEUTRAL_CHROMA
from psd_tools.constants import ColorMode, Resource

if TYPE_CHECKING:
    from psd_tools.api.protocols import PSDProtocol

logger = logging.getLogger(__name__)

# The grey ramp the CMYK lookup table is built over. 256 entries put adjacent
# rows within 3/255 of each other, so interpolating between them rather than
# taking the nearest costs almost nothing and keeps a 16- or 32-bit canvas
# smooth. It does not make the result more precise than 8 bit: ImageCms hands
# back uint8 ink, so the curve being interpolated is quantized whatever the
# canvas depth.
_RAMP = np.linspace(0.0, 1.0, 256, dtype=np.float32)

# Building a transform from the 557 KB SWOP profile costs ~20 ms, a visible tax
# on every composite() call. Keyed on a digest rather than on the profile bytes
# so that the cache does not pin a half-megabyte buffer per profile for the
# life of the process.
_LUT_CACHE: dict[bytes, np.ndarray | None] = {}


def _build_cmyk_lut(icc_profile: bytes) -> np.ndarray | None:
    """Return a ``(256, 4)`` canvas-space CMYK ramp, or None if unavailable.

    The source profile is sRGB because that is what the exit transform's
    destination is: :py:func:`psd_tools.api.pil_io._apply_icc` hard-codes
    ``createProfile("sRGB")``, so entering through anything else would mean a
    grey no longer survives the round trip out. The rendering intent is
    perceptual for the same reason -- ``profileToProfile()`` is called there
    without one and Pillow's default is perceptual. It is not a free choice:
    relative colorimetric moves the result by up to 53/255, and perceptual is
    also the one that reproduces Photoshop's own numbers.
    """
    try:
        from PIL import Image, ImageCms  # noqa: PLC0415
    except ImportError:
        logger.debug("Cannot widen through ICC: install little-cms")
        return None

    try:
        with io.BytesIO(icc_profile) as f:
            out_profile = ImageCms.ImageCmsProfile(f)
        transform = ImageCms.buildTransform(
            ImageCms.createProfile("sRGB"),
            out_profile,
            "RGB",
            "CMYK",
            renderingIntent=ImageCms.Intent.PERCEPTUAL,
        )
        ramp = (_RAMP * 255).round().astype(np.uint8)
        source = Image.fromarray(np.repeat(ramp[None, :, None], 3, axis=2), "RGB")
        ink = np.asarray(ImageCms.applyTransform(source, transform), dtype=np.float32)
    except Exception as e:
        # A CMYK-mode document can carry a profile that is not a CMYK one, and
        # buildTransform() raises on it. pil_io._apply_icc() has the same shape.
        logger.debug("Cannot widen through ICC: %s", e)
        return None

    # The transform yields ink; the canvas counts what is left (#747).
    return 1.0 - ink.reshape(256, 4) / 255.0


def _cmyk_lut(key: bytes, icc_profile: bytes) -> np.ndarray | None:
    """Look the table up by a digest *make_widen* has already computed.

    The digest is the caller's to supply because hashing the profile costs
    ~180 us for a press profile -- more than the lookup it guards -- and it
    would otherwise be paid on every widen call rather than once per document.
    """
    if key not in _LUT_CACHE:
        # A failed build is cached too: it costs as much as a successful one
        # and will fail again for the same profile.
        _LUT_CACHE[key] = _build_cmyk_lut(icc_profile)
    return _LUT_CACHE[key]


def _apply_lut(color: np.ndarray, lut: np.ndarray) -> np.ndarray:
    # np.interp clamps to the ramp's endpoints, so a 32-bit canvas carrying
    # values outside [0, 1] is pinned to black or white here rather than
    # extrapolated. Replication used to pass those through unchanged.
    gray = color[:, :, 0]
    return np.stack(
        [np.interp(gray, _RAMP, lut[:, i]).astype(np.float32) for i in range(4)],
        axis=2,
    )


def _naive_cmyk(color: np.ndarray) -> np.ndarray:
    """The formula a grey *fill* already converts by, in canvas space.

    ``paint._get_gray()`` sends a grey through ``gray_to_cmyk()`` and inverts
    it, giving ``(1, 1, 1, g)`` -- K-only. Using the same formula here keeps a
    grey backdrop and a grey fill agreeing on a document with no usable
    profile, which matters more than the formula being closer to Photoshop:
    it is not close, and the ICC path above is what handles that case.
    """
    ones = np.ones_like(color)
    return np.concatenate((ones, ones, ones, color), axis=2)


def _lab(color: np.ndarray) -> np.ndarray:
    """A grey is on Lab's neutral axis: a and b are neutral, L carries it.

    ``a``/``b`` are offset-encoded, so neutral is ``128 / 255``; 0.5 truncates
    to byte 127 where Photoshop writes 128 (#743).

    ``L`` is passed through as the grey itself rather than as its L*. This
    deliberately disagrees with the *fill* path, which converts (#752): a
    descriptor carries a colour a person picked in some space, so interpreting
    it is sound, while an arbitrary single-channel array -- a mask, a spot
    plane, a caller's scalar, a grayscale pattern's device grey -- carries no
    such claim, and converting it would invent a colour space it never had. The
    line is drawn at the descriptor, not at the canvas; do not "fix" the
    asymmetry.
    """
    neutral = np.full_like(color, LAB_NEUTRAL_CHROMA)
    return np.concatenate((color, neutral, neutral), axis=2)


def make_widen(psd: "PSDProtocol | None") -> Callable[[np.ndarray, int], np.ndarray]:
    """Build the widening function for *psd*, resolved once per composite.

    Returned as a closure rather than threaded as a document handle because
    four of the call sites are inside ``Compositor``, which holds no ``psd``.
    It also makes the conversion testable without a document.
    """
    color_mode = None
    icc: bytes | None = None
    icc_key: bytes | None = None
    if psd is not None:
        color_mode = psd.color_mode
        if Resource.ICC_PROFILE in psd.image_resources:
            icc = psd.image_resources.get_data(Resource.ICC_PROFILE)
            icc_key = hashlib.sha256(icc).digest()

    def widen(color: np.ndarray, channels: int) -> np.ndarray:
        if color.shape[2] != 1 or channels <= 1:
            return color
        if color_mode == ColorMode.CMYK and channels == 4:
            lut = _cmyk_lut(icc_key, icc) if icc_key and icc else None
            if lut is None:
                logger.debug(
                    "Widening a grey into CMYK without a usable ICC profile; "
                    "falling back to the K-only formula"
                )
                return _naive_cmyk(color)
            return _apply_lut(color, lut)
        if color_mode == ColorMode.LAB and channels == 3:
            return _lab(color)
        # RGB and indexed are correct by replication; a multichannel document's
        # spot inks have no colorimetric reading to convert to, so replicating
        # is the only monotonic thing available.
        return np.repeat(color, channels, axis=2)

    return widen
