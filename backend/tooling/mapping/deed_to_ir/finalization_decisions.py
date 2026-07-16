"""Compact finalization decision validation, merge, and prepare-contract conversion.

Validates agent-authored compact maps against the stored session requirements,
merges accepted values, and converts complete decisions into the existing
intent-first prepare inputs. Does not persist sessions or call prepare/publish.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from domains.mapping.deed_to_ir.payloads.published_output import ALLOWED_CLOSURE_DIMENSION_IDS

from .finalization_session import (
    ALLOWED_CORRECTION_DISPOSITIONS,
    ALLOWED_DEPENDENCY_DISPOSITIONS,
    ALLOWED_SCOPE_STATUSES,
    MAX_RATIONALE_CHARS,
    compute_missing_finalization_ids,
    empty_finalization_decisions,
    session_requirement_ids,
)
from .persistence_io import retryable_refusal

REASON_UNKNOWN_ID = "finalization_decision_unknown_id"
REASON_INVALID = "finalization_decision_invalid"
REASON_SCOPE_DEPENDENCY_CONFLICT = "finalization_scope_dependency_conflict"
REASON_SESSION_INVALID = "finalization_session_invalid"

_DECISION_LANES = (
    "scope_statuses",
    "correction_dispositions",
    "dependency_dispositions",
    "rationales",
)


def decision_maps_nonempty(request: Mapping[str, Any] | None) -> bool:
    """True when any compact decision map carries at least one entry."""
    if not isinstance(request, Mapping):
        return False
    for key in _DECISION_LANES:
        raw = request.get(key)
        if isinstance(raw, Mapping) and raw:
            return True
    return False


def validate_decision_map_shapes(request: Mapping[str, Any] | None) -> dict[str, Any]:
    """Absent/None and object maps are valid; lists/scalars/strings are invalid."""
    if request is None:
        return {"ok": True}
    if not isinstance(request, Mapping):
        return retryable_refusal(
            REASON_INVALID,
            "Finalization decision request must be an object of optional decision maps.",
        )
    for key in _DECISION_LANES:
        if key not in request:
            continue
        raw = request.get(key)
        if raw is None:
            continue
        if not isinstance(raw, Mapping):
            return retryable_refusal(
                REASON_INVALID,
                f"{key} must be an object map of known IDs to allowed values.",
            )
    return {"ok": True}


def validate_persisted_finalization_decisions(
    session: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate stored decision lanes before merging new agent input.

    Corrupted or prior-version values refuse with finalization_session_invalid
    so remap can replace the session. Does not prepare or publish.
    """
    decisions = session.get("decisions")
    if decisions is None:
        return {"ok": True}
    if not isinstance(decisions, Mapping):
        return retryable_refusal(
            REASON_SESSION_INVALID,
            "Persisted finalization decisions are malformed. Remap the latest IR "
            "to replace the session, then retry.",
        )

    known = session_requirement_ids(session)
    scope_ids = set(known["scope_ids"])
    correction_ids = set(known["correction_ids"])
    dependency_ids = set(known["dependency_ids"])
    rationale_ids = scope_ids | correction_ids | dependency_ids

    for lane, known_ids, allowed in (
        ("scope_statuses", scope_ids, set(ALLOWED_SCOPE_STATUSES)),
        ("correction_dispositions", correction_ids, set(ALLOWED_CORRECTION_DISPOSITIONS)),
        ("dependency_dispositions", dependency_ids, set(ALLOWED_DEPENDENCY_DISPOSITIONS)),
    ):
        if lane not in decisions:
            continue
        raw = decisions.get(lane)
        if not isinstance(raw, Mapping):
            return retryable_refusal(
                REASON_SESSION_INVALID,
                f"Persisted {lane} lane is malformed. Remap the latest IR to replace "
                "the session, then retry.",
            )
        for key, value in raw.items():
            kid = str(key or "").strip()
            if not kid or kid not in known_ids:
                return retryable_refusal(
                    REASON_SESSION_INVALID,
                    f"Persisted {lane} contains unknown id {key!r}. Remap the latest IR "
                    "to replace the session, then retry.",
                )
            text = str(value or "").strip() if isinstance(value, str) else ""
            if not isinstance(value, str) or text not in allowed:
                return retryable_refusal(
                    REASON_SESSION_INVALID,
                    f"Persisted {lane} has invalid value for {kid}. Remap the latest IR "
                    "to replace the session, then retry.",
                )

    if "rationales" in decisions:
        raw_rationales = decisions.get("rationales")
        if not isinstance(raw_rationales, Mapping):
            return retryable_refusal(
                REASON_SESSION_INVALID,
                "Persisted rationales lane is malformed. Remap the latest IR to replace "
                "the session, then retry.",
            )
        for key, value in raw_rationales.items():
            kid = str(key or "").strip()
            if not kid or kid not in rationale_ids:
                return retryable_refusal(
                    REASON_SESSION_INVALID,
                    f"Persisted rationales contains unknown id {key!r}. Remap the latest IR "
                    "to replace the session, then retry.",
                )
            if not isinstance(value, str):
                return retryable_refusal(
                    REASON_SESSION_INVALID,
                    f"Persisted rationale for {kid} is not a string. Remap the latest IR "
                    "to replace the session, then retry.",
                )
            text = value.strip()
            if not text or len(text) > MAX_RATIONALE_CHARS:
                return retryable_refusal(
                    REASON_SESSION_INVALID,
                    f"Persisted rationale for {kid} is empty or exceeds the length bound. "
                    "Remap the latest IR to replace the session, then retry.",
                )

    return {"ok": True}


