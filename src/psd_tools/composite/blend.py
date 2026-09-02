"""
Blend mode implementations.

This module implements Photoshop's blend modes for compositing layers. Blend modes
determine how a layer's colors interact with the layers beneath it. Each function
implements the mathematical formula for a specific blend mode.

The blend functions operate on NumPy arrays with normalized float32 values (0.0-1.0)
representing pixel color channels. They follow Adobe's PDF Blend Mode specification.

Blend mode categories:

**Normal modes:**
- ``normal``: Source replaces backdrop (no blending)

**Darken modes:**
- ``darken``: Selects darker of source and backdrop
- ``multiply``: Multiplies colors (darkens)
- ``color_burn``: Darkens backdrop to reflect source
- ``linear_burn``: Similar to multiply but more extreme
- ``darker_color``: Selects darker color (non-separable)

**Lighten modes:**
- ``lighten``: Selects lighter of source and backdrop
- ``screen``: Inverted multiply (lightens)
- ``color_dodge``: Brightens backdrop to reflect source
- ``linear_dodge``: Same as addition (Add blend mode)
- ``lighter_color``: Selects lighter color (non-separable)

**Contrast modes:**
- ``overlay``: Combination of multiply and screen
- ``soft_light``: Soft version of overlay
- ``hard_light``: Hard version of overlay
- ``vivid_light``: Combination of color dodge and burn
- ``linear_light``: Combination of linear dodge and burn
- ``pin_light``: Replaces colors based on brightness
- ``hard_mix``: Posterizes to primary colors

**Inversion modes:**
- ``difference``: Absolute difference between colors
- ``exclusion``: Similar to difference but lower contrast

**Component modes (non-separable):**
- ``hue``: Preserves luminosity and saturation, replaces hue
- ``saturation``: Preserves luminosity and hue, replaces saturation
- ``color``: Preserves luminosity, replaces hue and saturation
- ``luminosity``: Preserves hue and saturation, replaces luminosity
- ``darker_color``, ``lighter_color``: Return whichever operand is darker or
  lighter, whole -- listed under Darken and Lighten above, but non-separable
  like the four here, and wrapped by the same guards

Implementation details:

- Separable blend modes process each color channel independently
- The four component modes read three channels together, through the ``_lum``
  and ``_sat`` helpers below; on CMYK they blend the CMY complement and carry K
  across from one operand (#781)
- ``darker_color`` and ``lighter_color`` return one operand or the other whole.
  On CMYK that includes its K, and K also weighs in the comparison that chooses
  -- see ``_lightness`` (#781)
- All functions expect normalized float32 arrays (0.0-1.0 range)
- Division by zero is protected with small epsilon values

Example usage::

    import numpy as np
    from psd_tools.composite.blend import multiply, screen

    # Create backdrop and source colors (normalized)
    backdrop = np.array([0.5, 0.3, 0.8], dtype=np.float32)
    source = np.array([0.7, 0.6, 0.2], dtype=np.float32)

    # Apply blend mode
    result = multiply(backdrop, source)
    # Result: [0.35, 0.18, 0.16]

The ``BLEND_FUNC`` dictionary maps :py:class:`~psd_tools.constants.BlendMode`
enums to their corresponding functions. The compositor looks a mode up through
:py:func:`get_blend_func`, which answers from that table and binds the
document's colour mode where the function needs it.
"""

import functools
import logging
from typing import Callable, Literal

import numpy as np

from psd_tools.constants import BlendMode, ColorMode
from psd_tools.terminology import Enum

logger = logging.getLogger(__name__)

# Float32 constants used throughout blendmodes
_0 = np.float32(0.0)
_1 = np.float32(1.0)
_HALF = np.float32(0.5)
_2 = np.float32(2.0)
_4 = np.float32(4.0)
_6 = np.float32(6.0)

# Small epsilon to prevent division by zero in blend mode calculations.
# Chosen to be negligible relative to normalized [0, 1] color values.
_FLOAT_EPSILON: float = 1e-9


