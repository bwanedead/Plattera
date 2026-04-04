"""Mechanical helpers for append-only LLM-authored continuity journal carriage.

The harness stores, orders, validates, and slices entries; it does not interpret
or summarize author payloads.

Compaction and prompt-visible "recent" rows use the **same** mechanical rule:
the last ``keep_n`` distinct ``kernel_turn_index`` values appearing in
``continuity_journal_entries``, ``kernel_step_records``, and
``kernel_step_result_records``. That keeps folded journal rows, step records,
and bounded tool-result rows aligned by turn.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .loop_state import LoopMemoryState

# Mechanical caps (not semantic ranking).
_MAX_OPERATOR_PROGRESS_CHARS = 4096
_MAX_COMPACTED_SUMMARY_CHARS = 32000
# Cap prior summary size inside the compaction prompt only (mechanical bound).
_MAX_COMPACTION_PRIOR_IN_PROMPT_CHARS = 12000
# JSON-ish bound for tool outputs copied into continuity (mechanical only).
_MAX_OUTPUTS_FOR_CONTINUITY_JSON_CHARS = 8192


def _clamp_optional_str(text: str | None, max_chars: int) -> str | None:
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    if len(s) <= max_chars:
        return s
    return s[:max_chars]


def clamp_operator_progress_message(text: str | None) -> str | None:
    """Bound stored progress string length without rewriting meaning."""
    return _clamp_optional_str(text, _MAX_OPERATOR_PROGRESS_CHARS)


def clamp_compacted_summary_text(text: str | None) -> str | None:
    return _clamp_optional_str(text, _MAX_COMPACTED_SUMMARY_CHARS)


def clamp_compaction_prior_for_prompt(text: str | None) -> str | None:
    """Bound prior summary length embedded in the compaction LLM prompt (storage cap may be larger)."""
    return _clamp_optional_str(text, _MAX_COMPACTION_PRIOR_IN_PROMPT_CHARS)


def wrap_journal_entry(*, kernel_turn_index: int, author_payload: dict[str, Any]) -> dict[str, Any]:
    """Mechanical envelope so ordering does not depend on model-authored keys."""
    return {"kernel_turn_index": int(kernel_turn_index), "author_payload": dict(author_payload)}


def _turn_index(row: dict[str, Any]) -> int | None:
    try:
        return int(row["kernel_turn_index"])
    except (KeyError, TypeError, ValueError):
        return None


def kernel_turn_index_of(row: dict[str, Any]) -> int | None:
    """Public alias for mechanical turn lookup on journal, step, or result rows."""
    return _turn_index(row)


def fold_rows_not_yet_sent_to_compaction(
    journal_fold: list[dict[str, Any]],
    step_fold: list[dict[str, Any]],
    step_result_fold: list[dict[str, Any]],
    *,
    covered_through_turn_index: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Exclude rows already included in a prior successful compaction call (by ``kernel_turn_index``)."""

    def keep(row: dict[str, Any]) -> bool:
        t = _turn_index(row)
        if t is None:
            return True
        return t > int(covered_through_turn_index)

    return (
        [e for e in journal_fold if keep(e)],
        [r for r in step_fold if keep(r)],
        [x for x in step_result_fold if keep(x)],
    )


def max_kernel_turn_in_rows(*parts: list[dict[str, Any]]) -> int | None:
    m: int | None = None
    for rows in parts:
        for row in rows:
            t = _turn_index(row)
            if t is None:
                continue
            m = t if m is None else max(m, t)
    return m


def _collect_sorted_turn_indices(
    journal_entries: list[dict[str, Any]],
    step_records: list[dict[str, Any]],
    step_result_records: list[dict[str, Any]],
) -> list[int]:
    s: set[int] = set()
    for e in journal_entries:
        t = _turn_index(e)
        if t is not None:
            s.add(t)
    for r in step_records:
        t = _turn_index(r)
        if t is not None:
            s.add(t)
    for x in step_result_records:
        t = _turn_index(x)
        if t is not None:
            s.add(t)
    return sorted(s)


def verbatim_turn_indices(
    journal_entries: list[dict[str, Any]],
    step_records: list[dict[str, Any]],
    step_result_records: list[dict[str, Any]],
    *,
    keep_n: int,
) -> frozenset[int]:
    """The last ``keep_n`` distinct kernel turn indices present in journal, steps, or results (union)."""
    if keep_n <= 0:
        return frozenset()
    idx = _collect_sorted_turn_indices(journal_entries, step_records, step_result_records)
    if len(idx) <= keep_n:
        return frozenset(idx)
    return frozenset(idx[-keep_n:])


