"""Pytest configuration for psd-tools tests."""

from typing import Any

import pytest


def pytest_configure(config: Any) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "composite: mark test as requiring composite dependencies (aggdraw, scipy, scikit-image)",
    )


# Check if composite dependencies are available
try:
    import aggdraw  # noqa: F401 # type: ignore
    import scipy  # noqa: F401 # type: ignore
    import skimage  # noqa: F401

    HAS_COMPOSITE = True
except ImportError:
    HAS_COMPOSITE = False


# Marker to skip tests that require composite dependencies
skip_without_composite = pytest.mark.skipif(
    not HAS_COMPOSITE,
    reason="Requires composite dependencies: pip install 'psd-tools[composite]'",
)
