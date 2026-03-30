from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .run_summary.models import SharedRunSummaryEnvelope

RunSummaryBuilder = Callable[[dict[str, Any]], "SharedRunSummaryEnvelope"]

_RUN_SUMMARY_BUILDERS: dict[str, RunSummaryBuilder] = {}


class RunSummaryBuilderLookupError(KeyError):
    """Raised when no builder is registered for a loop_family."""


def register_run_summary_builder(*, loop_family: str, builder: RunSummaryBuilder) -> None:
    family = loop_family.strip()
    if not family:
        raise ValueError("run_summary_loop_family_required")
    _RUN_SUMMARY_BUILDERS[family] = builder


def get_run_summary_builder(loop_family: str) -> RunSummaryBuilder | None:
    return _RUN_SUMMARY_BUILDERS.get(loop_family.strip())


def require_run_summary_builder(loop_family: str) -> RunSummaryBuilder:
    builder = get_run_summary_builder(loop_family)
    if builder is None:
        raise RunSummaryBuilderLookupError(f"run_summary_builder_not_registered:{loop_family}")
    return builder