def partition_continuity_for_compaction(
    journal_entries: list[dict[str, Any]],
    step_records: list[dict[str, Any]],
    step_result_records: list[dict[str, Any]],
    *,
    keep_n: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return fold lists using turn-aligned verbatim tail (journal, steps, results)."""
    kept = verbatim_turn_indices(journal_entries, step_records, step_result_records, keep_n=keep_n)
    j_fold = [e for e in journal_entries if _turn_index(e) not in kept]
    s_fold = [r for r in step_records if _turn_index(r) not in kept]
    r_fold = [x for x in step_result_records if _turn_index(x) not in kept]
    return j_fold, s_fold, r_fold


def recent_journal_entries_for_prompt(
    journal_entries: list[dict[str, Any]],
    step_records: list[dict[str, Any]],
    step_result_records: list[dict[str, Any]],
    *,
    keep_n: int,
) -> list[dict[str, Any]]:
    """Journal rows whose turn is in the verbatim tail (sorted by ``kernel_turn_index``)."""
    kept = verbatim_turn_indices(journal_entries, step_records, step_result_records, keep_n=keep_n)
    rows = [e for e in journal_entries if _turn_index(e) in kept]
    rows.sort(key=lambda e: int(e["kernel_turn_index"]))
    return rows


def recent_step_records_for_prompt(
    journal_entries: list[dict[str, Any]],
    step_records: list[dict[str, Any]],
    step_result_records: list[dict[str, Any]],
    *,
    keep_n: int,
) -> list[dict[str, Any]]:
    """Step rows for the same verbatim tail turns (sorted by turn)."""
    kept = verbatim_turn_indices(journal_entries, step_records, step_result_records, keep_n=keep_n)
    rows = [r for r in step_records if _turn_index(r) in kept]
    rows.sort(key=lambda r: int(r["kernel_turn_index"]))
    return rows


def recent_step_result_records_for_prompt(
    journal_entries: list[dict[str, Any]],
    step_records: list[dict[str, Any]],
    step_result_records: list[dict[str, Any]],
    *,
    keep_n: int,
) -> list[dict[str, Any]]:
    """Tool-result rows for the same verbatim tail turns (sorted by turn)."""
    kept = verbatim_turn_indices(journal_entries, step_records, step_result_records, keep_n=keep_n)
    rows = [x for x in step_result_records if _turn_index(x) in kept]
    rows.sort(key=lambda x: int(x["kernel_turn_index"]))
    return rows


def validate_stored_journal_entry(row: Any) -> dict[str, Any] | None:
    """Return normalized row or None if invalid."""
    if not isinstance(row, dict):
        return None
    try:
        ki = int(row.get("kernel_turn_index"))
    except (TypeError, ValueError):
        return None
    payload = row.get("author_payload")
    if not isinstance(payload, dict):
        return None
    return wrap_journal_entry(kernel_turn_index=ki, author_payload=payload)


def validate_stored_step_record(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    out = dict(row)
    if "kernel_turn_index" not in out:
        return None
    try:
        out["kernel_turn_index"] = int(out["kernel_turn_index"])
    except (TypeError, ValueError):
        return None
    return out


def _bound_outputs_for_continuity(outputs: Mapping[str, Any], *, max_json_chars: int) -> tuple[Any, bool]:
    """Mechanical JSON size bound; may return a truncated string prefix when oversized."""
    as_dict = dict(outputs)
    raw = json.dumps(as_dict, ensure_ascii=False, default=str, sort_keys=True)
    if len(raw) <= max_json_chars:
        try:
            return json.loads(raw), False
        except json.JSONDecodeError:
            return as_dict, False
    return raw[:max_json_chars], True


def build_kernel_step_result_record(
    *,
    kernel_turn_index: int,
    action_type: str | None,
    execution_state: str,
    execution_reason_code: str | None,
    latest_refs_snapshot: Mapping[str, Any],
    outputs: Mapping[str, Any],
    artifact_refs: tuple[str, ...] | list[str],
    max_outputs_json_chars: int = _MAX_OUTPUTS_FOR_CONTINUITY_JSON_CHARS,
) -> dict[str, Any]:
    """Mechanical tool-result row for continuity (copy/truncate only; no semantic shaping)."""
    bounded, truncated = _bound_outputs_for_continuity(outputs, max_json_chars=max_outputs_json_chars)
    refs = list(artifact_refs) if not isinstance(artifact_refs, list) else list(artifact_refs)
    return {
        "kernel_turn_index": int(kernel_turn_index),
        "action_type": action_type,
        "execution_state": str(execution_state),
        "execution_reason_code": execution_reason_code,
        "artifact_refs": refs,
        "latest_refs_snapshot": dict(latest_refs_snapshot),
        "outputs_for_continuity": bounded,
        "result_truncated": bool(truncated),
    }


def apply_kernel_turn_continuity_carriage(
    *,
    loop_memory: LoopMemoryState,
    continuity_journal_entry: dict[str, Any] | None,
    operator_progress_message: str | None,
    action_type: str | None,
    action_inputs: dict[str, Any],
    idempotency_key: str,
    rationale: str | None,
    latest_refs_snapshot: dict[str, Any],
    skip_execution: bool,
    wait_for_human: bool,
    complete_run: bool,
    iteration: int,
    execution_state: str,
    execution_reason_code: str | None,
) -> None:
    """Append journal + step record; update operator progress when the model supplies a new string."""
    cont = loop_memory.continuity
    if continuity_journal_entry is not None:
        cont.continuity_journal_entries.append(
            wrap_journal_entry(
                kernel_turn_index=int(iteration),
                author_payload=dict(continuity_journal_entry),
            )
        )
    if operator_progress_message is not None:
        clamped = clamp_operator_progress_message(operator_progress_message)
        if clamped is not None:
            cont.operator_progress_message = clamped
    cont.kernel_step_records.append(
        {
            "kernel_turn_index": int(iteration),
            "action_type": action_type,
            "action_inputs": dict(action_inputs),
            "idempotency_key": str(idempotency_key),
            "rationale": rationale,
            "latest_refs_snapshot": dict(latest_refs_snapshot),
            "skip_execution": bool(skip_execution),
            "wait_for_human": bool(wait_for_human),
            "complete_run": bool(complete_run),
            "execution_state": str(execution_state),
            "execution_reason_code": execution_reason_code,
        }
    )
