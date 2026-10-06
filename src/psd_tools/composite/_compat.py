"""Compatibility module for optional composite dependencies."""

import functools
from typing import Any, Callable, TYPE_CHECKING, TypeVar

F = TypeVar("F", bound=Callable)

if TYPE_CHECKING:
    # Type checkers see these as always available
    import aggdraw  # type: ignore[import-not-found]
    from scipy import interpolate  # type: ignore[import-untyped]

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


def require_aggdraw(func: F) -> F:
    """
    Decorator to check if aggdraw is available before calling the function.

    Required for drawing a vector stroke. Filling a path does not need it:
    the coverage is computed exactly by
    :py:mod:`psd_tools.composite.scanline` (#844).

    Raises:
        ImportError: If aggdraw is not installed.

    Example:
        >>> @require_aggdraw
        ... def draw_stroke(layer):
        ...     return _draw_path(layer, pen={"color": 255, "width": 1.0})
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
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
    def wrapper(*args: Any, **kwargs: Any) -> Any:
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
