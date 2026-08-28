"""Pure scalar color space conversion utilities.

Units: RGB, CMYK, HSB and grayscale values are normalized floats in
``[0.0, 1.0]``. **CIE L*a*b* is the exception and is in native units** --
``L`` in ``0..100`` and ``a``/``b`` signed, nominally ``-128..127``. That is
what the PSD descriptors carry and what published reference tables are printed
in; normalizing it would mean choosing an encoding, and the only sensible
choice (``L/100``, ``(a + 128)/255``) is a *canvas* encoding rather than a
colorimetric one. It belongs with the compositor, in
``psd_tools.composite.paint``.

Comparing against Photoshop's scripting bridge needs care: ``SolidColor.lab``
does *not* report native units. It reports ``a`` and ``b`` through the signed
8-bit encoding Photoshop stores them in, ``a * (255 / 256) - 0.5``, which is
why a neutral colour comes back from it as ``a = b = -0.5`` rather than 0.
``L`` is native. See ``tests/psd_tools/test_color_convert.py``, which undoes
the encoding before comparing.

There are intentionally no numpy or internal ``psd_tools`` imports so this
module can be imported freely from both ``psd_tools.api`` and
``psd_tools.composite`` without introducing circular dependencies.

References:
    - ITU-R BT.601 for the luminance coefficients used in
      :func:`rgb_to_grayscale`.
    - Adobe Photoshop Color Model documentation for the CMYK ↔ RGB formulas.
    - CIE 15:2004 for the L*a*b* transfer function, and Lindbloom's
      Bradford-adapted sRGB/D50 matrices for :func:`lab_to_rgb` and
      :func:`rgb_to_lab`.
"""

import math

#: The normalized value of a neutral ``a``/``b`` axis in a Lab color *array*.
#:
#: An encoding constant rather than a conversion result -- the one value in this
#: module that is not in the native units the docstring above describes. It is
#: here because :func:`rgb_to_lab` returns exactly ``a = b = 0.0`` for a neutral,
#: and this is what that becomes once the compositor encodes it.
#:
#: Lab's two chroma axes are signed and are stored offset by 128 -- byte 128 is
#: ``a = 0``, byte 0 is ``a = -128`` -- so a normalized neutral is ``128 / 255``
#: rather than the ``0.5`` this used to be spelled as. The half-step between
#: them is not cosmetic: :py:func:`psd_tools.composite.composite_pil` truncates
#: rather than rounds on the way out, so ``0.5`` emits byte 127 where Photoshop
#: writes 128 (#743).
LAB_NEUTRAL_CHROMA = 128.0 / 255.0


def rgb_to_grayscale(r: float, g: float, b: float) -> float:
    """Convert normalized RGB to grayscale luminance (ITU-R BT.601).

    Args:
        r: Red channel in [0.0, 1.0].
        g: Green channel in [0.0, 1.0].
        b: Blue channel in [0.0, 1.0].

    Returns:
        Luminance value in [0.0, 1.0] using the BT.601 coefficients
        ``0.299·R + 0.587·G + 0.114·B``.

    Examples:
        >>> rgb_to_grayscale(1.0, 0.0, 0.0)
        0.299
        >>> rgb_to_grayscale(0.0, 0.0, 0.0)
        0.0
    """
    return 0.299 * r + 0.587 * g + 0.114 * b


def rgb_to_cmyk(r: float, g: float, b: float) -> tuple[float, float, float, float]:
    """Convert normalized RGB to CMYK.

    Pure black ``(0, 0, 0)`` maps to ``(0, 0, 0, 1)`` to avoid a division by
    zero in the key-channel normalization step.

    Args:
        r: Red channel in [0.0, 1.0].
        g: Green channel in [0.0, 1.0].
        b: Blue channel in [0.0, 1.0].

    Returns:
        4-tuple ``(C, M, Y, K)`` with each component in [0.0, 1.0].

    Examples:
        >>> rgb_to_cmyk(0.0, 0.0, 0.0)
        (0.0, 0.0, 0.0, 1.0)
        >>> rgb_to_cmyk(1.0, 1.0, 1.0)
        (0.0, 0.0, 0.0, 0.0)
    """
    if r == 0.0 and g == 0.0 and b == 0.0:
        return (0.0, 0.0, 0.0, 1.0)
    c, m, y = 1.0 - r, 1.0 - g, 1.0 - b
    k = min(c, m, y)
    d = 1.0 - k
    return ((c - k) / d, (m - k) / d, (y - k) / d, k)


