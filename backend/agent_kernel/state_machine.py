"""Deterministic kernel state machine transitions for Agent Kernel v0."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple

from .models import KernelState


class KernelEvent(str, Enum):
    """Explicit events that drive deterministic state transitions."""

    IR_READY = "ir_ready"
    COMPILE_COMPLETED = "compile_completed"
    JUDGE_COMPLETED = "judge_completed"
    REPAIR_REQUESTED = "repair_requested"
    REPAIR_COMPLETED = "repair_completed"
    MAP_COMPLETED = "map_completed"
    FINISH = "finish"


@dataclass(frozen=True)
class TransitionError(ValueError):
    """Raised when an event is invalid for the current state."""

    state: KernelState
    event: KernelEvent

    def __str__(self) -> str:
        return f"Invalid transition: state={self.state.value}, event={self.event.value}"


_TRANSITIONS: Dict[Tuple[KernelState, KernelEvent], KernelState] = {
    (KernelState.INIT, KernelEvent.IR_READY): KernelState.HAVE_IR,
    (KernelState.HAVE_IR, KernelEvent.COMPILE_COMPLETED): KernelState.HAVE_COMPILE,
    (KernelState.HAVE_IR, KernelEvent.JUDGE_COMPLETED): KernelState.HAVE_JUDGE,
    (KernelState.HAVE_IR, KernelEvent.REPAIR_REQUESTED): KernelState.REPAIRING,
    (KernelState.HAVE_COMPILE, KernelEvent.JUDGE_COMPLETED): KernelState.READY_TO_MAP,
    (KernelState.HAVE_COMPILE, KernelEvent.REPAIR_REQUESTED): KernelState.REPAIRING,
    (KernelState.HAVE_JUDGE, KernelEvent.COMPILE_COMPLETED): KernelState.READY_TO_MAP,
    (KernelState.HAVE_JUDGE, KernelEvent.REPAIR_REQUESTED): KernelState.REPAIRING,
    (KernelState.REPAIRING, KernelEvent.REPAIR_COMPLETED): KernelState.HAVE_IR,
    (KernelState.REPAIRING, KernelEvent.COMPILE_COMPLETED): KernelState.HAVE_COMPILE,
    (KernelState.REPAIRING, KernelEvent.JUDGE_COMPLETED): KernelState.HAVE_JUDGE,
    (KernelState.READY_TO_MAP, KernelEvent.MAP_COMPLETED): KernelState.MAPPED,
    (KernelState.READY_TO_MAP, KernelEvent.REPAIR_REQUESTED): KernelState.REPAIRING,
    (KernelState.MAPPED, KernelEvent.FINISH): KernelState.DONE,
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
