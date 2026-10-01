"""Resource limits shared by nested low-level PSD parsers."""

import operator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


class ParseLimitError(ValueError):
    """A structural parsing resource limit was exceeded."""


@dataclass(frozen=True)
class ParseLimits:
    """Limit single reads, cumulative materialized bytes, and parsed objects."""

    max_read_bytes: int | None = 256 * 1024**2
    max_total_bytes: int | None = 1024**3
    max_objects: int | None = 1_000_000

    def __post_init__(self) -> None:
        for name in ("max_read_bytes", "max_total_bytes", "max_objects"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool):
                raise TypeError("%s must be a positive integer or None" % name)
            try:
                normalized = operator.index(value)
            except TypeError:
                raise TypeError(
                    "%s must be a positive integer or None" % name
                ) from None
            if normalized <= 0:
                raise ValueError("%s must be positive" % name)
            object.__setattr__(self, name, normalized)


class _ParseBudget:
    def __init__(self, limits: ParseLimits):
        self.limits = limits
        self.total_bytes = 0
        self.objects = 0
        self.error: ParseLimitError | None = None

    def check(self, value: int, maximum: int | None, name: str) -> None:
        if self.error is not None:
            raise self.error
        if maximum is not None and value > maximum:
            self.error = ParseLimitError(
                "%s exceeded: %d > %d" % (name, value, maximum)
            )
            raise self.error


_budget: ContextVar[_ParseBudget | None] = ContextVar("psd_parse_budget", default=None)


@contextmanager
def parse_context(limits: ParseLimits | None = None) -> Iterator[bool]:
    """Start a parse budget or reuse the current synchronous parse budget."""
    if limits is not None and not isinstance(limits, ParseLimits):
        raise TypeError("parse_limits must be ParseLimits or None")
    if _budget.get() is not None:
        yield False
        return
    budget = _ParseBudget(limits if limits is not None else ParseLimits())
    token = _budget.set(budget)
    try:
        yield True
        if budget.error is not None:
            raise budget.error
    finally:
        _budget.reset(token)


def consume_bytes(size: int) -> None:
    """Reserve materialized bytes before reading or copying input."""
    budget = _budget.get()
    if budget is not None:
        budget.check(size, budget.limits.max_read_bytes, "max_read_bytes")
        budget.check(
            budget.total_bytes + size, budget.limits.max_total_bytes, "max_total_bytes"
        )
        budget.total_bytes += size


def consume_objects(count: int) -> None:
    """Reserve parsed elements, scalar values, or array entries."""
    budget = _budget.get()
    if budget is not None:
        budget.check(budget.objects + count, budget.limits.max_objects, "max_objects")
        budget.objects += count