def validate_compact_finalization_decisions(
    *,
    session: Mapping[str, Any],
    request: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate the entire compact request before any session mutation.

    Returns ``{"ok": True, "incoming": {...}}`` or a refusal payload.
    """
    req = request if isinstance(request, Mapping) else {}
    known = session_requirement_ids(session)
    scope_ids = set(known["scope_ids"])
    correction_ids = set(known["correction_ids"])
    dependency_ids = set(known["dependency_ids"])
    rationale_ids = scope_ids | correction_ids | dependency_ids

    incoming = empty_finalization_decisions()

    scope_result = _validate_string_map(
        req.get("scope_statuses"),
        field="scope_statuses",
        known_ids=scope_ids,
        allowed_values=set(ALLOWED_SCOPE_STATUSES),
    )
    if scope_result.get("executed") is False:
        return scope_result
    incoming["scope_statuses"] = scope_result["values"]

    correction_result = _validate_string_map(
        req.get("correction_dispositions"),
        field="correction_dispositions",
        known_ids=correction_ids,
        allowed_values=set(ALLOWED_CORRECTION_DISPOSITIONS),
    )
    if correction_result.get("executed") is False:
        return correction_result
    incoming["correction_dispositions"] = correction_result["values"]

    dependency_result = _validate_string_map(
        req.get("dependency_dispositions"),
        field="dependency_dispositions",
        known_ids=dependency_ids,
        allowed_values=set(ALLOWED_DEPENDENCY_DISPOSITIONS),
    )
    if dependency_result.get("executed") is False:
        return dependency_result
    incoming["dependency_dispositions"] = dependency_result["values"]

    rationale_result = _validate_rationale_map(
        req.get("rationales"),
        known_ids=rationale_ids,
    )
    if rationale_result.get("executed") is False:
        return rationale_result
    incoming["rationales"] = rationale_result["values"]

    return {"ok": True, "incoming": incoming}


def merge_finalization_decisions(
    *,
    session: Mapping[str, Any],
    incoming: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge validated incoming maps into a session copy (pending only)."""
    merged = dict(session)
    existing = (
        session.get("decisions") if isinstance(session.get("decisions"), Mapping) else {}
    )
    decisions = empty_finalization_decisions()
    for lane in _DECISION_LANES:
        base = existing.get(lane) if isinstance(existing.get(lane), Mapping) else {}
        patch = incoming.get(lane) if isinstance(incoming.get(lane), Mapping) else {}
        combined = {str(k): str(v) for k, v in dict(base).items()}
        combined.update({str(k): str(v) for k, v in dict(patch).items()})
        decisions[lane] = combined
    merged["decisions"] = decisions
    return merged


def evaluate_merged_finalization_completeness(
    session: Mapping[str, Any],
) -> dict[str, Any]:
    """Return missing IDs / HITL flag for a merged pending session."""
    known = session_requirement_ids(session)
    decisions = session.get("decisions") if isinstance(session.get("decisions"), Mapping) else {}
    scope_statuses = _as_str_map(decisions.get("scope_statuses"))
    correction_dispositions = _as_str_map(decisions.get("correction_dispositions"))
    dependency_dispositions = _as_str_map(decisions.get("dependency_dispositions"))
    rationales = _as_str_map(decisions.get("rationales"))
    missing = compute_missing_finalization_ids(
        scope_ids=known["scope_ids"],
        correction_ids=known["correction_ids"],
        dependency_ids=known["dependency_ids"],
        scope_statuses=scope_statuses,
        correction_dispositions=correction_dispositions,
        dependency_dispositions=dependency_dispositions,
        rationales=rationales,
    )
    needs_hitl = any(value == "needs_hitl" for value in correction_dispositions.values())
    complete = not any(missing.values())
    return {
        "complete": complete,
        "missing": missing,
        "needs_hitl": needs_hitl,
        "scope_statuses": scope_statuses,
        "correction_dispositions": correction_dispositions,
        "dependency_dispositions": dependency_dispositions,
        "rationales": rationales,
    }


def convert_compact_decisions_to_prepare_inputs(
    *,
    session: Mapping[str, Any],
    scope_statuses: Mapping[str, str],
    correction_dispositions: Mapping[str, str],
    dependency_dispositions: Mapping[str, str],
    rationales: Mapping[str, str],
) -> dict[str, Any]:
    """Convert compact session decisions into intent-first prepare inputs.

    Returns ``{"ok": True, ...}`` or a refusal (scope/dependency conflict).
    """
    requirements = (
        session.get("requirements") if isinstance(session.get("requirements"), Mapping) else {}
    )
    correction_candidates = list(requirements.get("correction_candidates") or [])
    dependency_candidates = list(requirements.get("dependency_candidates") or [])
    candidates_by_id = {
        str(row.get("candidate_id") or "").strip(): row
        for row in dependency_candidates
        if isinstance(row, Mapping) and str(row.get("candidate_id") or "").strip()
    }
    corrections_by_id = {
        str(row.get("target_entity_id") or "").strip(): row
        for row in correction_candidates
        if isinstance(row, Mapping) and str(row.get("target_entity_id") or "").strip()
    }

    for dep_id, disposition in dependency_dispositions.items():
        if disposition != "include":
            continue
        candidate = candidates_by_id.get(dep_id)
        if not isinstance(candidate, Mapping):
            continue
        affected = str(candidate.get("affected_scope") or "").strip()
        if not affected:
            continue
        if scope_statuses.get(affected) != "blocked":
            return retryable_refusal(
                REASON_SCOPE_DEPENDENCY_CONFLICT,
                (
                    f"Included dependency {dep_id} affects scope {affected}, which must be "
                    "blocked when the dependency is included."
                ),
            )

    scope_dispositions = [
        {"scope_id": scope_id, "status": status}
        for scope_id, status in scope_statuses.items()
    ]
    closure_dispositions = [
        {"dimension_id": dimension_id, "status": "closed"}
        for dimension_id in sorted(ALLOWED_CLOSURE_DIMENSION_IDS)
    ]

    correction_decisions: list[dict[str, Any]] = []
    for target_id, disposition in correction_dispositions.items():
        if disposition == "needs_hitl":
            continue
        candidate = corrections_by_id.get(target_id) or {}
        if disposition == "confirmed_source_repair":
            correction_decisions.append(
                {
                    "target_entity_id": target_id,
                    "posture": "confirmed_from_source",
                    "resolution_used_by_ir": True,
                    "recommended_action": "transcript_amendment",
                    "rationale": _canonical_confirmed_source_repair_rationale(
                        target_id=target_id,
                        candidate=candidate if isinstance(candidate, Mapping) else {},
                    ),
                }
            )
        elif disposition == "ir_only_exception":
            correction_decisions.append(
                {
                    "target_entity_id": target_id,
                    "posture": "suspected",
                    "resolution_used_by_ir": True,
                    "recommended_action": "ir_only_note",
                    "rationale": str(rationales.get(target_id) or "").strip(),
                }
            )

    dependency_decisions: list[dict[str, Any]] = []
    for dep_id, disposition in dependency_dispositions.items():
        if disposition == "include":
            dependency_decisions.append(
                {
                    "candidate_id": dep_id,
                    "disposition": "include",
                    "status": "blocked",
                }
            )
        elif disposition == "not_applicable":
            dependency_decisions.append(
                {
                    "candidate_id": dep_id,
                    "disposition": "not_applicable",
                    "rationale": str(rationales.get(dep_id) or "").strip(),
                }
            )

    return {
        "ok": True,
        "scope_dispositions": scope_dispositions,
        "closure_dispositions": closure_dispositions,
        "correction_decisions": correction_decisions,
        "dependency_decisions": dependency_decisions,
    }


def _canonical_confirmed_source_repair_rationale(
    *,
    target_id: str,
    candidate: Mapping[str, Any],
) -> str:
    inherited = candidate.get("inherited_value")
    selected = candidate.get("selected_ir_display_value")
    inherited_text = str(inherited).strip() if inherited is not None else ""
    selected_text = str(selected).strip() if selected is not None else ""
    if inherited_text and selected_text:
        return (
            f"Agent accepted the current IR value ({selected_text}) as a "
            f"source-confirmed repair of the inherited value ({inherited_text}) "
            f"for {target_id}."
        )
    return (
        f"Agent accepted the current IR value as a source-confirmed repair of the "
        f"inherited value for {target_id}."
    )


def _validate_string_map(
    raw: Any,
    *,
    field: str,
    known_ids: set[str],
    allowed_values: set[str],
) -> dict[str, Any]:
    if raw is None:
        return {"ok": True, "values": {}}
    if not isinstance(raw, Mapping):
        return retryable_refusal(
            REASON_INVALID,
            f"{field} must be an object map of known IDs to allowed values.",
        )
    values: dict[str, str] = {}
    for key, value in raw.items():
        kid = str(key or "").strip()
        if not kid or kid not in known_ids:
            return retryable_refusal(
                REASON_UNKNOWN_ID,
                f"Unknown {field} id: {key!r}.",
            )
        text = str(value or "").strip()
        if text not in allowed_values:
            return retryable_refusal(
                REASON_INVALID,
                f"Invalid {field} value for {kid}: {value!r}.",
            )
        values[kid] = text
    return {"ok": True, "values": values}


def _validate_rationale_map(
    raw: Any,
    *,
    known_ids: set[str],
) -> dict[str, Any]:
    if raw is None:
        return {"ok": True, "values": {}}
    if not isinstance(raw, Mapping):
        return retryable_refusal(
            REASON_INVALID,
            "rationales must be an object map of known requirement IDs to rationale text.",
        )
    values: dict[str, str] = {}
    for key, value in raw.items():
        kid = str(key or "").strip()
        if not kid or kid not in known_ids:
            return retryable_refusal(
                REASON_UNKNOWN_ID,
                f"Unknown rationales id: {key!r}.",
            )
        if not isinstance(value, str):
            return retryable_refusal(
                REASON_INVALID,
                f"Invalid rationale for {kid}: rationale must be a string.",
            )
        text = value.strip()
        if not text:
            return retryable_refusal(
                REASON_INVALID,
                f"Invalid rationale for {kid}: rationale must be non-empty.",
            )
        if len(text) > MAX_RATIONALE_CHARS:
            return retryable_refusal(
                REASON_INVALID,
                f"Invalid rationale for {kid}: exceeds {MAX_RATIONALE_CHARS} characters.",
            )
        values[kid] = text
    return {"ok": True, "values": values}


def _as_str_map(raw: Any) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(key).strip(): str(value).strip()
        for key, value in raw.items()
        if str(key or "").strip() and str(value or "").strip()
    }
