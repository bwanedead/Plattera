from __future__ import annotations

from typing import Any

_CONFIRMED_STATUSES = {"match", "confirmed"}
_UNRESOLVED_STATES = {"unknown", "candidate_found", "disputed", "accepted_with_risk"}
_SOURCE_COMPLETENESS_VALUES = {"complete", "partial_truncated", "partial_missing_context", "unknown"}
_SCOPE_ID_VALUES = {"target_scope", "outside_target_scope", "unknown_scope"}
_SCOPE_STATUS_VALUES = {"in_target", "outside_target", "unknown"}
_APPROVED_SCOPE_PROOF_CODES = {
    "explicit_outside_target_text",
    "source_truncation_boundary",
    "image_confirms_post_target_cutoff",
    "operator_marked_outside_target",
}
_SCOPE_CLOSURE_STATE_VALUES = {"achieved", "partial", "blocked", "not_attempted"}


def _ensure_ledger_shape(ledger: dict[str, Any] | None) -> dict[str, Any]:
    working = ledger if isinstance(ledger, dict) else {}
    items_raw = working.get("items")
    items = [dict(item) for item in items_raw if isinstance(item, dict)] if isinstance(items_raw, list) else []
    return {
        "items": items,
        "summary": dict(working.get("summary") or {}) if isinstance(working.get("summary"), dict) else {},
        "external_context_injections": [
            dict(row)
            for row in list(working.get("external_context_injections") or [])
            if isinstance(row, dict)
        ],
        "source_completeness": str(working.get("source_completeness") or "unknown").strip().lower() or "unknown",
        "source_completeness_reason": str(working.get("source_completeness_reason") or "").strip() or None,
        "source_limitations": [
            str(v).strip()
            for v in list(working.get("source_limitations") or [])
            if str(v).strip()
        ][:12],
        "scope_summaries": dict(working.get("scope_summaries") or {}) if isinstance(working.get("scope_summaries"), dict) else {},
        "blocker_feedback_state": dict(working.get("blocker_feedback_state") or {}) if isinstance(working.get("blocker_feedback_state"), dict) else {},
    }


