"""Deed-to-IR finalization session payload/model (domain-owned).

Defines the canonical pending-finalization shape and bounded prompt compaction.
Deterministic code never invents scope IDs, statuses, or decision defaults.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from domains.mapping.deed_to_ir.payloads.finalization_vocabulary import (
    ALLOWED_CORRECTION_DISPOSITIONS,
    ALLOWED_DEPENDENCY_DISPOSITIONS,
    ALLOWED_SCOPE_STATUSES,
)
from domains.mapping.deed_to_ir.payloads.published_output import (
    MAX_EXTERNAL_DEPENDENCIES,
    MAX_RATIONALE_LENGTH,
    MAX_SCOPE_RESULTS,
    MAX_UPSTREAM_CORRECTIONS,
)

SCHEMA_VERSION = "deed_to_ir.finalization_session.v1"
STATUS_PENDING_DECISIONS = "pending_decisions"
STATUS_PREVIEW_READY = "preview_ready"
STATUS_PUBLISHED = "published"
STATUS_STALE = "stale"
STALE_REASON_IR_REVISION_WITHOUT_REMAP = "ir_revision_without_remap"
SCOPE_INVENTORY_UNAVAILABLE = "scope_inventory_unavailable"
REQUIREMENTS_CAPACITY_EXCEEDED = "finalization_requirements_capacity_exceeded"

ACTIVE_FINALIZATION_STATUSES = frozenset(
    {STATUS_PENDING_DECISIONS, STATUS_PREVIEW_READY, STATUS_PUBLISHED}
)

MAX_SCOPE_REQUIREMENTS = MAX_SCOPE_RESULTS
MAX_CORRECTION_REQUIREMENTS = MAX_UPSTREAM_CORRECTIONS
MAX_DEPENDENCY_REQUIREMENTS = MAX_EXTERNAL_DEPENDENCIES
MAX_RATIONALE_CHARS = MAX_RATIONALE_LENGTH

_MAX_BASIS_REFS = 8
_MAX_DIAGNOSTICS = 16
_MAX_OBSERVED_SCOPE_IDS = MAX_SCOPE_REQUIREMENTS


def empty_finalization_decisions() -> dict[str, Any]:
    """Decision maps begin empty — no semantic defaults."""
    return {
        "scope_statuses": {},
        "correction_dispositions": {},
        "dependency_dispositions": {},
        "rationales": {},
    }


def build_pending_finalization_session(
    *,
    mapping_artifact_ref: str,
    source_ir_artifact_ref: str,
    scope_ids: Sequence[str],
    correction_candidates: Sequence[Mapping[str, Any]] | None = None,
    dependency_candidates: Sequence[Mapping[str, Any]] | None = None,
    diagnostics: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a fresh pending session bound to one mapping/IR lineage."""
    mapping_ref = str(mapping_artifact_ref or "").strip()
    ir_ref = str(source_ir_artifact_ref or "").strip()

    capacity_diagnostics: list[dict[str, Any]] = []
    bounded_scopes = _bound_requirement_lane(
        [str(item).strip() for item in scope_ids if str(item or "").strip()],
        lane="scope_ids",
        maximum=MAX_SCOPE_REQUIREMENTS,
        diagnostics=capacity_diagnostics,
    )
    bounded_corrections = _bound_requirement_lane(
        _compact_correction_requirements(correction_candidates),
        lane="correction_candidates",
        maximum=MAX_CORRECTION_REQUIREMENTS,
        diagnostics=capacity_diagnostics,
    )
    bounded_dependencies = _bound_requirement_lane(
        _compact_dependency_requirements(dependency_candidates),
        lane="dependency_candidates",
        maximum=MAX_DEPENDENCY_REQUIREMENTS,
        diagnostics=capacity_diagnostics,
    )

    merged_diagnostics = [
        *capacity_diagnostics,
        *(list(diagnostics) if isinstance(diagnostics, list) else []),
    ]

    session: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": STATUS_PENDING_DECISIONS,
        "lineage": {
            "mapping_artifact_ref": mapping_ref,
            "source_ir_artifact_ref": ir_ref,
        },
        "requirements": {
            "scope_ids": bounded_scopes,
            "correction_candidates": bounded_corrections,
            "dependency_candidates": bounded_dependencies,
        },
        "decisions": empty_finalization_decisions(),
        "preview_ref": None,
        "output_revision_ref": None,
    }
    bounded_diagnostics = _compact_diagnostics(merged_diagnostics)
    if bounded_diagnostics:
        session["diagnostics"] = bounded_diagnostics
    return session


