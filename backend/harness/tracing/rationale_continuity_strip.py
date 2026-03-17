"""Rationale-continuity strip — bounded carry-forward of decision reasoning.

Derived from kernel trace events (RawTraceEvent dicts from KernelTraceCollector).
Synthesizes one entry per iteration from: focus_selection, move_resolution,
execution, and progress_evaluation events.

The strip is populated on context.rationale_strip_snapshot by the kernel before
hook 4 (build_focus_packet) each iteration. Domain packs inject it into their
focus packet (main reasoning payloads only — not micro-tool prompt builders).

Entry shape:
    iteration_index:    int
    focus_key:          str | None
    move_type:          str | None
    why_summary:        str   (normalized rationale, capped at per_entry_cap)
    outcome_summary:    str   (execution_state summary)
    carry_forward_hint: str   (deterministic tactical guidance; empty for normal progress)

Inclusion / omission rules:
    Include an iteration when it introduces a NEW tactical constraint (execution
    refusal), new escalation implication (HITL / mark_blocked), new evidence posture
    (new_signal_arrived), rising stagnation, or a meaningful tactic shift (focus_key
    or move_type differs from the previous included entry).
    Omit iterations that repeat the same posture and tactic with no new carry-forward
    implication (normal positive-progress steps where nothing changed in approach).

Trimming rule:
    After the inclusion filter, if the candidate list still exceeds max_entries, drop
    oldest low-relevance entries first (normal-progress steps that only made the cut
    due to a tactic shift), then oldest high-relevance entries if still over cap.
"""
from __future__ import annotations

from typing import Any

# Phase names — must match trace_collector.py exactly.
_PHASE_FOCUS = "focus_selection"
_PHASE_MOVE = "move_resolution"
_PHASE_EXEC = "execution"
_PHASE_PROGRESS = "progress_evaluation"

# Progress reason codes that carry tactical or diagnostic significance.
_CRITICAL_PROGRESS_CODES = frozenset({
    "pending_human_feedback_no_new_signal",
    "no_material_change",
    "new_signal_arrived",
    "refresh_pending_reaudit_grace",
})

# Progress reason codes that represent routine forward motion — low carry-forward value.
_ROUTINE_PROGRESS_CODES = frozenset({
    "blocking_count_reduced",
    "blocking_state_changed",
    "audit_signature_changed",
    "initial_iteration_baseline",
    "refresh_improved_blocking_closure",
    "refresh_blocking_signature_changed",
})

# Move types that signal an explicit escalation or dead-end.
_ESCALATION_MOVE_TYPES = frozenset({"request_human_feedback", "mark_blocked"})


def build_rationale_continuity_strip(
    raw_events: list[dict[str, Any]],
    *,
    max_entries: int = 5,
    per_entry_cap: int = 256,
) -> list[dict[str, Any]]:
    """Derive a bounded rationale-continuity strip from kernel trace events.

    Processes the serialised RawTraceEvent dicts returned by
    ``KernelTraceCollector.build_raw_events()``.  Returns at most ``max_entries``
    entries, oldest-first, with low-relevance entries dropped before high-relevance
    ones when trimming is required.

    Args:
        raw_events: serialised RawTraceEvent dicts from KernelTraceCollector.
        max_entries: maximum number of iteration entries to return.
        per_entry_cap: character cap applied to each string field in an entry.

    Returns:
        List of entry dicts, oldest-first, bounded to max_entries.
    """
    # ------------------------------------------------------------------ 1. Parse
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
            # setdefault: first move event wins per iteration.
            bucket.setdefault("move_type", payload.get("move_type"))
            bucket.setdefault("_raw_rationale", str(payload.get("rationale") or ""))

        elif phase == _PHASE_EXEC:
            # Last execution event per iteration wins (skipped+executed can both appear).
            bucket["execution_state"] = str(payload.get("execution_state") or "")
            bucket["exec_retryable"] = payload.get("retryable")
            bucket["exec_reason_code"] = str(event.get("reason_code") or "")

        elif phase == _PHASE_PROGRESS:
            bucket["progress_reason_code"] = str(payload.get("reason_code") or "")
            bucket["made_progress"] = bool(payload.get("made_progress", True))
            bucket["no_progress_streak"] = int(payload.get("no_progress_streak") or 0)

    if not by_iteration:
        return []

    # ------------------------------------------------------------------ 2. Inclusion pass
    sorted_iters = sorted(by_iteration.keys())
    # Each candidate: (iter_idx, bucket, low_relevance_flag)
    candidates: list[tuple[int, dict[str, Any], bool]] = []
    prev_focus: Any = _SENTINEL
    prev_move: Any = _SENTINEL

    for iter_idx in sorted_iters:
        bucket = by_iteration[iter_idx]
        first = prev_focus is _SENTINEL

        if first or _is_noteworthy(bucket, prev_focus, prev_move):
            low_rel = _is_low_relevance(bucket)
            candidates.append((iter_idx, bucket, low_rel))
            prev_focus = bucket.get("focus_key")
            prev_move = bucket.get("move_type")

    # ------------------------------------------------------------------ 3. Trim to max_entries
    if len(candidates) > max_entries:
        # Drop oldest low-relevance first, then oldest regardless.
        # Build working list (mutable) tagged with relevance.
        work = list(candidates)
        while len(work) > max_entries:
            # Find the first (oldest) low-relevance entry.
            dropped = False
            for i, (_, _, low_rel) in enumerate(work):
                if low_rel:
                    work.pop(i)
                    dropped = True
                    break
            if not dropped:
                # All remaining are high-relevance; drop oldest.
                work.pop(0)
        candidates = work

    # ------------------------------------------------------------------ 4. Build entries
    entries: list[dict[str, Any]] = []
    for iter_idx, bucket, _ in candidates:
        exec_state = str(bucket.get("execution_state") or "")
        exec_retryable = bucket.get("exec_retryable")
        exec_rc = str(bucket.get("exec_reason_code") or "")
        move_type = str(bucket.get("move_type") or "")
        progress_rc = str(bucket.get("progress_reason_code") or "")
        made_progress = bool(bucket.get("made_progress", True))
        no_progress_streak = int(bucket.get("no_progress_streak") or 0)

        why = _normalize_why_summary(str(bucket.get("_raw_rationale") or ""), per_entry_cap)
        outcome = _format_outcome_summary(exec_state, exec_rc, move_type, per_entry_cap)
        hint = _derive_carry_forward_hint(
            exec_state, exec_retryable, progress_rc, made_progress, no_progress_streak
        )

        entries.append({
            "iteration_index": iter_idx,
            "focus_key": bucket.get("focus_key"),
            "move_type": move_type or None,
            "why_summary": why,
            "outcome_summary": outcome,
            "carry_forward_hint": hint,
        })

    return entries


