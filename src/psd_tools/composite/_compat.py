"""Compatibility module for optional composite dependencies."""

import functools
from typing import Callable, TYPE_CHECKING, TypeVar

F = TypeVar("F", bound=Callable)

if TYPE_CHECKING:
    # Type checkers see these as always available
    import aggdraw  # type: ignore[import-not-found]
    from scipy import interpolate  # type: ignore[import-untyped]
    from skimage import filters  # type: ignore[import-untyped]

# Check for optional dependencies
try:
    import aggdraw  # noqa: F401  # type: ignore[import-not-found,no-redef]

    HAS_AGGDRAW = True
except ImportError:
    HAS_AGGDRAW = False

try:
    from scipy import interpolate  # noqa: F401  # type: ignore[import-untyped,no-redef]

    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    from skimage import filters  # noqa: F401  # type: ignore[import-untyped,no-redef]

    HAS_SKIMAGE = True
except ImportError:
    HAS_SKIMAGE = False


def require_aggdraw(func: F) -> F:
    """
    Decorator to check if aggdraw is available before calling the function.

    Required for vector shape rendering (bezier curves, paths, strokes).

    Raises:
        ImportError: If aggdraw is not installed.

    Example:
        >>> @require_aggdraw
        ... def draw_vector_mask(layer):
        ...     return _draw_path(layer, brush={"color": 255})
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not HAS_AGGDRAW:
            raise ImportError(
                "Vector shape rendering requires: aggdraw\n\n"
                "Install with:\n"
                "    pip install 'psd-tools[composite]'\n"
                "Or:\n"
                "    pip install aggdraw"
            )
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def require_scipy(func: F) -> F:
    """
    Decorator to check if scipy is available before calling the function.

    Required for gradient fills (color interpolation).

    Raises:
        ImportError: If scipy is not installed.

    Example:
        >>> @require_scipy
        ... def draw_gradient_fill(viewport, color_mode, desc):
        ...     # gradient implementation
        ...     pass
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not HAS_SCIPY:
            raise ImportError(
                "Gradient fills require: scipy\n\n"
                "Install with:\n"
                "    pip install 'psd-tools[composite]'\n"
                "Or:\n"
                "    pip install scipy"
            )
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def require_skimage(func: F) -> F:
    """
    Decorator to check if scikit-image is available before calling the function.

    Required for layer effects (stroke effects, filters).

    Raises:
        ImportError: If scikit-image is not installed.

    Example:
        >>> @require_skimage
        ... def draw_stroke_effect(viewport, shape, desc, psd):
        ...     # effect implementation
        ...     pass
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not HAS_SKIMAGE:
            raise ImportError(
                "Layer effects require: scikit-image\n\n"
                "Install with:\n"
                "    pip install 'psd-tools[composite]'\n"
                "Or:\n"
                "    pip install scikit-image"
            )
        return func(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