def mark_session_stale(
    session: Mapping[str, Any],
    *,
    new_ir_artifact_ref: str,
) -> dict[str, Any]:
    """Copy a session as stale after a newer IR write (no decision migration)."""
    stale = dict(session)
    stale["status"] = STATUS_STALE
    stale["stale"] = True
    stale["stale_reason"] = STALE_REASON_IR_REVISION_WITHOUT_REMAP
    stale["superseded_by_ir_artifact_ref"] = str(new_ir_artifact_ref or "").strip()
    return stale


def compact_finalization_session_for_prompt(
    session: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Bounded active-session projection for per-turn prompt runtime.

    Pending: lineage, requirements, accepted decisions, missing IDs, allowed values.
    Preview-ready / published: status, refs, and next_required_action only.
    Stale sessions are excluded.
    """
    if not isinstance(session, Mapping) or not session:
        return None
    status = str(session.get("status") or "").strip()
    if status not in ACTIVE_FINALIZATION_STATUSES:
        return None

    if status == STATUS_PREVIEW_READY:
        preview_ref = str(session.get("preview_ref") or "").strip() or None
        return {
            "status": STATUS_PREVIEW_READY,
            "final_package_preview_ref": preview_ref,
            "next_required_action": "finalize_current_deed_to_ir_output",
        }

    if status == STATUS_PUBLISHED:
        return {
            "status": STATUS_PUBLISHED,
            "output_revision_ref": str(session.get("output_revision_ref") or "").strip() or None,
            "final_package_preview_ref": str(session.get("preview_ref") or "").strip() or None,
        }

    lineage = session.get("lineage") if isinstance(session.get("lineage"), Mapping) else {}
    decisions = session.get("decisions") if isinstance(session.get("decisions"), Mapping) else {}

    known = session_requirement_ids(session)
    scope_ids = list(known["scope_ids"])[:MAX_SCOPE_REQUIREMENTS]
    correction_ids = list(known["correction_ids"])[:MAX_CORRECTION_REQUIREMENTS]
    dependency_ids = list(known["dependency_ids"])[:MAX_DEPENDENCY_REQUIREMENTS]

    accepted_scopes = _accepted_decision_map(
        decisions.get("scope_statuses"),
        known_ids=set(scope_ids),
        allowed_values=ALLOWED_SCOPE_STATUSES,
        maximum=MAX_SCOPE_REQUIREMENTS,
    )
    accepted_corrections = _accepted_decision_map(
        decisions.get("correction_dispositions"),
        known_ids=set(correction_ids),
        allowed_values=ALLOWED_CORRECTION_DISPOSITIONS,
        maximum=MAX_CORRECTION_REQUIREMENTS,
    )
    accepted_dependencies = _accepted_decision_map(
        decisions.get("dependency_dispositions"),
        known_ids=set(dependency_ids),
        allowed_values=ALLOWED_DEPENDENCY_DISPOSITIONS,
        maximum=MAX_DEPENDENCY_REQUIREMENTS,
    )
    known_ids = set(scope_ids) | set(correction_ids) | set(dependency_ids)
    accepted_rationales = _accepted_rationales(
        decisions.get("rationales"),
        known_ids=known_ids,
        maximum=MAX_SCOPE_REQUIREMENTS
        + MAX_CORRECTION_REQUIREMENTS
        + MAX_DEPENDENCY_REQUIREMENTS,
    )

    missing = compute_missing_finalization_ids(
        scope_ids=scope_ids,
        correction_ids=correction_ids,
        dependency_ids=dependency_ids,
        scope_statuses=accepted_scopes,
        correction_dispositions=accepted_corrections,
        dependency_dispositions=accepted_dependencies,
        rationales=accepted_rationales,
    )

    compact: dict[str, Any] = {
        "status": STATUS_PENDING_DECISIONS,
        "lineage": {
            "mapping_artifact_ref": lineage.get("mapping_artifact_ref"),
            "source_ir_artifact_ref": lineage.get("source_ir_artifact_ref"),
        },
        "missing": missing,
        "allowed_values": {
            "scope_statuses": list(ALLOWED_SCOPE_STATUSES),
            "correction_dispositions": list(ALLOWED_CORRECTION_DISPOSITIONS),
            "dependency_dispositions": list(ALLOWED_DEPENDENCY_DISPOSITIONS),
        },
        "requirements": {
            "scope_ids": scope_ids,
            "correction_ids": correction_ids,
            "dependency_ids": dependency_ids,
        },
    }
    accepted: dict[str, Any] = {}
    if accepted_scopes:
        accepted["scope_statuses"] = accepted_scopes
    if accepted_corrections:
        accepted["correction_dispositions"] = accepted_corrections
    if accepted_dependencies:
        accepted["dependency_dispositions"] = accepted_dependencies
    if accepted_rationales:
        accepted["rationale_ids"] = list(accepted_rationales.keys())
    if accepted:
        compact["decisions"] = accepted

    diagnostics = session.get("diagnostics")
    if isinstance(diagnostics, list) and diagnostics:
        compact["diagnostics"] = _compact_diagnostics(diagnostics)

    return compact


def compute_missing_finalization_ids(
    *,
    scope_ids: Sequence[str],
    correction_ids: Sequence[str],
    dependency_ids: Sequence[str],
    scope_statuses: Mapping[str, str],
    correction_dispositions: Mapping[str, str],
    dependency_dispositions: Mapping[str, str],
    rationales: Mapping[str, str],
) -> dict[str, list[str]]:
    """Exact unresolved decision and rationale IDs for the current session."""
    missing_scope = [sid for sid in scope_ids if sid not in scope_statuses]
    missing_corrections = [cid for cid in correction_ids if cid not in correction_dispositions]
    missing_dependencies = [did for did in dependency_ids if did not in dependency_dispositions]
    missing_rationale: list[str] = []
    for cid, disposition in correction_dispositions.items():
        if disposition == "ir_only_exception" and cid not in rationales:
            missing_rationale.append(cid)
    for did, disposition in dependency_dispositions.items():
        if disposition == "not_applicable" and did not in rationales:
            missing_rationale.append(did)
    return {
        "scope_ids": missing_scope,
        "correction_ids": missing_corrections,
        "dependency_ids": missing_dependencies,
        "rationale_ids": missing_rationale,
    }


def session_requirement_ids(session: Mapping[str, Any]) -> dict[str, list[str]]:
    requirements = (
        session.get("requirements") if isinstance(session.get("requirements"), Mapping) else {}
    )
    return {
        "scope_ids": [
            str(item).strip()
            for item in (requirements.get("scope_ids") or [])
            if str(item or "").strip()
        ],
        "correction_ids": _requirement_ids(
            requirements.get("correction_candidates"),
            id_keys=("target_entity_id",),
        ),
        "dependency_ids": _requirement_ids(
            requirements.get("dependency_candidates"),
            id_keys=("candidate_id", "dependency_id"),
        ),
    }


def _bound_requirement_lane(
    items: Sequence[Any],
    *,
    lane: str,
    maximum: int,
    diagnostics: list[dict[str, Any]],
) -> list[Any]:
    observed = len(items)
    if observed > maximum:
        diagnostics.append(
            {
                "code": REQUIREMENTS_CAPACITY_EXCEEDED,
                "lane": lane,
                "observed_count": observed,
                "maximum_count": maximum,
                "message": (
                    f"Finalization {lane} discovery exceeded publish capacity "
                    f"({observed} > {maximum})."
                ),
            }
        )
        return list(items[:maximum])
    return list(items)


def _compact_correction_requirements(
    rows: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    compact: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        target = str(row.get("target_entity_id") or "").strip()
        if not target:
            continue
        entry: dict[str, Any] = {"target_entity_id": target}
        value_kind = str(row.get("value_kind") or "").strip()
        if value_kind:
            entry["value_kind"] = value_kind
        for key in ("inherited_value", "selected_ir_display_value", "matching_patch_target_id"):
            raw = row.get(key)
            if isinstance(raw, str) and raw.strip():
                entry[key] = raw.strip()
            elif raw is not None and key == "inherited_value" and not isinstance(raw, (dict, list)):
                entry[key] = raw
        basis_refs = row.get("basis_refs")
        if isinstance(basis_refs, list) and basis_refs:
            entry["basis_refs"] = [
                str(ref).strip()
                for ref in basis_refs
                if isinstance(ref, str) and str(ref).strip()
            ][:_MAX_BASIS_REFS]
        compact.append(entry)
    return compact


def _compact_dependency_requirements(
    rows: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    compact: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        candidate_id = str(row.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        entry: dict[str, Any] = {
            "candidate_id": candidate_id,
            "dependency_id": str(row.get("dependency_id") or candidate_id).strip() or candidate_id,
        }
        affected = str(row.get("affected_scope") or "").strip()
        if affected:
            entry["affected_scope"] = affected
        description = str(row.get("description") or "").strip()
        if description:
            entry["description"] = description[:512]
        compact.append(entry)
    return compact


def _compact_diagnostics(
    rows: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    capacity_rows: list[dict[str, Any]] = []
    other_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        code = str(row.get("code") or "").strip()
        if not code:
            continue
        entry: dict[str, Any] = {"code": code}
        message = str(row.get("message") or "").strip()
        if message:
            entry["message"] = message[:256]
        lane = str(row.get("lane") or "").strip()
        if lane:
            entry["lane"] = lane
        if row.get("observed_count") is not None:
            try:
                entry["observed_count"] = int(row.get("observed_count"))
            except (TypeError, ValueError):
                pass
        if row.get("maximum_count") is not None:
            try:
                entry["maximum_count"] = int(row.get("maximum_count"))
            except (TypeError, ValueError):
                pass
        candidate_id = str(row.get("candidate_id") or "").strip()
        if candidate_id:
            entry["candidate_id"] = candidate_id
        observed = row.get("observed_scope_ids")
        if isinstance(observed, list):
            entry["observed_scope_ids"] = [
                str(item).strip() for item in observed if str(item or "").strip()
            ][:_MAX_OBSERVED_SCOPE_IDS]
        if code == REQUIREMENTS_CAPACITY_EXCEEDED:
            capacity_rows.append(entry)
        else:
            other_rows.append(entry)
    # Capacity diagnostics always retain slots so truncation cannot become silent.
    retained_capacity = capacity_rows[:_MAX_DIAGNOSTICS]
    remaining = _MAX_DIAGNOSTICS - len(retained_capacity)
    return retained_capacity + other_rows[:remaining]


def _requirement_ids(
    rows: object,
    *,
    id_keys: Sequence[str],
) -> list[str]:
    if not isinstance(rows, list):
        return []
    ids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        for key in id_keys:
            value = str(row.get(key) or "").strip()
            if value and value not in seen:
                seen.add(value)
                ids.append(value)
                break
    return ids


def _accepted_decision_map(
    raw: object,
    *,
    known_ids: set[str],
    allowed_values: Sequence[str],
    maximum: int,
) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        return {}
    allowed = set(allowed_values)
    out: dict[str, str] = {}
    for key, value in raw.items():
        text_key = str(key or "").strip()
        if not text_key or text_key not in known_ids:
            continue
        text_value = str(value or "").strip()
        if text_value not in allowed:
            continue
        out[text_key] = text_value
        if len(out) >= maximum:
            break
    return out


def _accepted_rationales(
    raw: object,
    *,
    known_ids: set[str],
    maximum: int,
) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        text_key = str(key or "").strip()
        if not text_key or text_key not in known_ids:
            continue
        text_value = str(value or "").strip()
        if not text_value or len(text_value) > MAX_RATIONALE_CHARS:
            continue
        out[text_key] = text_value
        if len(out) >= maximum:
            break
    return out
