from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .run_state import SharedRunStateEnvelope

RunStateBuilder = Callable[[dict[str, Any]], "SharedRunStateEnvelope"]

_RUN_STATE_BUILDERS: dict[str, RunStateBuilder] = {}


class RunStateBuilderLookupError(KeyError):
    """Raised when a requested run-state builder is not registered."""


def register_run_state_builder(*, loop_family: str, builder: RunStateBuilder) -> None:
    family = loop_family.strip()
    if not family:
        raise ValueError("run_state_loop_family_required")
    _RUN_STATE_BUILDERS[family] = builder


def get_run_state_builder(loop_family: str) -> RunStateBuilder | None:
    return _RUN_STATE_BUILDERS.get(loop_family.strip())


def require_run_state_builder(loop_family: str) -> RunStateBuilder:
    builder = get_run_state_builder(loop_family)
    if builder is None:
        raise RunStateBuilderLookupError(f"run_state_builder_not_registered:{loop_family}")
    return builder