def cmyk_to_rgb(c: float, m: float, y: float, k: float) -> tuple[float, float, float]:
    """Convert normalized CMYK to RGB.

    Args:
        c: Cyan channel in [0.0, 1.0].
        m: Magenta channel in [0.0, 1.0].
        y: Yellow channel in [0.0, 1.0].
        k: Black (key) channel in [0.0, 1.0].

    Returns:
        3-tuple ``(R, G, B)`` with each component in [0.0, 1.0].

    Examples:
        >>> cmyk_to_rgb(0.0, 0.0, 0.0, 0.0)
        (1.0, 1.0, 1.0)
        >>> cmyk_to_rgb(0.0, 0.0, 0.0, 1.0)
        (0.0, 0.0, 0.0)
    """
    return (
        (1.0 - c) * (1.0 - k),
        (1.0 - m) * (1.0 - k),
        (1.0 - y) * (1.0 - k),
    )


def hsb_to_rgb(h: float, s: float, v: float) -> tuple[float, float, float]:
    """Convert HSB (hue/saturation/brightness) to normalized RGB.

    Uses the standard six-sector algorithm.  When saturation is zero the
    color is achromatic and ``(v, v, v)`` is returned.

    Hue is an angle, so it is cyclic: any value outside ``[0.0, 1.0)`` wraps
    into it, and ``1.0``, ``2.0`` and ``-1.0`` all mean the same hue as
    ``0.0``. This used to be a bare ``h == 1.0`` special case with a silent
    achromatic fallback for everything else out of range, which turned a fully
    saturated hue into grey rather than into the color one turn away (#754).

    Saturation and brightness are not angles, so they clamp rather than wrap.

    Total: any float, including infinities and NaN, returns a triple inside
    ``[0, 1]`` rather than raising or propagating. Descriptor values are
    unvalidated file data, and the ``Returns:`` line below used to hold only for
    in-range ``s``/``v`` -- ``s = 1.2, v = 1.5`` gave ``(1.5, -0.3, -0.3)``,
    which the uint8 cast in ``composite_pil()`` *wraps* into an unrelated color
    (#757). Same policy as :py:func:`lab_to_rgb`.

    Args:
        h: Hue as a fraction of a full turn, cyclic. Any value is folded
            back onto the circle, where 1.0 is the same hue as 0.0.
        s: Saturation in [0.0, 1.0]. Outside that it saturates.
        v: Brightness (value) in [0.0, 1.0]. Outside that it saturates.

    Returns:
        3-tuple ``(R, G, B)`` with each component in [0.0, 1.0].

    Examples:
        >>> hsb_to_rgb(0.0, 0.0, 0.5)   # achromatic 50% grey
        (0.5, 0.5, 0.5)
        >>> hsb_to_rgb(0.0, 1.2, 1.5)   # out of range, saturated not wrapped
        (1.0, 0.0, 0.0)
    """
    # Before the ``not s`` test, so that a NaN saturation reaches it as 0.0 and
    # takes the achromatic answer rather than propagating through the sector
    # arithmetic below.
    s = _clamp(s, 0.0, 1.0)
    v = _clamp(v, 0.0, 1.0)
    if not s:
        return (v, v, v)
    if not math.isfinite(h):
        # NaN and the infinities name no angle, so there is no turn to wrap
        # them onto and the achromatic answer is the only degradation left.
        # Worth spelling out because ``int(float("nan") * 6.0)`` raises, and a
        # descriptor carries unvalidated file data. Same policy as
        # ``lab_to_rgb``, which reaches it by clamping rather than by a test.
        return (v, v, v)
    h = h % 1.0
    sector = int(h * 6.0) % 6
    f = h * 6.0 - int(h * 6.0)
    w = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    sectors: tuple[tuple[float, float, float], ...] = (
        (v, t, w),
        (q, v, w),
        (w, v, t),
        (w, q, v),
        (t, w, v),
        (v, w, q),
    )
    return sectors[sector]


