"""Mechanical harness run quiescence assessment (PID/activity only)."""

from __future__ import annotations

from harness.cli._process_util import is_pid_alive
from harness.cli.run_state import read_state

REASON_RUN_NOT_QUIESCENT = "run_not_quiescent"
REASON_RUN_ACTIVITY_UNKNOWN = "run_activity_unknown"

__all__ = [
    "REASON_RUN_ACTIVITY_UNKNOWN",
    "REASON_RUN_NOT_QUIESCENT",
    "assess_run_quiescence",
]


def assess_run_quiescence(run_id: str) -> str | None:
    """Return ``None`` when the run is safe to mutate; else a stable refuse reason."""
    state = read_state(run_id)
    if state is None:
        return REASON_RUN_ACTIVITY_UNKNOWN
    try:
        pid = int(state.pid)
    except (TypeError, ValueError):
        return REASON_RUN_ACTIVITY_UNKNOWN
    if pid <= 0:
        return None
    try:
        alive = is_pid_alive(pid)
    except Exception:
        return REASON_RUN_ACTIVITY_UNKNOWN
    if alive:
        return REASON_RUN_NOT_QUIESCENT
    return None
