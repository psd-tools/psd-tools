"""Pytest configuration for psd-tools tests."""

import argparse
from typing import Any

import pytest


def pytest_configure(config: Any) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "composite: mark test as requiring composite dependencies (aggdraw, scipy)",
    )


# Check if composite dependencies are available
try:
    import aggdraw  # type: ignore[import-not-found]  # noqa: F401
    import scipy  # type: ignore[import-untyped]  # noqa: F401

    HAS_COMPOSITE = True
except ImportError:
    HAS_COMPOSITE = False


# Marker to skip tests that require composite dependencies
skip_without_composite = pytest.mark.skipif(
    not HAS_COMPOSITE,
    reason="Requires composite dependencies: pip install 'psd-tools[composite]'",
)


def _non_negative_int(value: str) -> int:
    count = int(value)
    if count < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {count}")
    return count


def pytest_addoption(parser: Any) -> None:
    parser.addoption(
        "--mutants",
        type=_non_negative_int,
        default=0,
        help="byte-mutated variants per fixture for tests/psd_tools/test_malformed.py",
    )