def scope_summaries_from_ledger(ledger: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _ensure_ledger_shape(ledger)
    return dict(normalized.get("scope_summaries") or {})

def _normalized_scope_id(raw_scope_id: Any) -> str:
    scope_id = str(raw_scope_id or "").strip().lower()
    if scope_id in _SCOPE_ID_VALUES:
        return scope_id
    return "unknown_scope"

def _scope_id_from_scope_status(scope_status: str) -> str:
    status = _normalize_scope_status(scope_status)
    if status == "in_target":
        return "target_scope"
    if status == "outside_target":
        return "outside_target_scope"
    return "unknown_scope"

def _normalize_scope_status(raw_scope_status: Any) -> str:
    status = str(raw_scope_status or "").strip().lower()
    if status in _SCOPE_STATUS_VALUES:
        return status
    if status in {"target_scope", "in_target_scope"}:
        return "in_target"
    if status in {"outside_target_scope", "out_of_scope"}:
        return "outside_target"
    return "unknown"

def _scope_status_from_item_scope_fields(item: dict[str, Any]) -> str:
    scope_id = _normalized_scope_id(item.get("scope_id"))
    in_target_scope = _normalized_in_target_scope(item.get("in_target_scope"))
    if scope_id == "target_scope" or in_target_scope is True:
        return "in_target"
    if scope_id == "outside_target_scope" or in_target_scope is False:
        return "outside_target"
    return "unknown"

def _normalize_scope_proof_codes(raw_scope_proof: Any) -> list[str]:
    codes: list[str] = []
    for entry in list(raw_scope_proof or []):
        code = str(entry or "").strip().lower()
        if code not in _APPROVED_SCOPE_PROOF_CODES:
            continue
        if code in codes:
            continue
        codes.append(code)
    return codes[:6]

def _merge_scope_proof_codes(base_codes: list[str], extra_codes: list[str]) -> list[str]:
    merged = list(base_codes)
    for code in extra_codes:
        normalized = str(code or "").strip().lower()
        if normalized not in _APPROVED_SCOPE_PROOF_CODES:
            continue
        if normalized in merged:
            continue
        merged.append(normalized)
    return merged[:6]

def _scope_proof_codes_from_signal(signal: dict[str, Any]) -> list[str]:
    if not isinstance(signal, dict):
        return []
    codes: list[str] = []
    if bool(signal.get("operator_marked_outside_target")):
        codes.append("operator_marked_outside_target")
    blob = " ".join(
        [
            str(signal.get("message") or ""),
            str(signal.get("reason") or ""),
            str(signal.get("query") or ""),
            str(signal.get("observed_text") or ""),
        ]
    ).lower()
    if "outside target" in blob or "outside target scope" in blob:
        codes.append("explicit_outside_target_text")
    if "truncation boundary" in blob or "cutoff boundary" in blob or "post-target cutoff" in blob:
        codes.append("source_truncation_boundary")
    if (
        str(signal.get("status") or "").strip().lower() in _CONFIRMED_STATUSES
        and ("post-target cutoff" in blob or "after target cutoff" in blob)
    ):
        codes.append("image_confirms_post_target_cutoff")
    return _normalize_scope_proof_codes(codes)

def _read_scope_priority(raw_scope_priority: Any) -> int:
    try:
        value = int(raw_scope_priority)
    except Exception:
        value = 50
    return max(0, min(100, value))

def _scope_label(scope_id: str) -> str:
    normalized = _normalized_scope_id(scope_id)
    if normalized == "target_scope":
        return "Target Scope"
    if normalized == "outside_target_scope":
        return "Outside Target Scope"
    return "Unknown Scope"

def _scope_rank(scope_id: str) -> int:
    normalized = _normalized_scope_id(scope_id)
    if normalized == "target_scope":
        return 0
    if normalized == "unknown_scope":
        return 1
    return 2

def _scope_id_for_item(item: dict[str, Any]) -> str:
    scope_id = _normalized_scope_id(item.get("scope_id"))
    if scope_id != "unknown_scope":
        if scope_id == "outside_target_scope" and not _normalize_scope_proof_codes(item.get("scope_proof")):
            return "unknown_scope"
        return scope_id
    in_target_scope = item.get("in_target_scope")
    if in_target_scope is True:
        return "target_scope"
    if in_target_scope is False:
        if _normalize_scope_proof_codes(item.get("scope_proof")):
            return "outside_target_scope"
        return "unknown_scope"
    return "unknown_scope"

def _normalized_in_target_scope(raw_value: Any) -> bool | None:
    if isinstance(raw_value, bool):
        return raw_value
    text = str(raw_value or "").strip().lower()
    if text in {"true", "yes", "target_scope"}:
        return True
    if text in {"false", "no", "outside_target_scope"}:
        return False
    return None

def _apply_scope_from_signal(*, item: dict[str, Any], signal: dict[str, Any]) -> None:
    if not isinstance(item, dict) or not isinstance(signal, dict):
        return
    proof_codes = _normalize_scope_proof_codes(signal.get("scope_proof"))
    proof_codes = _merge_scope_proof_codes(
        proof_codes,
        _scope_proof_codes_from_signal(signal),
    )
    explicit_scope_status = _normalize_scope_status(signal.get("scope_status"))
    explicit_scope_id = _normalized_scope_id(signal.get("scope_id"))
    in_target_scope = _normalized_in_target_scope(signal.get("in_target_scope"))
    scope_status = "unknown"
    if explicit_scope_status in _SCOPE_STATUS_VALUES:
        scope_status = explicit_scope_status
    elif explicit_scope_id in {"target_scope", "outside_target_scope"}:
        scope_status = "in_target" if explicit_scope_id == "target_scope" else "outside_target"
    elif in_target_scope is not None:
        scope_status = "in_target" if in_target_scope else "outside_target"
    if scope_status == "outside_target" and not proof_codes:
        scope_status = "unknown"
    if scope_status == "unknown" and proof_codes:
        if any(
            code in proof_codes
            for code in {
                "explicit_outside_target_text",
                "image_confirms_post_target_cutoff",
                "operator_marked_outside_target",
                "source_truncation_boundary",
            }
        ):
            scope_status = "outside_target"
    if scope_status == "outside_target":
        item["scope_id"] = "outside_target_scope"
        item["scope_label"] = str(signal.get("scope_label") or "Outside Target Scope")
        item["scope_priority"] = _read_scope_priority(
            signal.get("scope_priority")
            if signal.get("scope_priority") is not None
            else 80
        )
        item["in_target_scope"] = False
        item["scope_proof"] = proof_codes
        return
    if scope_status == "in_target":
        item["scope_id"] = "target_scope"
        item["scope_label"] = str(signal.get("scope_label") or "Target Scope")
        item["scope_priority"] = _read_scope_priority(
            signal.get("scope_priority")
            if signal.get("scope_priority") is not None
            else 0
        )
        item["in_target_scope"] = True
        item["scope_proof"] = []

def _apply_scope_defaults(items: list[dict[str, Any]]) -> None:
    for item in items:
        if not isinstance(item, dict):
            continue
        scope_id = _scope_id_for_item(item)
        scope_proof = _normalize_scope_proof_codes(item.get("scope_proof"))
        if scope_id == "outside_target_scope" and not scope_proof:
            scope_id = "unknown_scope"
        item["scope_id"] = scope_id
        item["scope_label"] = str(item.get("scope_label") or _scope_label(scope_id))
        item["scope_proof"] = scope_proof if scope_id == "outside_target_scope" else []
        priority_default = 0 if scope_id == "target_scope" else 80 if scope_id == "outside_target_scope" else 50
        item["scope_priority"] = _read_scope_priority(
            item.get("scope_priority") if item.get("scope_priority") is not None else priority_default
        )
        if item.get("in_target_scope") is None:
            if scope_id == "target_scope":
                item["in_target_scope"] = True
            elif scope_id == "outside_target_scope":
                item["in_target_scope"] = False
            else:
                item["in_target_scope"] = None

def _extract_source_completeness_signal(signal: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(signal, dict):
        return None
    explicit = str(signal.get("source_completeness") or "").strip().lower()
    if explicit in _SOURCE_COMPLETENESS_VALUES:
        limitations = [
            str(v).strip()
            for v in list(signal.get("source_limitations") or [])
            if str(v).strip()
        ][:6]
        return {
            "source_completeness": explicit,
            "reason": str(signal.get("source_completeness_reason") or "").strip() or None,
            "limitations": limitations,
        }

    blob = " ".join(
        [
            str(signal.get("message") or ""),
            str(signal.get("reason") or ""),
            str(signal.get("query") or ""),
            str(signal.get("observed_text") or ""),
            str(signal.get("retrieval_blocker") or ""),
        ]
    ).lower()
    if any(
        token in blob
        for token in {
            "truncated",
            "cut off",
            "cropped",
            "image ends",
            "missing lower",
            "below visible",
            "not visible in source",
        }
    ):
        return {
            "source_completeness": "partial_truncated",
            "reason": "Source image appears truncated or cut off.",
            "limitations": ["Source content appears cut off; lower-page context is unavailable."],
        }
    if any(
        token in blob
        for token in {
            "missing context",
            "context unavailable",
            "referenced record unavailable",
            "external dependency not available",
            "dependency missing",
        }
    ):
        return {
            "source_completeness": "partial_missing_context",
            "reason": "Required context is missing from the available source set.",
            "limitations": ["Missing context prevents full-document closure."],
        }
    return None

def _merge_source_completeness_signal(
    *,
    source_completeness: str,
    source_completeness_reason: str | None,
    source_limitations: list[str],
    signal: dict[str, Any] | None,
) -> tuple[str, str | None, list[str]]:
    if not isinstance(signal, dict):
        return source_completeness, source_completeness_reason, source_limitations
    incoming = str(signal.get("source_completeness") or "").strip().lower()
    if incoming not in _SOURCE_COMPLETENESS_VALUES:
        return source_completeness, source_completeness_reason, source_limitations
    priority = {"unknown": 0, "complete": 1, "partial_missing_context": 2, "partial_truncated": 3}
    current_priority = priority.get(source_completeness, 0)
    incoming_priority = priority.get(incoming, 0)
    merged = source_completeness
    if incoming_priority >= current_priority:
        merged = incoming
    merged_reason = source_completeness_reason
    incoming_reason = str(signal.get("reason") or "").strip() or None
    if incoming_reason and merged == incoming:
        merged_reason = incoming_reason
    limitations = list(source_limitations)
    for limitation in list(signal.get("limitations") or []):
        text = str(limitation).strip()
        if not text:
            continue
        if text in limitations:
            continue
        limitations.append(text)
    return merged, merged_reason, limitations[:12]

def _compute_scope_summaries(ledger: dict[str, Any]) -> dict[str, Any]:
    items = ledger.get("items") if isinstance(ledger, dict) else []
    if not isinstance(items, list):
        return {}
    source_completeness = str(ledger.get("source_completeness") or "unknown").strip().lower()
    rows: dict[str, dict[str, Any]] = {
        "target_scope": {"scope_id": "target_scope", "scope_label": "Target Scope", "scope_closure_state": "not_attempted", "unresolved_count": 0, "mapping_blocking_unresolved_count": 0, "resolved_count": 0},
        "outside_target_scope": {"scope_id": "outside_target_scope", "scope_label": "Outside Target Scope", "scope_closure_state": "not_attempted", "unresolved_count": 0, "mapping_blocking_unresolved_count": 0, "resolved_count": 0},
        "unknown_scope": {"scope_id": "unknown_scope", "scope_label": "Unknown Scope", "scope_closure_state": "not_attempted", "unresolved_count": 0, "mapping_blocking_unresolved_count": 0, "resolved_count": 0},
    }
    for item in items:
        if not isinstance(item, dict):
            continue
        requirement = item.get("closure_requirement") if isinstance(item.get("closure_requirement"), dict) else {}
        scope_status = _normalize_scope_status(requirement.get("scope_status"))
        if scope_status == "unknown":
            scope_status = _scope_status_from_item_scope_fields(item)
        state = str(item.get("state") or "unknown").strip().lower()
        if (
            scope_status == "unknown"
            and state not in _UNRESOLVED_STATES
            and bool(item.get("blocking"))
            and len([str(v).strip() for v in list(item.get("evidence_refs") or []) if str(v).strip()]) > 0
        ):
            scope_status = "in_target"
        scope_proof = _normalize_scope_proof_codes(requirement.get("scope_proof"))
        if not scope_proof:
            scope_proof = _normalize_scope_proof_codes(item.get("scope_proof"))
        if scope_status == "outside_target" and not scope_proof:
            scope_status = "unknown"
        scope_id = _scope_id_from_scope_status(scope_status)
        row = rows.get(scope_id)
        if not isinstance(row, dict):
            continue
        unresolved = state in _UNRESOLVED_STATES
        if unresolved:
            row["unresolved_count"] = int(row["unresolved_count"]) + 1
        else:
            row["resolved_count"] = int(row["resolved_count"]) + 1
        if unresolved and bool(item.get("blocking")):
            row["mapping_blocking_unresolved_count"] = int(row["mapping_blocking_unresolved_count"]) + 1
    for scope_id, row in rows.items():
        unresolved_count = int(row.get("unresolved_count") or 0)
        mapping_unresolved = int(row.get("mapping_blocking_unresolved_count") or 0)
        resolved_count = int(row.get("resolved_count") or 0)
        if unresolved_count <= 0 and resolved_count <= 0:
            scope_state = "not_attempted"
        elif mapping_unresolved > 0:
            if scope_id == "outside_target_scope" and source_completeness in {"partial_truncated", "partial_missing_context"}:
                scope_state = "partial"
            else:
                scope_state = "blocked"
        elif unresolved_count > 0:
            scope_state = "partial"
        else:
            scope_state = "achieved"
        if scope_state not in _SCOPE_CLOSURE_STATE_VALUES:
            scope_state = "partial"
        row["scope_closure_state"] = scope_state
    return rows
