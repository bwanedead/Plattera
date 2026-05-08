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

import hashlib
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
# 32000 comfortably covers typical multi-draft hydrate outputs (~8-10k chars)
# without straining prompt budgets.  The old 8192 value was tight enough to
# clip a 3-draft hydrate (8453 chars) into a raw string prefix, destroying
# dict structure before text_field_summaries could traverse it.
_MAX_OUTPUTS_FOR_CONTINUITY_JSON_CHARS = 32000
# Per-field clip applied when the full dict still exceeds the cap after
# the cap is raised (extreme cases with very many or very large fields).
_STRUCTURED_CLIP_FIELD_CHARS = 2000
# Sentinel key written into clip-replacement dicts so tool_result_slices can
# detect clipped fields and mark them is_complete=False with the original length.
# Paired constant: tool_result_slices.py uses the same literal.
CLIP_SENTINEL_KEY: str = "__clipped__"


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


# Compact caps for host-derived continuity fields (mechanical; semantically bounded).
_HOST_RATIONALE_MAX_CHARS = 1200
_HOST_ACTION_TARGET_MAX_CHARS = 400
_HOST_NET_EFFECT_MAX_CHARS = 400
_HOST_REF_IDS_IN_SUMMARY = 8


def _clip(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def _summarize_action_target(
    action_type: str | None,
    action_inputs: Mapping[str, Any],
) -> str:
    """Compact string naming what this action targeted (ref bundle or input keys).

    Visible in the journal so repeated rereads of the same bundle are legible
    from memory alone, without needing prompt_observability_summary.
    """
    if not action_type:
        return ""
    ref_ids = action_inputs.get("ref_ids")
    if isinstance(ref_ids, (list, tuple)) and ref_ids:
        refs = [str(x).strip() for x in ref_ids if isinstance(x, str) and str(x).strip()]
        shown = refs[:_HOST_REF_IDS_IN_SUMMARY]
        suffix = "" if len(refs) <= _HOST_REF_IDS_IN_SUMMARY else f" (+{len(refs) - _HOST_REF_IDS_IN_SUMMARY} more)"
        return _clip("refs: " + ", ".join(shown) + suffix, _HOST_ACTION_TARGET_MAX_CHARS)
    if action_inputs:
        keys = sorted(str(k) for k in action_inputs.keys())
        return _clip("inputs: " + ", ".join(keys[:8]), _HOST_ACTION_TARGET_MAX_CHARS)
    return ""


def _ref_bundle_signature(
    action_type: str | None,
    action_inputs: Mapping[str, Any],
) -> str | None:
    """Short hash over action_type + inputs; stable fingerprint for repeated-reread detection."""
    if not action_type:
        return None
    try:
        payload = json.dumps(
            {"action_type": action_type, "action_inputs": dict(action_inputs)},
            sort_keys=True,
            default=str,
            ensure_ascii=False,
        )
    except (TypeError, ValueError):
        return None
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]