def gray_to_rgb(gray: float) -> tuple[float, float, float]:
    """Expand a grayscale value to an achromatic RGB triple.

    Args:
        gray: Luminance in [0.0, 1.0].

    Returns:
        3-tuple ``(gray, gray, gray)``.

    Examples:
        >>> gray_to_rgb(0.5)
        (0.5, 0.5, 0.5)
    """
    return (gray, gray, gray)


def gray_to_cmyk(gray: float) -> tuple[float, float, float, float]:
    """Convert a grayscale value to CMYK using only the K (black) channel.

    White (1.0) maps to no ink ``(0, 0, 0, 0)``.
    Black (0.0) maps to full key ``(0, 0, 0, 1)``.

    Args:
        gray: Luminance in [0.0, 1.0] where 1.0 is white.

    Returns:
        4-tuple ``(0.0, 0.0, 0.0, 1.0 - gray)``.

    Examples:
        >>> gray_to_cmyk(1.0)
        (0.0, 0.0, 0.0, 0.0)
        >>> gray_to_cmyk(0.0)
        (0.0, 0.0, 0.0, 1.0)
    """
    return (0.0, 0.0, 0.0, 1.0 - gray)


# CIE 15:2004's transfer-function constants, in the exact-rational form that
# makes kappa * eps == 8.0 and the two branches meet without a step.
_LAB_EPS = 216.0 / 24389.0
_LAB_KAPPA = 24389.0 / 27.0

#: D50 white point, as the tristimulus the matrices below actually sum to.
#:
#: Deliberately Lindbloom's ``(0.96422, 1.0, 0.82521)`` and not the ICC PCS
#: triple ``(0.9642, 1.0, 0.8249)``. Pairing the ICC triple with these matrices
#: leaves the transform without an exact fixed point: white comes back as
#: ``(1.0, 1.0, 0.99981)`` and a neutral grey as ``b = -0.025``, which the
#: compositor's truncating cast turns into byte 127 where Photoshop -- and
#: :py:data:`LAB_NEUTRAL_CHROMA` -- write 128.
_LAB_D50 = (0.96422, 1.0, 0.82521)

# Bradford-adapted, so they carry the D50 adaptation rather than needing a
# separate chromatic-adaptation step.
_XYZ_D50_TO_SRGB = (
    (3.1338561, -1.6168667, -0.4906146),
    (-0.9787684, 1.9161415, 0.0334540),
    (0.0719453, -0.2289914, 1.4052427),
)
_SRGB_TO_XYZ_D50 = (
    (0.4360747, 0.3850649, 0.1430804),
    (0.2225045, 0.7168786, 0.0606169),
    (0.0139322, 0.0971045, 0.7141733),
)