# Separable blend functions
def normal(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    return Cs


def multiply(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    return Cb * Cs


def screen(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    return Cb + Cs - (Cb * Cs)


def overlay(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    return hard_light(Cs, Cb)


def darken(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    return np.minimum(Cb, Cs)


def lighten(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    return np.maximum(Cb, Cs)


def color_dodge(Cb: np.ndarray, Cs: np.ndarray, s: float = 1.0) -> np.ndarray:
    B = np.zeros_like(Cb, dtype=np.float32)
    B[Cs == 1] = 1
    B[Cb == 0] = 0
    index = (Cs != 1) & (Cb != 0)
    B[index] = np.minimum(1, Cb[index] / (s * (1 - Cs[index] + _FLOAT_EPSILON)))
    return B


def color_burn(Cb: np.ndarray, Cs: np.ndarray, s: float = 1.0) -> np.ndarray:
    B = np.zeros_like(Cb, dtype=np.float32)
    B[Cb == 1] = 1
    index = (Cb != 1) & (Cs != 0)
    B[index] = 1 - np.minimum(1, (1 - Cb[index]) / (s * Cs[index] + _FLOAT_EPSILON))
    return B


def linear_dodge(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    return np.minimum(1, Cb + Cs)


def linear_burn(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    return np.maximum(0, Cb + Cs - 1)


def hard_light(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    index = Cs > 0.5
    B = multiply(Cb, 2 * Cs)
    B[index] = screen(Cb, 2 * Cs - 1)[index]
    return B


def soft_light(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    # D is a function of the backdrop alone. Keying its piecewise on Cs instead
    # left every Cb <= 0.25 pixel on the sqrt arm, up to 12.6 steps of 1/255
    # away from Photoshop (#189).
    index = Cb <= 0.25
    index_not = ~index
    D = np.zeros_like(Cb, dtype=np.float32)
    D[index] = ((16 * Cb[index] - 12) * Cb[index] + 4) * Cb[index]
    D[index_not] = np.sqrt(Cb[index_not])

    index = Cs <= 0.5
    index_not = ~index
    B = np.zeros_like(Cb, dtype=np.float32)
    B[index] = Cb[index] - (1 - 2 * Cs[index]) * Cb[index] * (1 - Cb[index])
    B[index_not] = Cb[index_not] + (2 * Cs[index_not] - 1) * (
        D[index_not] - Cb[index_not]
    )
    return B


def vivid_light(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    """
    Burns or dodges the colors by increasing or decreasing the contrast,
    depending on the blend color. If the blend color (light source) is lighter
    than 50% gray, the image is lightened by decreasing the contrast. If the
    blend color is darker than 50% gray, the image is darkened by increasing
    the contrast.
    """

    # Deliberately not color_burn/color_dodge: those carry the spec's backdrop
    # special cases -- Cb == 1 burns to 1, Cb == 0 dodges to 0 -- and Photoshop
    # does not apply them here. Inside Vivid Light the *source* extreme wins,
    # so Cs == 0 burns to 0 and Cs == 1 dodges to 1 whatever the backdrop. Plain
    # Color Burn and Color Dodge do keep the backdrop cases, so the two really
    # do differ; both readings are pinned against Photoshop's own render (#189).
    burn = Cs <= 0.5
    dodge = ~burn
    B = np.zeros_like(Cb, dtype=np.float32)
    B[burn] = 1 - np.minimum(1, (1 - Cb[burn]) / (2 * Cs[burn] + _FLOAT_EPSILON))
    B[dodge] = np.minimum(1, Cb[dodge] / (2 * (1 - Cs[dodge]) + _FLOAT_EPSILON))
    B[Cs == 0] = 0
    B[Cs == 1] = 1
    return B


def linear_light(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    """
    Burns or dodges the colors by decreasing or increasing the brightness,
    depending on the blend color. If the blend color (light source) is lighter
    than 50% gray, the image is lightened by increasing the brightness. If the
    blend color is darker than 50% gray, the image is darkened by decreasing
    the brightness.
    """
    index = Cs > 0.5
    B = linear_burn(Cb, 2 * Cs)
    B[index] = linear_dodge(Cb, 2 * Cs - 1)[index]
    return B


def pin_light(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    """
    Replaces the colors, depending on the blend color. If the blend color
    (light source) is lighter than 50% gray, pixels darker than the blend color
    are replaced, and pixels lighter than the blend color do not change. If the
    blend color is darker than 50% gray, pixels lighter than the blend color
    are replaced, and pixels darker than the blend color do not change. This is
    useful for adding special effects to an image.
    """
    index = Cs > 0.5
    B = darken(Cb, 2 * Cs)
    B[index] = lighten(Cb, 2 * Cs - 1)[index]
    return B


def difference(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    return np.abs(Cb - Cs)


def exclusion(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    return Cb + Cs - 2 * Cb * Cs


def subtract(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    return np.maximum(0, Cb - Cs)


def hard_mix(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    """
    Adds the red, green and blue channel values of the blend color to the RGB
    values of the base color. If the resulting sum for a channel is above 255 it
    receives a value of 255, and below 255 a value of 0; on exactly 255 the
    backdrop decides, as the comment below sets out.
    Therefore, all blended pixels have red, green, and blue channel values of
    either 0 or 255. This changes all pixels to primary additive colors (red,
    green, or blue), white, or black.
    """
    # Photoshop breaks the exact tie toward the backdrop: where Cb + Cs == 1 the
    # result is 1 only where Cb > 0.5. That tie is a real case and not float
    # noise -- two complementary 8-bit values sum to exactly 1.0 in float32 for
    # all 256 of them -- so it is testable rather than something to fudge past.
    # The 0.999999 factor this replaces decided every tie the other way and got
    # 9 of 145 measured boundary samples wrong (#189).
    total = Cb + Cs
    B = np.zeros_like(Cb, dtype=np.float32)
    B[(total > 1) | ((total == 1) & (Cb > 0.5))] = 1
    return B


def divide(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    """
    Looks at the color information in each channel and divides the blend color
    from the base color.
    """
    B = Cb / (Cs + _FLOAT_EPSILON)
    B[B > 1] = 1
    return B


# The wrappers :py:func:`non_separable` builds, which are the only blend
# functions that take a colour mode. Populated by the decorator rather than
# listed here, so that a seventh mode added *through the decorator* needs no
# edit here; one written by hand would still have to register itself, as it
# would have to reimplement the fallbacks. Binding the mode over the whole of
# ``BLEND_FUNC`` instead is not an option: ``color_dodge`` and ``color_burn``
# already have a third parameter of their own.
_MODE_AWARE: set[Callable] = set()


# The one place the two fallbacks are applied, so that both decorators below
# get them and cannot drift apart. What they are and why is documented on
# :py:func:`non_separable`.
def _guarded(func, apply):
    """Wrap *apply* in the two fallbacks every non-separable mode shares.

    ``func`` is only ever the undecorated function, for its name in the log and
    for :py:func:`functools.wraps`; ``apply`` is what actually blends. Both
    operands must be the same width for either decorator's arithmetic to mean
    anything, so a mismatch takes the fallback rather than reaching it: K would
    otherwise be an empty slice off a three-channel backdrop, and the mode would
    quietly return one channel fewer than it was given.
    """

    @functools.wraps(func)
    def _blend_fn(
        Cb: np.ndarray, Cs: np.ndarray, color_mode: ColorMode | None = None
    ) -> np.ndarray:
        if color_mode == ColorMode.MULTICHANNEL:
            # Ahead of the width test, and with a message of its own: for three
            # or four plates the width is the wrong diagnosis, and those are
            # exactly the two counts that used to blend rather than fall back.
            logger.debug(
                "%s blend is not defined on a multichannel document; "
                "falling back to normal",
                func.__name__,
            )
            return normal(Cb, Cs)
        if Cs.shape[2] not in (3, 4) or Cb.shape[2] != Cs.shape[2]:
            # The canvas width, and inside the compositor the document's:
            # ``Compositor._fit_source()`` widens a one-channel source at the
            # door, so every array reaching here from there is exactly that wide
            # (#749). A direct caller can hand over any width, which is why this
            # is a fallback and not an assertion.
            logger.debug(
                "%s blend is not defined for a %d-channel source against a "
                "%d-channel backdrop; falling back to normal",
                func.__name__,
                Cs.shape[2],
                Cb.shape[2],
            )
            return normal(Cb, Cs)
        return apply(Cb, Cs)

    _MODE_AWARE.add(_blend_fn)
    return _blend_fn


# Non-separable blending happens on the CMY complement, which is what the
# canvas already holds (#747: "the transform yields ink; the canvas counts what
# is left"). There is no conversion to RGB and back: Photoshop blends those
# three channels directly and carries K across from one operand -- K of Cb for
# hue, saturation and color, K of Cs for luminosity. Scripted against Photoshop
# 2026 over six CMYK colour pairs, that reproduces all four modes to within
# 1.2/255; converting through RGB first, by any formula tried, does not (#781).
def non_separable(k: Literal["b", "s"]):
    """Wrap a component blend -- Hue, Saturation, Color or Luminosity.

    The wrapped functions are three-channel by construction: the helpers below
    index channels 0, 1 and 2 by name. RGB reaches them unchanged. CMYK hands
    them its first three channels -- the CMY complement -- and gets K back from
    whichever operand *k* names, ``"b"`` for the backdrop or ``"s"`` for the
    source. There is no default: taking K from the wrong operand is invisible in
    every RGB document and wrong in every CMYK one, which is how it went
    unnoticed until #781.

    Any other width falls back to :py:func:`normal` rather than raising or
    inventing a result, and so does a multichannel document at any plate count:

    - **Multichannel** falls back, and is checked first for that reason. Its
      channels are spot inks, so a hue or a luminosity read off them is
      meaningless whether there are three of them or thirty; keying on the width
      alone had four plates claimed as CMYK and three blended as if they were R,
      G and B (#746).
    - **One channel** falls back on the width: grayscale, duotone and bitmap are
      each one channel wide, and Photoshop offers none of the six on any of
      them. Two channels, and five or more, likewise.
    - **CMYK** blends its CMY complement. **RGB** blends directly, and so does
      indexed, whose canvas
      :py:data:`~psd_tools.api.utils.EXPECTED_CHANNELS` fixes at three.

    Photoshop offers none of the six on any of the modes that fall back.
    Scripted against Photoshop 2026, a grayscale document rejects every one with
    *The command "Set" is not currently available* and they are greyed out in
    the UI; bitmap mode does not admit layers at all; and a multichannel
    document does not either -- converting to Multichannel flattens, so the
    blend mode cannot be set on one in the first place. So there is no result to
    reproduce, and widening or reinterpreting the array would produce output
    Photoshop never does (#735, #746).

    With no mode to ask -- a bare :py:class:`~psd_tools.composite.Compositor`,
    or one of these functions called directly -- the width decides alone, as it
    did before #746, and four channels are taken for CMYK. That is a guess, and
    on a four-plate multichannel array it is the wrong one; it is the same guess
    the whole module made before #746, kept because a caller who supplies no
    document is not asking to be told which mode it has.

    Lab is three channels wide and so is blended as if it were RGB. That is this
    module's pre-existing treatment of Lab, not something the fallback decides,
    and it is the right side to leave Lab on: Photoshop does offer all six modes
    on a Lab document.
    """

    def decorator(func):
        def apply(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
            if Cs.shape[2] == 4:
                K = Cb[:, :, 3:4] if k == "b" else Cs[:, :, 3:4]
                return np.concatenate((func(Cb[:, :, :3], Cs[:, :, :3]), K), axis=2)
            return func(Cb, Cs)

        return _guarded(func, apply)

    return decorator


def non_separable_selection(func):
    """Wrap Darker Color or Lighter Color, which choose between whole pixels.

    These two differ from the four component modes in taking the array whole
    rather than by its first three channels: they return one operand or the
    other unchanged, and on CMYK that has to include its K. Photoshop agrees --
    over six colour pairs its Darker Color is one of the two inputs exactly, K
    and all -- and forcing K from a fixed operand instead, as #781 found, gave a
    colour neither input had (#781).

    They also compare a different quantity: :py:func:`_lightness`, which folds K
    in, where the component modes blend the CMY complement with no K term at
    all. Both halves of that asymmetry are Photoshop's, not a simplification.

    The multichannel and width fallbacks are the same ones
    :py:func:`non_separable` documents; both decorators get them from
    :py:func:`_guarded`.
    """
    return _guarded(func, func)


def _lightness(C: np.ndarray) -> np.ndarray:
    """How light a colour is, for the two modes that choose between pixels.

    On CMYK the K plate darkens every ink, so it belongs in the comparison:
    this is ``_lum(CMY) * K``, which is algebraically ``_lum(CMY * K)`` -- the
    luminance of the naive CMYK-to-RGB conversion. The four component modes
    deliberately use no K term at all; both halves of that asymmetry are what
    Photoshop does (#781).
    """
    if C.shape[2] == 4:
        return _lum(C[:, :, :3] * C[:, :, 3:4])
    return _lum(C)


@non_separable("b")
def hue(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    return _set_lum(_set_sat(Cs, _sat(Cb)), _lum(Cb))


@non_separable("b")
def saturation(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    return _set_lum(_set_sat(Cb, _sat(Cs)), _lum(Cb))


@non_separable("b")
def color(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    return _set_lum(Cs, _lum(Cb))


@non_separable("s")
def luminosity(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    return _set_lum(Cb, _lum(Cs))


@non_separable_selection
def darker_color(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    index = np.repeat(_lightness(Cs) < _lightness(Cb), Cb.shape[2], axis=2)
    B = Cb.copy()
    B[index] = Cs[index]
    return B


@non_separable_selection
def lighter_color(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    index = np.repeat(_lightness(Cs) > _lightness(Cb), Cb.shape[2], axis=2)
    B = Cb.copy()
    B[index] = Cs[index]
    return B


def dissolve(Cb: np.ndarray, Cs: np.ndarray) -> np.ndarray:
    # TODO: Implement me!
    logger.debug("Dissolve blend is not implemented")
    return normal(Cb, Cs)


# Helper functions from PDF reference.
def _lum(C: np.ndarray) -> np.ndarray:
    return 0.3 * C[:, :, 0:1] + 0.59 * C[:, :, 1:2] + 0.11 * C[:, :, 2:3]


def _set_lum(C: np.ndarray, L: np.ndarray) -> np.ndarray:
    d = L - _lum(C)
    return _clip_color(C + d)


def _clip_color(C: np.ndarray) -> np.ndarray:
    L = np.repeat(_lum(C), 3, axis=2)
    C_min = np.repeat(np.min(C, axis=2, keepdims=True), 3, axis=2)
    C_max = np.repeat(np.max(C, axis=2, keepdims=True), 3, axis=2)

    index = C_min < 0.0
    L_i = L[index]
    C[index] = L_i + (C[index] - L_i) * L_i / (L_i - C_min[index] + _FLOAT_EPSILON)

    index = C_max > 1.0
    L_i = L[index]
    C[index] = L_i + (C[index] - L_i) * (1 - L_i) / (
        C_max[index] - L_i + _FLOAT_EPSILON
    )

    # For numerical stability.
    C[C < 0.0] = 0
    C[C > 1] = 1
    return C


def _sat(C: np.ndarray) -> np.ndarray:
    return np.max(C, axis=2, keepdims=True) - np.min(C, axis=2, keepdims=True)


def _set_sat(C: np.ndarray, s: np.ndarray) -> np.ndarray:
    s = np.repeat(s, 3, axis=2)

    C_max = np.repeat(np.max(C, axis=2, keepdims=True), 3, axis=2)
    C_mid = np.repeat(np.median(C, axis=2, keepdims=True), 3, axis=2)
    C_min = np.repeat(np.min(C, axis=2, keepdims=True), 3, axis=2)

    B = np.zeros_like(C, dtype=np.float32)

    index_diff = C_max > C_min
    index_mid = C == C_mid
    index_max = (C == C_max) & ~index_mid
    index_min = C == C_min

    index = index_mid & index_diff
    B[index] = (
        (C_mid[index] - C_min[index])
        * s[index]
        / (C_max[index] - C_min[index] + _FLOAT_EPSILON)
    )
    index = index_max & index_diff
    B[index] = s[index]

    B[~index_diff & index_mid] = 0
    B[~index_diff & index_max] = 0

    B[index_min] = 0

    return B


def rgb2hsl(img: np.ndarray) -> np.ndarray:
    """Convert an RGB image to HSL space using vectorized arrays."""
    ch_min = np.min(img, axis=2)
    ch_max = np.max(img, axis=2)

    delta = ch_max - ch_min
    total = ch_max + ch_min
    non_zero = delta > _FLOAT_EPSILON

    out = np.empty_like(img)
    H = out[..., 0]
    S = out[..., 1]
    L = out[..., 2]

    # Lightness
    L[:] = _HALF * total

    # Saturation
    S[:] = _0
    den = _1 - np.abs(_2 * L - _1)
    S[non_zero] = delta[non_zero] / den[non_zero]

    # Hue
    R, G, B = img[..., 0], img[..., 1], img[..., 2]
    idx_R = (ch_max == R) & non_zero
    idx_G = (ch_max == G) & non_zero
    idx_B = (ch_max == B) & non_zero

    H[:] = _0
    H[idx_R] = ((G[idx_R] - B[idx_R]) / delta[idx_R]) % _6
    H[idx_G] = ((B[idx_G] - R[idx_G]) / delta[idx_G]) + _2
    H[idx_B] = ((R[idx_B] - G[idx_B]) / delta[idx_B]) + _4
    H *= _1 / _6

    return out


def hsl2rgb(img: np.ndarray) -> np.ndarray:
    """Convert an HSL image to RGB space using vectorized arrays."""
    H, S, L = img[..., 0], img[..., 1], img[..., 2]

    out = np.zeros_like(img)
    R = out[..., 0]
    G = out[..., 1]
    B = out[..., 2]

    C = (_1 - np.abs(_2 * L - _1)) * S
    H_ = H * _6
    X = C * (_1 - np.abs(H_ % _2 - _1))

    mask0 = H_ < 1
    mask1 = (1 <= H_) & (H_ < 2)
    mask2 = (2 <= H_) & (H_ < 3)
    mask3 = (3 <= H_) & (H_ < 4)
    mask4 = (4 <= H_) & (H_ < 5)
    mask5 = 5 <= H_

    R[mask0], G[mask0], B[mask0] = C[mask0], X[mask0], _0
    R[mask1], G[mask1], B[mask1] = X[mask1], C[mask1], _0
    R[mask2], G[mask2], B[mask2] = _0, C[mask2], X[mask2]
    R[mask3], G[mask3], B[mask3] = _0, X[mask3], C[mask3]
    R[mask4], G[mask4], B[mask4] = X[mask4], _0, C[mask4]
    R[mask5], G[mask5], B[mask5] = C[mask5], _0, X[mask5]

    m = L - C / _2

    R += m
    G += m
    B += m

    return out


def hsl2hsv(img: np.ndarray) -> np.ndarray:
    """Convert an HSL image to HSV space using vectorized arrays."""
    H, SL, L = img[..., 0], img[..., 1], img[..., 2]

    out = np.empty_like(img)

    # Hue
    out[..., 0] = H

    # Value
    V = L + SL * np.minimum(L, _1 - L)
    out[..., 2] = V

    # Saturation
    SV = out[..., 1]
    SV[:] = _0

    mask = V > _FLOAT_EPSILON
    SV[mask] = _2 * (_1 - L[mask] / V[mask])

    return out


def hsv2hsl(img: np.ndarray) -> np.ndarray:
    """Convert an HSV image to HSL space using vectorized arrays."""
    H, SV, V = img[..., 0], img[..., 1], img[..., 2]

    out = np.empty_like(img)

    # Hue
    out[..., 0] = H

    # Lightness
    L = V * (_1 - SV * _HALF)
    out[..., 2] = L

    # Saturation
    SL = out[..., 1]
    SL[:] = _0

    denom = np.minimum(L, _1 - L)
    mask = denom > _FLOAT_EPSILON
    SL[mask] = (V[mask] - L[mask]) / denom[mask]

    return out


"""Blend function table."""
BLEND_FUNC = {
    # Layer attributes
    BlendMode.NORMAL: normal,
    BlendMode.MULTIPLY: multiply,
    BlendMode.SCREEN: screen,
    BlendMode.OVERLAY: overlay,
    BlendMode.DARKEN: darken,
    BlendMode.LIGHTEN: lighten,
    BlendMode.COLOR_DODGE: color_dodge,
    BlendMode.COLOR_BURN: color_burn,
    BlendMode.LINEAR_DODGE: linear_dodge,
    BlendMode.LINEAR_BURN: linear_burn,
    BlendMode.HARD_LIGHT: hard_light,
    BlendMode.SOFT_LIGHT: soft_light,
    BlendMode.VIVID_LIGHT: vivid_light,
    BlendMode.LINEAR_LIGHT: linear_light,
    BlendMode.PIN_LIGHT: pin_light,
    BlendMode.HARD_MIX: hard_mix,
    BlendMode.DIVIDE: divide,
    BlendMode.DIFFERENCE: difference,
    BlendMode.EXCLUSION: exclusion,
    BlendMode.SUBTRACT: subtract,
    BlendMode.HUE: hue,
    BlendMode.SATURATION: saturation,
    BlendMode.COLOR: color,
    BlendMode.LUMINOSITY: luminosity,
    BlendMode.DARKER_COLOR: darker_color,
    BlendMode.LIGHTER_COLOR: lighter_color,
    BlendMode.DISSOLVE: dissolve,
    # Descriptor keys
    Enum.Normal: normal,
    Enum.Multiply: multiply,
    Enum.Screen: screen,
    Enum.Overlay: overlay,
    Enum.Darken: darken,
    Enum.Lighten: lighten,
    Enum.ColorDodge: color_dodge,
    Enum.ColorBurn: color_burn,
    b"linearDodge": linear_dodge,
    b"linearBurn": linear_burn,
    Enum.HardLight: hard_light,
    Enum.SoftLight: soft_light,
    b"vividLight": vivid_light,
    b"linearLight": linear_light,
    b"pinLight": pin_light,
    b"hardMix": hard_mix,
    b"blendDivide": divide,
    Enum.Difference: difference,
    Enum.Exclusion: exclusion,
    Enum.Subtract: subtract,
    Enum.Hue: hue,
    Enum.Saturation: saturation,
    Enum.Color: color,
    Enum.Luminosity: luminosity,
    b"darkerColor": darker_color,
    b"lighterColor": lighter_color,
    Enum.Dissolve: dissolve,
}


def get_blend_func(
    blend_mode: bytes, color_mode: ColorMode | None = None
) -> Callable[[np.ndarray, np.ndarray], np.ndarray]:
    """Look up *blend_mode*, with the document's colour mode already bound in.

    :py:data:`BLEND_FUNC` answers by blend mode alone, which is all a separable
    mode needs. The six non-separable ones also need to know what the channels
    of their operands *are* -- three spot plates are not R, G and B, and a
    fourth is not black generation -- so the mode is bound to those here rather
    than plumbed through every blend signature (#746).

    The result takes ``(Cb, Cs)`` either way, so the compositor calls it without
    caring which kind it got. Pass no *color_mode* and the width decides alone,
    exactly as it did before; :py:data:`BLEND_FUNC` itself is unchanged and
    stays the mode-blind table.

    *blend_mode* is ``bytes`` and not :py:class:`~psd_tools.constants.BlendMode`
    because :py:data:`BLEND_FUNC` is keyed by two families -- enum members for a
    layer's own mode, raw descriptor keys such as ``b"lighterColor"`` for a
    stroke's or an effect's -- and ``BlendMode`` subclasses ``bytes``, so the
    supertype admits both without a union of a type and its own supertype.

    Unknown keys answer :py:func:`normal`, as the ``.get`` calls this replaces
    did. ``PASS_THROUGH`` is one of them and reaches here for real: a group that
    isolates its adjustments is composited as an ordinary source.
    """
    func = BLEND_FUNC.get(blend_mode, normal)
    if color_mode is None or func not in _MODE_AWARE:
        return func
    return functools.partial(func, color_mode=color_mode)
