"""Deterministic kernel state machine transitions for Agent Kernel v0."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple

from .models import KernelState


class KernelEvent(str, Enum):
    """Explicit events that drive deterministic state transitions."""

    SOURCE_READY = "source_ready"
    ANALYSIS_COMPLETED = "analysis_completed"
    REVIEW_COMPLETED = "review_completed"
    REPAIR_REQUESTED = "repair_requested"
    REPAIR_COMPLETED = "repair_completed"
    PACKAGE_COMMITTED = "package_committed"
    FINISH = "finish"

    # Transitional aliases for compatibility with older workflow-oriented call sites.
    IR_READY = SOURCE_READY
    COMPILE_COMPLETED = ANALYSIS_COMPLETED
    JUDGE_COMPLETED = REVIEW_COMPLETED
    MAP_COMPLETED = PACKAGE_COMMITTED


@dataclass(frozen=True)
class TransitionError(ValueError):
    """Raised when an event is invalid for the current state."""

    state: KernelState
    event: KernelEvent

    def __str__(self) -> str:
        return f"Invalid transition: state={self.state.value}, event={self.event.value}"


_TRANSITIONS: Dict[Tuple[KernelState, KernelEvent], KernelState] = {
    (KernelState.INIT, KernelEvent.SOURCE_READY): KernelState.SOURCE_READY,
    (KernelState.SOURCE_READY, KernelEvent.ANALYSIS_COMPLETED): KernelState.ANALYZED,
    (KernelState.SOURCE_READY, KernelEvent.REVIEW_COMPLETED): KernelState.REVIEWED,
    (KernelState.SOURCE_READY, KernelEvent.REPAIR_REQUESTED): KernelState.REPAIRING,
    (KernelState.ANALYZED, KernelEvent.REVIEW_COMPLETED): KernelState.PACKAGE_READY,
    (KernelState.ANALYZED, KernelEvent.REPAIR_REQUESTED): KernelState.REPAIRING,
    (KernelState.REVIEWED, KernelEvent.ANALYSIS_COMPLETED): KernelState.PACKAGE_READY,
    (KernelState.REVIEWED, KernelEvent.REPAIR_REQUESTED): KernelState.REPAIRING,
    (KernelState.REPAIRING, KernelEvent.REPAIR_COMPLETED): KernelState.SOURCE_READY,
    (KernelState.REPAIRING, KernelEvent.ANALYSIS_COMPLETED): KernelState.ANALYZED,
    (KernelState.REPAIRING, KernelEvent.REVIEW_COMPLETED): KernelState.REVIEWED,
    (KernelState.PACKAGE_READY, KernelEvent.PACKAGE_COMMITTED): KernelState.PACKAGE_COMMITTED,
    (KernelState.PACKAGE_READY, KernelEvent.REPAIR_REQUESTED): KernelState.REPAIRING,
    (KernelState.PACKAGE_COMMITTED, KernelEvent.FINISH): KernelState.DONE,
}


def can_transition(state: KernelState, event: KernelEvent) -> bool:
    """Return whether a state/event pair is valid."""
    return (state, event) in _TRANSITIONS


def advance_state(state: KernelState, event: KernelEvent) -> KernelState:
    """Advance to the next deterministic state or raise TransitionError."""
    next_state = _TRANSITIONS.get((state, event))
    if next_state is None:
        raise TransitionError(state=state, event=event)
    return next_state
