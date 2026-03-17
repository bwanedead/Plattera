"""Rationale-continuity strip — bounded carry-forward of decision reasoning.

Derived from kernel trace events (RawTraceEvent dicts from KernelTraceCollector).
Synthesizes one entry per iteration from: focus_selection, move_resolution,
execution, and progress_evaluation events.

The strip is populated on context.rationale_strip_snapshot by the kernel before
hook 4 (build_focus_packet) each iteration. Domain packs inject it into their
focus packet so the LLM sees a compact history of why decisions were made.

Entry shape:
    iteration_index:    int
    focus_key:          str | None
    move_type:          str | None
    why_summary:        str   (rationale from move_resolved, capped at per_entry_cap)
    outcome_summary:    str   (execution_state from execution event)
    carry_forward_hint: str   (progress reason_code from progress_evaluation)
"""
from __future__ import annotations

from typing import Any

# Phase names emitted by KernelTraceCollector (match trace_collector.py exactly).
_PHASE_FOCUS = "focus_selection"
_PHASE_MOVE = "move_resolution"
_PHASE_EXEC = "execution"
_PHASE_PROGRESS = "progress_evaluation"


def build_rationale_continuity_strip(
    raw_events: list[dict[str, Any]],
    *,
    max_entries: int = 5,
    per_entry_cap: int = 256,
) -> list[dict[str, Any]]:
    """Derive a bounded rationale-continuity strip from kernel trace events.

    Processes the serialized RawTraceEvent dicts returned by
    ``KernelTraceCollector.build_raw_events()``. Returns the most recent
    ``max_entries`` iterations, oldest-first (readable as carry-forward narrative).

    Args:
        raw_events: serialised RawTraceEvent dicts from KernelTraceCollector.
        max_entries: maximum number of iteration entries to return.
        per_entry_cap: character cap applied to each string field in an entry.

    Returns:
        List of entry dicts, oldest-first, bounded to max_entries.
    """
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

        if phase == _PHASE_FOCUS:
            bucket["focus_key"] = payload.get("focus_key")
        elif phase == _PHASE_MOVE:
            bucket.setdefault("move_type", payload.get("move_type"))
            bucket.setdefault("why_summary", str(payload.get("rationale") or ""))
        elif phase == _PHASE_EXEC:
            state = str(payload.get("execution_state") or "")
            rc = str(event.get("reason_code") or "")
            bucket["outcome_summary"] = f"{state}: {rc}" if rc else state
        elif phase == _PHASE_PROGRESS:
            bucket["carry_forward_hint"] = str(payload.get("reason_code") or "")

    sorted_iters = sorted(by_iteration.keys())
    recent = sorted_iters[-max_entries:] if len(sorted_iters) > max_entries else sorted_iters

    entries: list[dict[str, Any]] = []
    for iter_idx in recent:
        bucket = by_iteration[iter_idx]
        entries.append({
            "iteration_index": iter_idx,
            "focus_key": bucket.get("focus_key"),
            "move_type": bucket.get("move_type"),
            "why_summary": _cap(str(bucket.get("why_summary") or ""), per_entry_cap),
            "outcome_summary": _cap(str(bucket.get("outcome_summary") or ""), per_entry_cap),
            "carry_forward_hint": _cap(str(bucket.get("carry_forward_hint") or ""), per_entry_cap),
        })

    return entries


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
