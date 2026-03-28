from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .schema import CanonicalTraceRecord

TraceBuilder = Callable[..., CanonicalTraceRecord]
TraceDetector = Callable[[dict[str, Any]], bool]
TraceValidator = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class TraceFamilyRegistration:
    loop_family: str
    builder: TraceBuilder
    detector: TraceDetector
    validator: TraceValidator | None = None


class TraceFamilyLookupError(KeyError):
    """Raised when a requested canonical trace family is not registered."""


_TRACE_FAMILY_REGISTRY: dict[str, TraceFamilyRegistration] = {}


def register_trace_family(
    *,
    loop_family: str,
    builder: TraceBuilder,
    detector: TraceDetector,
    validator: TraceValidator | None = None,
) -> None:
    family = loop_family.strip()
    if not family:
        raise ValueError("trace_family_name_required")
    _TRACE_FAMILY_REGISTRY[family] = TraceFamilyRegistration(
        loop_family=family,
        builder=builder,
        detector=detector,
        validator=validator,
    )


def get_trace_family(loop_family: str) -> TraceFamilyRegistration | None:
    return _TRACE_FAMILY_REGISTRY.get(loop_family.strip())


def require_trace_family(loop_family: str) -> TraceFamilyRegistration:
    registration = get_trace_family(loop_family)
    if registration is None:
        raise TraceFamilyLookupError(f"trace_family_not_registered:{loop_family}")
    return registration


def iter_trace_families() -> tuple[TraceFamilyRegistration, ...]:
    return tuple(_TRACE_FAMILY_REGISTRY.values())
