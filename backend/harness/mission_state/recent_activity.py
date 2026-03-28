"""Bounded recent-activity lane for continuity carry-forward.

This helper is observational only. It summarizes what happened recently without
predicting what should happen next.
"""
from __future__ import annotations

from typing import Any


RECENT_ACTIVITY_LANE_VERSION = "recent_activity.v1"

_DEFAULT_RICH_TAIL = 2
_DEFAULT_SUMMARY_TAIL = 5

_MAX_STEP_FIELDS_CHARS = 280
_MAX_CAPSULE_STEPS = 8
_MAX_SUMMARY_CHAIN = 6
_MAX_TRANSITION_REASON_CHARS = 200


def _compact_resolution_progress_for_lane(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    item_id = str(raw.get("item_id") or "").strip()[:96] or None
    state_before = str(raw.get("state_before") or "").strip()[:32] or None
    state_after = str(raw.get("state_after") or "").strip()[:32] or None
    transition_reason = str(raw.get("transition_reason") or "").strip()[:_MAX_TRANSITION_REASON_CHARS] or None
    return {
        "event": str(raw.get("event") or "").strip()[:48] or None,
        "item_id": item_id,
        "state_before": state_before,
        "state_after": state_after,
        "transition_reason": transition_reason,
        "recency_rank": raw.get("recency_rank"),
        "newly_promoted": raw.get("newly_promoted"),
    }


def build_recent_activity_lane(
    continuity_log: list[dict[str, Any]] | None,
    *,
    current_iteration: int | None = None,
    rich_tail: int = _DEFAULT_RICH_TAIL,
    summary_tail: int = _DEFAULT_SUMMARY_TAIL,
) -> dict[str, Any]:
    """Build a recent-skewed iteration window from continuity log entries."""
    log = [row for row in (continuity_log or []) if isinstance(row, dict)]
    groups = _iteration_groups_from_log(log)
    if not groups:
        return {
            "schema_version": RECENT_ACTIVITY_LANE_VERSION,
            "rich_capsules": [],
            "summary_capsules": [],
            "ungrouped_tail": [],
            "bounded_note": "No continuity steps yet.",
        }

    rt = max(1, int(rich_tail))
    st = max(0, int(summary_tail))
    rich_cap = [_rich_capsule_from_block(g) for g in groups[:rt]]
    summary_cap = [_summary_capsule_from_block(g) for g in groups[rt : rt + min(3, st)]]

    has_numeric_iteration = any(_coerce_iteration(e.get("iteration")) is not None for e in log)
    ungrouped_tail = _ungrouped_tail(log, max_entries=4) if has_numeric_iteration else []

    return {
        "schema_version": RECENT_ACTIVITY_LANE_VERSION,
        "current_iteration": current_iteration,
        "rich_capsules": rich_cap,
        "summary_capsules": summary_cap,
        "ungrouped_tail": ungrouped_tail,
        "bounded_note": "Recent path only; full event history is not injected here.",
    }


def _coerce_iteration(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _iteration_groups_from_log(log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not log:
        return []
    if not any(_coerce_iteration(e.get("iteration")) is not None for e in log):
        tail_entries = log[-24:]
        return [{"iteration": None, "steps": tail_entries}] if tail_entries else []

    groups: list[dict[str, Any]] = []
    i = len(log) - 1
    max_groups = _DEFAULT_RICH_TAIL + _DEFAULT_SUMMARY_TAIL + 2
    while i >= 0 and len(groups) < max_groups:
        cur_iter = _coerce_iteration(log[i].get("iteration"))
        if cur_iter is not None:
            block_rev: list[dict[str, Any]] = []
            target = cur_iter
            while i >= 0:
                it = _coerce_iteration(log[i].get("iteration"))
                if it == target:
                    block_rev.append(log[i])
                    i -= 1
                elif it is None:
                    block_rev.append(log[i])
                    i -= 1
                else:
                    break
            block_rev.reverse()
            groups.append({"iteration": target, "steps": block_rev})
            continue
        block_rev = []
        while i >= 0 and _coerce_iteration(log[i].get("iteration")) is None:
            block_rev.append(log[i])
            i -= 1
        block_rev.reverse()
        if block_rev:
            groups.append({"iteration": None, "steps": block_rev})
    return groups


def _rich_capsule_from_block(block: dict[str, Any]) -> dict[str, Any]:
    steps_in = [s for s in list(block.get("steps") or []) if isinstance(s, dict)]
    steps_out: list[dict[str, Any]] = []
    focus_keys: list[str] = []
    for s in steps_in[-_MAX_CAPSULE_STEPS:]:
        dk = str(s.get("decision_key") or "").strip().lower()
        if dk and dk not in focus_keys:
            focus_keys.append(dk)
        steps_out.append(
            {
                "focused_item_ref": dk or None,
                "focus_source": str(s.get("focus_source") or "").strip()[:64] or None,
                "move_chosen": str(s.get("move") or "").strip()[:64],
                "outcome": str(s.get("outcome") or "").strip()[:_MAX_STEP_FIELDS_CHARS],
                "evidence_used_or_attempted": str(s.get("evidence_kind") or "").strip()[:120] or None,
                "gate_posture": (
                    dict(s["gate_posture"]) if isinstance(s.get("gate_posture"), dict) else None
                ),
                "why_closure_not_achieved": (
                    str(s.get("why_no_closure") or "").strip()[:_MAX_STEP_FIELDS_CHARS] or None
                ),
                "state_changes_hint": (
                    str(s.get("state_delta_hint") or "").strip()[:_MAX_STEP_FIELDS_CHARS] or None
                ),
                "resolution_progress_compact": _compact_resolution_progress_for_lane(s.get("resolution_progress")),
            }
        )
    last_step = steps_in[-1] if steps_in else {}
    return {
        "iteration": block.get("iteration"),
        "primary_focus_keys": focus_keys[:4],
        "steps": steps_out,
        "aggregated_outcome": (
            str(last_step.get("outcome") or "").strip()[:_MAX_STEP_FIELDS_CHARS] or None
        ),
    }


def _summary_capsule_from_block(block: dict[str, Any]) -> dict[str, Any]:
    steps_in = [s for s in list(block.get("steps") or []) if isinstance(s, dict)]
    chain = " → ".join(
        str(s.get("move") or "").strip()[:32] for s in steps_in[-_MAX_SUMMARY_CHAIN:] if s.get("move")
    )
    last = steps_in[-1] if steps_in else {}
    return {
        "iteration": block.get("iteration"),
        "move_chain": chain[:240] or None,
        "last_outcome": str(last.get("outcome") or "").strip()[:_MAX_STEP_FIELDS_CHARS] or None,
        "last_focus": str(last.get("decision_key") or "").strip().lower() or None,
    }


def _ungrouped_tail(log: list[dict[str, Any]], *, max_entries: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in log[-max_entries:]:
        if not isinstance(s, dict):
            continue
        if s.get("iteration") is not None:
            continue
        out.append(
            {
                "decision_key": str(s.get("decision_key") or "").strip().lower() or None,
                "move": str(s.get("move") or "").strip()[:64],
                "outcome": str(s.get("outcome") or "").strip()[:_MAX_STEP_FIELDS_CHARS],
            }
        )
    return out
