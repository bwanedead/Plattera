"""Prompt-facing compact projection of resolution work graph state.

This module is read-only: it projects durable ``ResolutionState`` into a compact
prompt view without mutating, truncating, or deleting checkpoint/audit state.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...mission_state import ResolutionState
from .prompt_utils import jsonable

PROJECTION_KIND = "work_graph_projection.v1"
COMPACT_TEXT_MAX_CHARS = 180
MAX_EVIDENCE_REFS = 8
_OPAQUE_KEYS_STRIPPED_FROM_PROMPT = frozenset({"launch_context", "turn_snapshot"})

_CLOSED_STATUSES = frozenset({"closed", "resolved", "done", "complete", "completed"})
_EARNED_DETERMINATIONS = frozenset({"earned", "resolved", "verified"})
_REPAIR_FEEDBACK_KEYS = (
    "outcome",
    "reason_code",
    "semantic_repair_debt",
    "pending_hitl_integration_prompt_ids",
    "row_skip_details",
    "validation_errors",
    "repair_targets",
    "repair_hint",
)


def build_prompt_work_graph_projection(
    resolution_state: ResolutionState,
    *,
    state_patch_feedback: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a compact prompt view of the work graph.

    Closed/stable rows are projected as index-card rows. Open, active, blocked,
    or repair-adjacent rows keep richer continuation fields.
    """
    active_item_id = resolution_state.active_item_id
    repair_feedback = _compact_repair_feedback(state_patch_feedback)
    projection: dict[str, Any] = {
        "projection_kind": PROJECTION_KIND,
        "active_item_id": active_item_id,
        "items": [
            _project_item(item, active_item_id=active_item_id)
            for item in resolution_state.items
        ],
    }
    if resolution_state.relations:
        projection["relations"] = [
            _project_relation(relation)
            for relation in resolution_state.relations
        ]
    if repair_feedback:
        projection["repair_feedback"] = repair_feedback
    if resolution_state.opaque_payload:
        opaque_keys = sorted(
            str(k)
            for k in resolution_state.opaque_payload.keys()
            if str(k) not in _OPAQUE_KEYS_STRIPPED_FROM_PROMPT
        )
        if opaque_keys:
            projection["opaque_payload_keys"] = opaque_keys
    return projection


def _project_item(item: Any, *, active_item_id: str | None) -> dict[str, Any]:
    payload = jsonable(item)
    if not isinstance(payload, dict):
        return {}
    compact = _is_closed(payload) and not _needs_detail(payload, active_item_id=active_item_id)
    row: dict[str, Any] = {
        "item_id": payload.get("item_id"),
        "title": payload.get("title"),
        "kind": payload.get("kind"),
        "status": payload.get("status"),
    }
    _copy_if_present(row, payload, "determination")
    _copy_if_present(row, payload, "structure_kind")
    _copy_if_present(row, payload, "blocking")
    _copy_if_present(row, payload, "requires_hitl")
    _copy_if_present(row, payload, "no_further_progress")
    _copy_if_present(row, payload, "dependencies")
    _copy_if_present(row, payload, "closure_summary")
    _copy_if_present(row, payload, "reopen_triggers")
    _copy_sequence_fields(row, payload)
    _copy_evidence(row, payload)

    verification_basis = payload.get("verification_basis")
    if compact:
        compact_basis = _compact_text(verification_basis)
        if compact_basis is not None:
            row["verification_basis"] = compact_basis
    else:
        for key in (
            "summary",
            "verification_basis",
            "next_needed_step",
            "completion_criteria",
            "notes",
            "context_notes",
        ):
            _copy_if_present(row, payload, key)

    covered_units = payload.get("covered_units")
    if isinstance(covered_units, list) and covered_units:
        row["covered_units"] = [
            _project_covered_unit(
                unit,
                compact=_is_closed(unit) and not _needs_unit_detail(unit),
            )
            for unit in covered_units
            if isinstance(unit, Mapping)
        ]
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}


def _project_covered_unit(unit: Mapping[str, Any], *, compact: bool) -> dict[str, Any]:
    payload = dict(unit)
    row: dict[str, Any] = {
        "unit_id": payload.get("unit_id"),
        "label": payload.get("label") or payload.get("title"),
        "status": payload.get("status"),
    }
    for key in (
        "kind",
        "determination",
        "value_kind",
        "candidate_values",
        "determined_value",
        "materiality",
        "closure_summary",
        "reopen_triggers",
    ):
        _copy_if_present(row, payload, key)
    _copy_evidence(row, payload)
    verification_basis = payload.get("verification_basis")
    if compact:
        compact_basis = _compact_text(verification_basis)
        if compact_basis is not None:
            row["verification_basis"] = compact_basis
    else:
        for key in ("summary", "verification_basis", "next_needed_step", "opaque_payload"):
            _copy_if_present(row, payload, key)
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}


def _project_relation(relation: Any) -> dict[str, Any]:
    payload = jsonable(relation)
    if not isinstance(payload, dict):
        return {}
    row = {
        "source_item_id": payload.get("source_item_id"),
        "target_item_id": payload.get("target_item_id"),
        "relation_type": payload.get("relation_type"),
    }
    compact_summary = _compact_text(payload.get("summary"))
    if compact_summary is not None:
        row["summary"] = compact_summary
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}


def _is_closed(payload: Mapping[str, Any]) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    determination = str(payload.get("determination") or "").strip().lower()
    return status in _CLOSED_STATUSES or determination in _EARNED_DETERMINATIONS


def _needs_detail(payload: Mapping[str, Any], *, active_item_id: str | None) -> bool:
    item_id = payload.get("item_id")
    if active_item_id and item_id == active_item_id:
        return True
    status = str(payload.get("status") or "").strip().lower()
    if status in {"open", "active", "blocked", "in_review", "failed", "rejected"}:
        return True
    return bool(payload.get("blocking") or payload.get("requires_hitl") or payload.get("no_further_progress"))


def _needs_unit_detail(payload: Mapping[str, Any]) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    if status in {"open", "active", "blocked", "in_review", "failed", "rejected"}:
        return True
    return bool(payload.get("next_needed_step"))


def _copy_evidence(row: dict[str, Any], payload: Mapping[str, Any]) -> None:
    refs = payload.get("evidence_refs")
    if isinstance(refs, list) and refs:
        row["evidence_refs"] = [str(ref) for ref in refs[:MAX_EVIDENCE_REFS]]
        row["evidence_ref_count"] = len(refs)
    locators = payload.get("evidence_locators")
    if isinstance(locators, list) and locators:
        row["evidence_locator_count"] = len(locators)


def _copy_sequence_fields(row: dict[str, Any], payload: Mapping[str, Any]) -> None:
    for key in ("sequence_scope", "sequence_index"):
        _copy_if_present(row, payload, key)


def _copy_if_present(row: dict[str, Any], payload: Mapping[str, Any], key: str) -> None:
    value = payload.get(key)
    if value not in (None, "", [], {}):
        row[key] = value


def _compact_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > COMPACT_TEXT_MAX_CHARS or "\n" in text:
        return None
    return text


def _compact_repair_feedback(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    feedback: dict[str, Any] = {}
    for key in _REPAIR_FEEDBACK_KEYS:
        raw = value.get(key)
        if raw not in (None, "", [], {}):
            feedback[key] = jsonable(raw)
    return feedback
