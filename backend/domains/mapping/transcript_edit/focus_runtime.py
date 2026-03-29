from __future__ import annotations

from typing import Any


def select_focus_decision_key(
    *,
    decision_ledger: dict[str, Any],
    fallback_focus: dict[str, Any] | None,
    focus_feedback: dict[str, Any] | None,
    blocker_registry: dict[str, Any] | None,
    select_focus_target_fn,
) -> str:
    selected = select_focus_target_fn(
        decision_ledger=decision_ledger,
        fallback_focus=fallback_focus,
        focus_feedback=focus_feedback,
        blocker_registry=blocker_registry,
    )
    return str((selected or {}).get("decision_key") or "").strip().lower()


def findings_for_focus_key(*, top_findings: list[dict[str, Any]], focus_key: str) -> list[dict[str, Any]]:
    key = str(focus_key or "").strip().lower()
    if not key:
        return []
    focused: list[dict[str, Any]] = []
    for finding in top_findings:
        if not isinstance(finding, dict):
            continue
        inferred_key = decision_key_for_finding(finding)
        if inferred_key == key:
            focused.append(finding)
    return focused


_KNOWN_DECISION_KEYS = frozenset(
    {
        "range",
        "township",
        "section",
        "tie_distance",
        "tie_bearing",
        "acreage",
        "closure_or_pob",
    }
)


def decision_key_for_finding(finding: dict[str, Any]) -> str:
    """Infer a seed decision key from evidence-shaped rows (message / optional explicit keys only)."""
    if not isinstance(finding, dict):
        return ""
    for k in ("suggested_decision_key", "decision_key", "target_decision_key"):
        raw = str(finding.get(k) or "").strip().lower()
        if raw in _KNOWN_DECISION_KEYS:
            return raw
    message = str(finding.get("message") or "").strip().lower()
    if "bearing" in message:
        return "tie_bearing"
    if "distance" in message or "tie distance" in message:
        return "tie_distance"
    if "acre" in message:
        return "acreage"
    if "point of beginning" in message or "pob" in message or "closure" in message:
        return "closure_or_pob"
    if "township" in message:
        return "township"
    if "section" in message:
        return "section"
    if "range" in message:
        return "range"
    return ""


def conflict_map_from_ledger(ledger: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(ledger, dict):
        return []
    items = ledger.get("items")
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        alternatives = [str(v).strip() for v in list(item.get("alternatives") or []) if str(v).strip()]
        if len(alternatives) < 2:
            continue
        state = str(item.get("state") or "").strip().lower()
        if state not in {"disputed", "accepted_with_risk", "candidate_found", "unknown"}:
            continue
        out.append(
            {
                "decision_key": str(item.get("key") or ""),
                "values": alternatives[:6],
                "conflict": True,
            }
        )
    return out


def baseline_residual_from_unresolved(item: dict[str, Any]) -> dict[str, Any]:
    requirement = item.get("closure_requirement") if isinstance(item.get("closure_requirement"), dict) else {}
    return {
        "decision_key": str(item.get("key") or ""),
        "label": str(item.get("label") or item.get("key") or "decision"),
        "state": str(item.get("state") or "unknown"),
        "mapping_blocking": bool(item.get("mapping_blocking")),
        "scope_id": str(item.get("scope_id") or "unknown_scope"),
        "scope_label": str(item.get("scope_label") or "Unknown Scope"),
        "scope_priority": int(item.get("scope_priority") or 50),
        "in_target_scope": bool(item.get("in_target_scope")),
        "scope_status": str(item.get("scope_status") or "unknown"),
        "scope_proof": [str(v) for v in list(item.get("scope_proof") or []) if str(v).strip()][:6],
        "incomplete_source_residual": bool(item.get("incomplete_source_residual")),
        "required_information": str(requirement.get("required_information") or "").strip(),
        "minimal_user_action": str(requirement.get("minimal_user_action") or "").strip(),
    }


def baseline_evidence_attempts(
    *,
    span_context: list[dict[str, Any]],
    image_verification: dict[str, Any],
) -> list[dict[str, Any]]:
    image_payload = image_verification.get("payload") if isinstance(image_verification, dict) else {}
    image_results = image_payload.get("results") if isinstance(image_payload, dict) else []
    image_count = len(image_results) if isinstance(image_results, list) else 0
    return [
        {
            "attempt": "open_spans",
            "status": "completed",
            "result_count": len(span_context),
        },
        {
            "attempt": "image_verify",
            "status": "completed" if image_count > 0 else "attempted",
            "result_count": image_count,
        },
    ]


def next_recommended_action_text(residual_blockers: list[dict[str, Any]]) -> str:
    if not residual_blockers:
        return "Proceed with plan/apply stage."
    prioritized = sorted(
        [item for item in residual_blockers if isinstance(item, dict)],
        key=lambda item: (
            0
            if str(item.get("scope_status") or "").strip().lower() == "in_target"
            else 1
            if str(item.get("scope_status") or "").strip().lower() == "unknown"
            else 2,
            int(item.get("scope_priority") or 50),
        ),
    )
    for item in prioritized:
        if not bool(item.get("mapping_blocking")):
            continue
        label = str(item.get("label") or item.get("decision_key") or "decision")
        action = str(item.get("minimal_user_action") or item.get("required_information") or "").strip()
        if action:
            return f"{label}: {action}"
        return f"Resolve {label}."
    first = prioritized[0] if prioritized else {}
    label = str(first.get("label") or first.get("decision_key") or "decision")
    return f"Review optional transcript-quality issue: {label}."


def recent_image_evidence_attempt_count(
    *,
    continuity_log: list[dict[str, Any]],
    decision_key: str | None,
    window: int = 8,
) -> int:
    key = str(decision_key or "").strip().lower()
    if not key or not isinstance(continuity_log, list):
        return 0
    bounded = [row for row in continuity_log[-max(1, int(window)) :] if isinstance(row, dict)]
    count = 0
    for row in bounded:
        if str(row.get("decision_key") or "").strip().lower() != key:
            continue
        if str(row.get("move") or "").strip().lower() != "gather_more_evidence":
            continue
        evidence_kind = str(row.get("evidence_kind") or "").strip().lower()
        if evidence_kind.startswith("image_evidence"):
            count += 1
    return count


def registry_row_for_decision_key(
    *,
    registry: dict[str, Any] | None,
    decision_key: str | None,
) -> dict[str, Any] | None:
    if not isinstance(registry, dict):
        return None
    key = str(decision_key or "").strip().lower()
    if not key:
        return None
    rows = [row for row in list(registry.get("rows") or []) if isinstance(row, dict)]
    matches = [
        row
        for row in rows
        if str(row.get("decision_key") or "").strip().lower() == key
    ]
    if not matches:
        return None
    matches.sort(
        key=lambda row: int(row.get("updated_at") or row.get("created_at") or 0),
        reverse=True,
    )
    return dict(matches[0])