def _srgb_gamma(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055


def _srgb_ungamma(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _clamp(value: float, low: float, high: float) -> float:
    """Clamp, mapping NaN to *low*.

    ``max(low, nan)`` returns ``low`` because ``nan > low`` is false, and
    ``min`` then leaves it alone. That is the behaviour wanted here -- a NaN
    from a malformed descriptor degrades to the end of the axis rather than
    poisoning the canvas -- but it is a property of the argument order, so do
    not reverse it.
    """
    return min(high, max(low, value))


def lab_to_rgb(lightness: float, a: float, b: float) -> tuple[float, float, float]:
    """Convert CIE L*a*b* to normalized sRGB.

    The white point is D50, which is what Photoshop's Lab is; a D65 conversion
    is wrong here by a mean of 11.6/255 and a maximum of 92.7/255 against
    Photoshop's own numbers, against 0.35/255 and 4.5/255 for this one.

    Out-of-gamut colors are clipped per channel. Every caller writes to a canvas
    that cannot represent them, so the alternative is not a better color but an
    array the compositor cannot use. The result is therefore always inside
    ``[0, 1]`` and never reports that clipping happened.

    Total: any float, including infinities and NaN, returns a usable triple
    rather than raising. Descriptor values are unvalidated file data.

    Args:
        lightness: ``L*``, 0..100. Outside that the result saturates.
        a: green-red chroma, nominally -128..127. Outside that it saturates.
        b: blue-yellow chroma, nominally -128..127. Outside that it saturates.

    Returns:
        3-tuple ``(R, G, B)`` with each component in [0.0, 1.0].

    Examples:
        >>> tuple(round(v, 4) for v in lab_to_rgb(100.0, 0.0, 0.0))
        (1.0, 1.0, 1.0)
        >>> tuple(round(v, 4) for v in lab_to_rgb(0.0, 0.0, 0.0))
        (0.0, 0.0, 0.0)
        >>> tuple(round(v, 4) for v in lab_to_rgb(54.291, 80.812, 69.885))
        (1.0, 0.0, 0.0)
    """
    fy = (lightness + 16.0) / 116.0
    fxyz = (fy + a / 500.0, fy, fy - b / 200.0)
    xyz = []
    for f, white in zip(fxyz, _LAB_D50):
        # ``f * f * f`` rather than ``f ** 3`` on purpose. A descriptor carries
        # unvalidated file data, and on a large float the power operator raises
        # OverflowError where the multiplication saturates to inf -- which the
        # clamps below then degrade to the end of the axis. Keep the
        # multiplication, or a malformed fill becomes an exception.
        cube = f * f * f
        xyz.append(
            (cube if cube > _LAB_EPS else (116.0 * f - 16.0) / _LAB_KAPPA) * white
        )

    rgb = []
    for row in _XYZ_D50_TO_SRGB:
        linear = row[0] * xyz[0] + row[1] * xyz[1] + row[2] * xyz[2]
        # One clamp, after the transfer function rather than either side of
        # it. A negative linear value takes _srgb_gamma's linear branch, so it
        # never reaches the fractional power that would make it complex, and
        # infinities and NaN pass straight through to be clamped here.
        rgb.append(_clamp(_srgb_gamma(linear), 0.0, 1.0))
    return (rgb[0], rgb[1], rgb[2])


def rgb_to_lab(r: float, g: float, b: float) -> tuple[float, float, float]:
    """Convert normalized sRGB to CIE L*a*b*.

    The exact inverse of :func:`lab_to_rgb` for any in-gamut color: round
    tripping every sRGB value on a 6x6x6 grid returns it to within
    0.0003/255. A neutral grey returns ``a = b = 0.0`` exactly, which is what
    :py:data:`LAB_NEUTRAL_CHROMA` encodes.

    Args:
        r: Red channel in [0.0, 1.0]. Values outside are clamped.
        g: Green channel in [0.0, 1.0]. Values outside are clamped.
        b: Blue channel in [0.0, 1.0]. Values outside are clamped.

    Returns:
        3-tuple ``(L*, a, b)`` in native units -- ``L*`` in 0..100, ``a`` and
        ``b`` signed.

    Examples:
        >>> tuple(round(v, 4) for v in rgb_to_lab(1.0, 1.0, 1.0))
        (100.0, 0.0, 0.0)
        >>> tuple(round(v, 4) for v in rgb_to_lab(0.5, 0.5, 0.5))
        (53.389, 0.0, 0.0)
    """
    linear = [_srgb_ungamma(_clamp(v, 0.0, 1.0)) for v in (r, g, b)]
    f = []
    for row, white in zip(_SRGB_TO_XYZ_D50, _LAB_D50):
        ratio = (row[0] * linear[0] + row[1] * linear[1] + row[2] * linear[2]) / white
        f.append(
            ratio ** (1.0 / 3.0)
            if ratio > _LAB_EPS
            else (_LAB_KAPPA * ratio + 16.0) / 116.0
        )
    return (116.0 * f[1] - 16.0, 500.0 * (f[0] - f[1]), 200.0 * (f[1] - f[2]))
