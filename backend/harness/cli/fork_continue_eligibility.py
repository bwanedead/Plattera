"""Continue-fork eligibility gates (generic CLI control-plane)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.cli.resume import is_same_run_resumable_reason
from harness.cli.resume_paths import latest_existing_turn_number
from harness.cli.run_quiescence import assess_run_quiescence
from harness.cli.run_state import HarnessCliRunState

REASON_CONTINUE_NOT_TERMINAL = "continue_not_terminal"
REASON_CONTINUE_COMPLETED = "continue_completed"
REASON_CONTINUE_WAITING_HITL = "continue_waiting_hitl"
REASON_CONTINUE_OPERATOR_RESUMABLE = "continue_operator_resumable"
REASON_CONTINUE_TERMINAL_NOT_ELIGIBLE = "continue_terminal_not_eligible"
REASON_CONTINUE_CHECKPOINT_NOT_LATEST = "continue_checkpoint_not_latest"
REASON_CONTINUE_RESULT_MALFORMED = "continue_result_malformed"
REASON_CONTINUE_TERMINAL_CONFLICT = "continue_terminal_conflict"

_CONTINUE_TERMINAL_CLASSES = frozenset({"failed", "exhausted"})
_CONTINUE_REASON_CODES = frozenset(
    {
        "model_call_failed",
        "recoverable_turn_failure_budget_exhausted",
    }
)
_COMPLETED_CLASSES = frozenset({"completed", "complete", "succeeded", "success"})
_COMPLETED_REASONS = frozenset({"complete_run"})
_HITL_REASONS = frozenset({"wait_for_human"})


def continue_pre_allocate_refusal(
    *,
    source_run_id: str,
    source_state: HarnessCliRunState,
    source_run_dir: Path,
    from_turn: int,
) -> str | None:
    """Return a stable refuse code, or None when continuation may allocate."""
    quiet = assess_run_quiescence(source_run_id)
    if quiet:
        return quiet
    terminal_err = continue_terminal_refusal(source_run_id=source_run_id, source_state=source_state)
    if terminal_err:
        return terminal_err
    latest = latest_existing_turn_number(run_dir=source_run_dir)
    if latest is None or from_turn != latest:
        return REASON_CONTINUE_CHECKPOINT_NOT_LATEST
    return None


def continue_terminal_refusal(
    *,
    source_run_id: str,
    source_state: HarnessCliRunState,
) -> str | None:
    del source_run_id
    result, result_err = _load_terminal_object(source_state.paths.result_file)
    if result_err:
        return result_err
    result_coord = _terminal_coordinate_error(result) if result is not None else None
    if result_coord:
        return result_coord
    done, done_err = _load_terminal_object(source_state.paths.done_file)
    if done_err:
        return done_err
    done_coord = _terminal_coordinate_error(done) if done is not None else None
    if done_coord:
        return done_coord
    if result is None and done is None:
        return REASON_CONTINUE_NOT_TERMINAL
    if result is not None and done is not None:
        if _terminal_posture(result) != _terminal_posture(done):
            return REASON_CONTINUE_TERMINAL_CONFLICT
    return _classify_terminal(result if result is not None else done)


def _classify_terminal(result: dict[str, Any] | None) -> str | None:
    if result is None:
        return REASON_CONTINUE_NOT_TERMINAL
    posture = _terminal_posture(result)
    if posture.hitl:
        return REASON_CONTINUE_WAITING_HITL
    if posture.operator_resumable:
        return REASON_CONTINUE_OPERATOR_RESUMABLE
    if posture.completed:
        return REASON_CONTINUE_COMPLETED
    if posture.terminal_class == "paused":
        return REASON_CONTINUE_WAITING_HITL
    if (
        posture.terminal_class in _CONTINUE_TERMINAL_CLASSES
        or posture.reason_code in _CONTINUE_REASON_CODES
    ):
        return None
    return REASON_CONTINUE_TERMINAL_NOT_ELIGIBLE


@dataclass(frozen=True)
class _TerminalPosture:
    terminal_class: str
    status: str
    reason_code: str
    wait_for_human: bool
    hitl: bool
    completed: bool
    operator_resumable: bool


def _terminal_coordinate_error(doc: dict[str, Any]) -> str | None:
    """Refuse present coordinates that are not canonical nonblank strings."""
    for key in ("terminal_class", "status", "reason_code"):
        if key not in doc:
            continue
        if not _canonical_token(doc.get(key)):
            return REASON_CONTINUE_RESULT_MALFORMED
    if "wait_for_human" in doc and type(doc.get("wait_for_human")) is not bool:
        return REASON_CONTINUE_RESULT_MALFORMED
    return None


def _canonical_token(value: object) -> bool:
    return type(value) is str and bool(value) and value.strip() == value


def _terminal_posture(doc: dict[str, Any]) -> _TerminalPosture:
    reason = _token(doc.get("reason_code"))
    terminal_class = _token(doc.get("terminal_class"))
    status = _token(doc.get("status"))
    wait_for_human = doc.get("wait_for_human") is True
    return _TerminalPosture(
        terminal_class=terminal_class,
        status=status,
        reason_code=reason,
        wait_for_human=wait_for_human,
        hitl=wait_for_human or reason in _HITL_REASONS,
        completed=(
            terminal_class in _COMPLETED_CLASSES
            or status in _COMPLETED_CLASSES
            or reason in _COMPLETED_REASONS
        ),
        operator_resumable=is_same_run_resumable_reason(reason),
    )


def _load_terminal_object(path: str) -> tuple[dict[str, Any] | None, str | None]:
    file_path = Path(path)
    if not file_path.is_file():
        return None, None
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None, REASON_CONTINUE_RESULT_MALFORMED
    if type(raw) is not dict:
        return None, REASON_CONTINUE_RESULT_MALFORMED
    return raw, None


def _token(value: object) -> str:
    return value if type(value) is str else ""