# ---------------------------------------------------------------------------
# Inclusion / relevance helpers
# ---------------------------------------------------------------------------

# Sentinel — distinct from None so we can tell "never set" from "set to None".
_SENTINEL = object()


def _is_noteworthy(
    bucket: dict[str, Any],
    prev_focus: Any,
    prev_move: Any,
) -> bool:
    """Return True if this iteration introduces a new tactical implication."""
    exec_state = str(bucket.get("execution_state") or "")
    move_type = str(bucket.get("move_type") or "")
    progress_rc = str(bucket.get("progress_reason_code") or "")
    made_progress = bool(bucket.get("made_progress", True))
    no_progress_streak = int(bucket.get("no_progress_streak") or 0)

    # Any execution refusal — new tactical constraint.
    if exec_state == "refused":
        return True

    # Escalation or dead-end move — new implication.
    if move_type in _ESCALATION_MOVE_TYPES:
        return True

    # Critical progress signal.
    if progress_rc in _CRITICAL_PROGRESS_CODES:
        return True

    # Rising stagnation — needs LLM awareness.
    if not made_progress and no_progress_streak >= 2:
        return True

    # Focus shift — new item being worked.
    if bucket.get("focus_key") != prev_focus:
        return True

    # Move tactic shift — approach changed.
    if move_type != str(prev_move or ""):
        return True

    return False


def _is_low_relevance(bucket: dict[str, Any]) -> bool:
    """Return True if this entry can be dropped first during trimming.

    Low-relevance = normal positive progress with no refusal, escalation, or stagnation.
    Included in the strip because of a tactic shift, but adds the least carry-forward value.
    """
    exec_state = str(bucket.get("execution_state") or "")
    move_type = str(bucket.get("move_type") or "")
    progress_rc = str(bucket.get("progress_reason_code") or "")
    made_progress = bool(bucket.get("made_progress", True))
    no_progress_streak = int(bucket.get("no_progress_streak") or 0)

    if exec_state == "refused":
        return False
    if move_type in _ESCALATION_MOVE_TYPES:
        return False
    if progress_rc in _CRITICAL_PROGRESS_CODES:
        return False
    if not made_progress and no_progress_streak >= 2:
        return False
    # Normal positive progress — low carry-forward value.
    return made_progress and progress_rc in _ROUTINE_PROGRESS_CODES


# ---------------------------------------------------------------------------
# Hint mapping, formatting, and normalization
# ---------------------------------------------------------------------------

def _derive_carry_forward_hint(
    execution_state: str,
    retryable: Any,
    progress_reason_code: str,
    made_progress: bool,
    no_progress_streak: int,
) -> str:
    """Map combined execution + progress signals to a deterministic tactical hint.

    Returns an empty string for routine forward progress (no advisory needed).
    """
    # Execution refusal takes priority — most actionable signal.
    if execution_state == "refused":
        if retryable is True:
            return "adjust inputs/shape; prior attempt refused (retryable)"
        return "blocked by invariant/capability; escalate or change approach"

    # HITL pending — warn against thrashing.
    if progress_reason_code == "pending_human_feedback_no_new_signal":
        return "await HITL; avoid thrash"

    # Refresh grace window — baseline is pre-edit; don't misread as failure.
    if progress_reason_code == "refresh_pending_reaudit_grace":
        return "refresh window; don't treat pre-edit baseline as failure"

    # New evidence — encourage re-evaluation.
    if progress_reason_code == "new_signal_arrived":
        return "new evidence arrived; re-evaluate focus/move"

    # Rising no-progress streak — change tactic urgently.
    if not made_progress and no_progress_streak >= 2:
        return "change tactic: gather new signal or escalate"

    # Single no-progress iteration — softer advisory.
    if not made_progress:
        return "no material change; adjust approach"

    # Routine forward progress — no advisory hint needed.
    return ""


def _format_outcome_summary(
    execution_state: str,
    exec_reason_code: str,
    move_type: str,
    cap: int,
) -> str:
    """Return a compact, normalized outcome summary string."""
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


def _normalize_why_summary(raw: str, limit: int) -> str:
    """Collapse whitespace noise and apply hard cap; return empty string if blank."""
    text = " ".join(raw.split())  # strip + collapse multiline/extra spaces
    return _cap(text, limit) if text else ""


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
