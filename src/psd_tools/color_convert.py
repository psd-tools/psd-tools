"""Pure scalar color space conversion utilities.

All functions operate on normalized float values in ``[0.0, 1.0]``.
There are intentionally no numpy or internal ``psd_tools`` imports so this
module can be imported freely from both ``psd_tools.api`` and
``psd_tools.composite`` without introducing circular dependencies.

References:
    - ITU-R BT.601 for the luminance coefficients used in
      :func:`rgb_to_grayscale`.
    - Adobe Photoshop Color Model documentation for the CMYK ↔ RGB formulas.
"""


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
        >>> rgb_to_grayscale(1.0, 1.0, 1.0)
        1.0
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

    Args:
        h: Hue in [0.0, 1.0); a value of exactly 1.0 wraps to 0.0.
        s: Saturation in [0.0, 1.0].
        v: Brightness (value) in [0.0, 1.0].

    Returns:
        3-tuple ``(R, G, B)`` with each component in [0.0, 1.0].

    Examples:
        >>> hsb_to_rgb(0.0, 0.0, 0.5)   # achromatic 50% grey
        (0.5, 0.5, 0.5)
    """
    if not s:
        return (v, v, v)
    if h == 1.0:
        h = 0.0
    i = int(h * 6.0)
    f = h * 6.0 - i
    w = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    sectors: dict[int, tuple[float, float, float]] = {
        0: (v, t, w),
        1: (q, v, w),
        2: (w, v, t),
        3: (w, q, v),
        4: (t, w, v),
        5: (v, w, q),
    }
    return sectors.get(i, (v, v, v))


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
