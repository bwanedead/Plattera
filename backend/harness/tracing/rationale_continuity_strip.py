"""Rationale-continuity strip — bounded carry-forward from kernel trace events.

Derives a short list of per-iteration summaries from serialized ``RawTraceEvent``
dicts (see ``KernelTraceCollector``). Only **mechanical** phases emitted by the
current collector are interpreted — today that is ``phase == "execution"`` for
step dispatch outcomes.

The strip is derived from persisted trace events only; it does not import
orchestration staging vocabulary or semantic phase models.
"""
from __future__ import annotations

from typing import Any

_PHASE_EXEC = "execution"


def build_rationale_continuity_strip(
    raw_events: list[dict[str, Any]],
    *,
    max_entries: int = 5,
    per_entry_cap: int = 256,
) -> list[dict[str, Any]]:
    """Derive a bounded rationale-continuity strip from kernel trace events."""
    by_iteration: dict[int, dict[str, Any]] = {}

    for event in raw_events:
        if not isinstance(event, dict):
            continue
        phase = event.get("phase")
        iter_idx = event.get("iteration_index")
        if iter_idx is None or phase is None:
            continue
        try:
            iter_idx = int(iter_idx)
        except (TypeError, ValueError):
            continue

        payload = event.get("payload") or {}
        if not isinstance(payload, dict):
            continue

        bucket = by_iteration.setdefault(iter_idx, {})

        if phase == _PHASE_EXEC:
            bucket["execution_state"] = str(payload.get("execution_state") or "")
            bucket["exec_retryable"] = payload.get("retryable")
            bucket["exec_reason_code"] = str(event.get("reason_code") or "")

    if not by_iteration:
        return []

    sorted_iters = sorted(by_iteration.keys())
    candidates: list[tuple[int, dict[str, Any], int]] = []
    for iter_idx in sorted_iters:
        bucket = by_iteration[iter_idx]
        candidates.append((iter_idx, bucket, _relevance_rank(bucket)))

    if len(candidates) > max_entries:
        work = list(candidates)
        while len(work) > max_entries:
            worst_rank = max(r for _, _, r in work)
            for i, (_, _, r) in enumerate(work):
                if r == worst_rank:
                    work.pop(i)
                    break
        candidates = work

    entries: list[dict[str, Any]] = []
    for iter_idx, bucket, _ in candidates:
        exec_state = str(bucket.get("execution_state") or "")
        exec_retryable = bucket.get("exec_retryable")
        exec_rc = str(bucket.get("exec_reason_code") or "")
        move_type = str(bucket.get("move_type") or "")
        outcome = _format_outcome_summary(exec_state, exec_rc, move_type, per_entry_cap)
        hint = _derive_carry_forward_hint(exec_state, exec_retryable)

        entries.append(
            {
                "iteration_index": iter_idx,
                "focus_key": bucket.get("focus_key"),
                "move_type": move_type or None,
                "why_summary": "",
                "outcome_summary": outcome,
                "carry_forward_hint": hint,
            }
        )

    return entries


def _relevance_rank(bucket: dict[str, Any]) -> int:
    exec_state = str(bucket.get("execution_state") or "")
    if exec_state == "refused":
        return 1
    return 4


def _derive_carry_forward_hint(execution_state: str, retryable: Any) -> str:
    if execution_state == "refused":
        if retryable is True:
            return "adjust inputs/shape; prior attempt refused (retryable)"
        return "blocked by invariant/capability; escalate or change approach"
    return ""


def _format_outcome_summary(
    execution_state: str,
    exec_reason_code: str,
    move_type: str,
    cap: int,
) -> str:
    if execution_state == "refused":
        rc = exec_reason_code or "refusal"
        return _cap(f"refused ({rc})", cap)
    if execution_state == "skipped":
        label = move_type or "skip"
        return _cap(f"skipped ({label})", cap)
    if execution_state == "deduped":
        return "deduped (idempotent)"
    if execution_state == "executed":
        return "executed"
    return _cap(execution_state, cap) if execution_state else ""


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