def _refs_changed(
    prior_refs: Mapping[str, Any] | None,
    post_refs: Mapping[str, Any],
) -> bool:
    if prior_refs is None:
        return bool(post_refs)
    try:
        prior_blob = json.dumps(dict(prior_refs), sort_keys=True, default=str, ensure_ascii=False)
        post_blob = json.dumps(dict(post_refs), sort_keys=True, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return True
    return prior_blob != post_blob


def _derive_net_effect(
    *,
    execution_state: str,
    execution_reason_code: str | None,
    skip_execution: bool,
    complete_run: bool,
    wait_for_human: bool,
    patch_outcome: str | None,
    refs_changed: bool,
) -> str:
    if complete_run:
        return "terminal: complete_run signaled"
    if wait_for_human:
        return "blocked: awaiting HITL"
    if skip_execution:
        if patch_outcome == "applied":
            return "no-dispatch; state patch applied"
        if patch_outcome in {"rejected", "not_applied"}:
            return f"no-dispatch; state patch {patch_outcome}"
        return "no-dispatch; no state delta"
    state = (execution_state or "").strip().lower()
    if state == "executed":
        if refs_changed:
            return "tool executed; refs changed"
        return "tool executed; no ref delta"
    if state == "refused":
        return f"tool refused: {execution_reason_code or 'unknown'}"
    if state:
        return f"tool {state}"
    return ""


def build_host_derived_continuity_payload(
    *,
    kernel_turn_index: int,
    active_item_id_snapshot: str | None,
    rationale: str | None,
    action_type: str | None,
    action_inputs: Mapping[str, Any],
    skip_execution: bool,
    wait_for_human: bool,
    complete_run: bool,
    execution_state: str,
    execution_reason_code: str | None,
    patch_outcome: str | None,
    prior_latest_refs: Mapping[str, Any] | None,
    post_latest_refs: Mapping[str, Any],
    author_addendum: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Canonical host-derived continuity payload for a single turn.

    Always emitted, even when the model omits ``continuity_journal_entry``. The
    shape carries why-this-move (rationale) and the turn's net effect so that
    future turns can read memory and see what happened, not just re-read raw
    artifacts. Model-authored continuity, when present, is nested under
    ``author_addendum`` — never substituted for the canonical record.
    """
    refs_changed = _refs_changed(prior_latest_refs, post_latest_refs)
    net_effect = _derive_net_effect(
        execution_state=execution_state,
        execution_reason_code=execution_reason_code,
        skip_execution=skip_execution,
        complete_run=complete_run,
        wait_for_human=wait_for_human,
        patch_outcome=patch_outcome,
        refs_changed=refs_changed,
    )
    clipped_rationale = _clip(str(rationale or "").strip(), _HOST_RATIONALE_MAX_CHARS) or None
    host_derived: dict[str, Any] = {
        "kernel_turn_index": int(kernel_turn_index),
        "active_item_id": active_item_id_snapshot,
        "action_type": action_type,
        "action_target_summary": _summarize_action_target(action_type, action_inputs),
        "action_ref_bundle_signature": _ref_bundle_signature(action_type, action_inputs),
        "rationale": clipped_rationale,
        "execution_state": str(execution_state) if execution_state else None,
        "execution_reason_code": execution_reason_code,
        "patch_outcome": patch_outcome,
        "refs_changed": bool(refs_changed),
        "net_effect": _clip(net_effect, _HOST_NET_EFFECT_MAX_CHARS) or None,
    }
    payload: dict[str, Any] = {"host_derived": host_derived}
    if author_addendum:
        payload["author_addendum"] = dict(author_addendum)
    return payload


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


def _clip_large_text_fields(value: Any, *, max_chars: int) -> Any:
    """Recursively clip oversized string leaves to keep dict structure intact under JSON size pressure.

    Oversized strings are replaced by a sentinel dict carrying the original length and a
    bounded excerpt rather than a plain trimmed string.  This lets ``_extract_text_field_summaries``
    in ``tool_result_slices`` detect clipped fields and emit ``is_complete: false`` with the
    correct ``original_char_length``, preventing the truncated text from being misreported as
    complete to the agent.

    Sentinel shape::

        {
            "__clipped__": True,
            "original_char_length": <int>,
            "excerpt": <first max_chars chars of the original string>,
        }

    Non-string nodes pass through unchanged.
    """
    if isinstance(value, str):
        if len(value) <= max_chars:
            return value
        return {
            CLIP_SENTINEL_KEY: True,
            "original_char_length": len(value),
            "excerpt": value[:max_chars],
        }
    if isinstance(value, dict):
        return {k: _clip_large_text_fields(v, max_chars=max_chars) for k, v in value.items()}
    if isinstance(value, list):
        return [_clip_large_text_fields(item, max_chars=max_chars) for item in value]
    return value


def _bound_outputs_for_continuity(outputs: Mapping[str, Any], *, max_json_chars: int) -> tuple[Any, bool]:
    """Mechanical JSON size bound; prefers a field-clipped dict over a raw string prefix when oversized.

    Return value is ``(stored_value, result_truncated)``.

    * **Within cap** → returns the round-tripped dict, ``truncated=False``.
    * **Over cap after field-clip** → returns the field-clipped dict, ``truncated=True``; dict
      structure is preserved so ``_extract_text_field_summaries`` can still traverse it.
    * **Extreme fallback** (field-clipped dict still over cap) → returns a raw JSON string
      prefix, ``truncated=True``.  This branch should only trigger for outputs with an
      unusual number of very large non-string fields.
    """
    as_dict = dict(outputs)
    raw = json.dumps(as_dict, ensure_ascii=False, default=str, sort_keys=True)
    if len(raw) <= max_json_chars:
        try:
            return json.loads(raw), False
        except json.JSONDecodeError:
            return as_dict, False
    # Oversized: apply field-level clipping to keep dict structure intact.
    clipped = _clip_large_text_fields(as_dict, max_chars=_STRUCTURED_CLIP_FIELD_CHARS)
    clipped_raw = json.dumps(clipped, ensure_ascii=False, default=str, sort_keys=True)
    if len(clipped_raw) <= max_json_chars:
        return clipped, True
    # Extreme fallback: even the clipped dict exceeds the cap; return a string prefix.
    return clipped_raw[:max_json_chars], True


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


def _strip_volatile_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _strip_volatile_fields(raw)
            for key, raw in value.items()
            if str(key) not in {"schema_version", "updated_at_epoch_seconds"}
        }
    if isinstance(value, list):
        return [_strip_volatile_fields(item) for item in value]
    return value


def _work_state_signature(loop_memory: LoopMemoryState) -> str:
    cont = loop_memory.continuity
    payload = {
        "mission_state": _strip_volatile_fields(cont.mission_state.model_dump(mode="json")),
        "resolution_state": _strip_volatile_fields(cont.resolution_state.model_dump(mode="json")),
        "latest_refs": _strip_volatile_fields(dict(cont.latest_refs)),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


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
    """Append journal + step record; always emit a canonical host-derived journal entry.

    The host-derived entry carries why-this-move (rationale), the ref bundle
    signature, the patch outcome, and a net-effect summary. Model-authored
    ``continuity_journal_entry`` is preserved as ``author_addendum`` inside the
    same payload — it never replaces the host record and never erases continuity
    by omission.
    """
    cont = loop_memory.continuity
    active_item_id_snapshot = cont.active_item_id
    if active_item_id_snapshot is None:
        active_item_id_snapshot = cont.resolution_state.active_item_id

    prior_step = cont.kernel_step_records[-1] if cont.kernel_step_records else None
    prior_refs = prior_step.get("latest_refs_snapshot") if isinstance(prior_step, dict) else None
    patch_outcome_raw = cont.state_patch_feedback.get("outcome") if isinstance(cont.state_patch_feedback, dict) else None
    patch_outcome = str(patch_outcome_raw) if patch_outcome_raw else None

    host_payload = build_host_derived_continuity_payload(
        kernel_turn_index=int(iteration),
        active_item_id_snapshot=active_item_id_snapshot,
        rationale=rationale,
        action_type=action_type,
        action_inputs=dict(action_inputs),
        skip_execution=bool(skip_execution),
        wait_for_human=bool(wait_for_human),
        complete_run=bool(complete_run),
        execution_state=str(execution_state),
        execution_reason_code=execution_reason_code,
        patch_outcome=patch_outcome,
        prior_latest_refs=prior_refs if isinstance(prior_refs, Mapping) else None,
        post_latest_refs=dict(latest_refs_snapshot),
        author_addendum=continuity_journal_entry if continuity_journal_entry else None,
    )
    cont.continuity_journal_entries.append(
        wrap_journal_entry(
            kernel_turn_index=int(iteration),
            author_payload=host_payload,
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
            "active_item_id_snapshot": active_item_id_snapshot,
            "resolution_item_count_snapshot": len(cont.resolution_state.items),
            "success_condition_count_snapshot": len(cont.mission_state.success_conditions),
            "closure_ready_to_close_snapshot": bool(cont.mission_state.closure_state.ready_to_close),
            "closure_ready_to_publish_snapshot": bool(cont.mission_state.closure_state.ready_to_publish),
            "work_state_signature": _work_state_signature(loop_memory),
        }
    )
